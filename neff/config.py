"""Panel configuration: the model roster, pricing, and run constants.

Everything here is deliberately explicit and version-pinned. Providers silently
upgrade model aliases (`-latest` style names), and a silent mid-panel model swap
would corrupt a longitudinal correlation study in a way that is very hard to
detect after the fact. So we pin exact IDs, log the ID returned by the API on
every single call, and treat any drift as an event worth recording.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .ledger import Price

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OBS_PATH = DATA_DIR / "observations.jsonl"
LEDGER_PATH = DATA_DIR / "ledger.jsonl"
TASKS_PATH = DATA_DIR / "tasks.jsonl"
RESOLUTIONS_PATH = DATA_DIR / "resolutions.jsonl"

# --- budget -----------------------------------------------------------------
# Hard cap. Enforced in code by neff.ledger.Ledger, not by discipline.
BUDGET_USD = 200.0

# Measured, not assumed. `neff.collect --dry-run --tasks 25` on 21 Aug 2026,
# pricing the real task battery against the real roster of ten collected models.
# The planning documents had carried $0.24/day for a NINE-model panel, which was
# both stale and roughly half the true figure.
MEASURED_DAILY_USD = 0.4442


def collection_days() -> int:
    """Calendar days of collection, inclusive of both endpoints."""
    from datetime import date as _date

    return (_date.fromisoformat(DATA_FREEZE) - _date.fromisoformat(COLLECTION_START)).days + 1


def projected_ws1_usd() -> float:
    """What the 15-week prospective panel is actually expected to cost.

    Includes the test-retest replicates of PREREGISTRATION.md 5.4(d). They are
    real calls on the same arm, so excluding them would understate the projection
    the arm cap is set against -- the exact way the previous $25 figure went
    stale and left a hard stop sitting two thirds of the way up the real spend.
    """
    per_day = MEASURED_DAILY_USD * (1.0 + REPLICATES_PER_DAY / TASKS_PER_DAY)
    return per_day * collection_days()


# Sub-caps per workstream, so one arm cannot quietly consume the whole budget.
# These sum to less than the cap on purpose -- the remainder is reserve, released
# only against the Week-5 interim read.
#
# ws1_prospective was $70 against a projected spend of ~$47, and the projection
# it was set from said $25. An arm cap is not a warning: `Ledger.check` raises
# BudgetExceeded, so reaching it STOPS COLLECTION. A 15-week unattended run whose
# per-day cost drifts up -- longer prompts as filings accumulate, more re-asked
# open questions -- would have halted in November, at the far end of the panel,
# with no way to recover the lost days. The cap now carries roughly 2x the
# measured projection, and `tests/test_budget_headroom.py` fails if that margin
# is ever eroded. The GLOBAL $200 cap is unchanged: this reallocates headroom
# between arms, it does not create any.
ARM_CAPS_USD = {
    "pilot": 10.0,
    "ws1_prospective": 110.0,   # ~2.2x the measured projection incl. replicates
    "ws2_retrospective": 20.0,
    "ws5_mitigation": 10.0,
    "h2_reasoning": 35.0,
}


@dataclass(frozen=True)
class ModelSpec:
    """One member of the panel.

    key:      stable short name used in our data files. NEVER change this once
              collection starts -- it is the join key across the whole study.
    provider: which client handles it.
    model_id: exact pinned API identifier.
    family:   vendor/lineage grouping. The H3 test (intra-family vs cross-family
              diversity) is defined entirely by this field, so it must reflect
              genuine lineage rather than marketing.
    """

    key: str
    provider: str
    model_id: str
    family: str
    price: Price
    tier: str = "mid"
    supports_logprobs: bool = False
    enabled: bool = True
    primary: bool = True
    # thinking_budget: Google only. None means "send no thinkingConfig at all",
    # which is REQUIRED for models that reject the field -- `gemini-3.5-flash-lite`
    # answers HTTP 400 `Request contains an invalid argument` if it is present.
    # 0 disables extended thinking on models that support the field.
    #
    # Per-model rather than per-provider for exactly the reason AUDIT.md findings
    # 13 and 15 record: within one vendor, one model accepts a parameter and its
    # sibling rejects it, and a provider-wide setting silently breaks whichever
    # one disagrees.
    thinking_budget: Optional[int] = None
    notes: str = ""


# --- the panel --------------------------------------------------------------
# NINE models across SIX families => 36 pairs, of which THREE are within-family.
#
# The three within-family pairs (Anthropic, OpenAI, Google) are the entire
# evidence base for H3 ("intra-vendor diversity is an illusion") and for the H6
# capability control. An earlier version of this panel had SEVEN models and
# exactly ONE within-family pair, which made both hypotheses nearly undecidable:
#
#   - Inference by cluster-robust SE was invalid outright. Clustering is by pair,
#     so with one within-family pair the `same_family` coefficient's variance came
#     from a single cluster. On synthetic data with NO family structure it
#     returned t = +7.06 and declared the effect real -- a false positive
#     manufactured by the estimator.
#   - The valid alternative, an exact permutation test over family labels, has
#     only C(7,2) = 21 distinct labelings, so its BEST ACHIEVABLE p-value was
#     1/21 = 0.048. A headline hypothesis cannot rest on a test whose ceiling is
#     the significance threshold.
#
# With three within-family pairs the permutation floor drops below 0.001. The
# marginal cost is a few dollars on a $23 study; the marginal rigour is the
# difference between a decidable hypothesis and an undecidable one.
#
# Each added model is the SAME vendor at a DIFFERENT tier, mirroring the
# Anthropic pair, so the three within-family pairs are structurally comparable.
#
# !! Undated ids like `gpt-4.1-mini` are ALIASES: the live call returned
#    `gpt-4.1-mini-2025-04-14`. The drift check caught it. Dated snapshots are
#    pinned instead, so OpenAI repointing an alias mid-panel cannot swap a model
#    underneath a 15-week longitudinal study.
# !! model_id values MUST be verified against each provider's live model list
#    before collection starts. `python -m neff.verify` does this and fails loudly.
#    Prices are USD per million tokens and must be re-checked at purchase time.

PANEL: List[ModelSpec] = [
    ModelSpec(
        key="claude_sonnet",
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        family="anthropic",
        price=Price(input_per_mtok=3.00, output_per_mtok=15.00),
        tier="frontier",
        notes=(
            "Frontier anchor: lets us test whether capability tier affects "
            "correlation. VERIFIED 19 Aug 2026 by live call at temperature=0. "
            "NOT claude-sonnet-5: that model REMOVED the sampling parameters and "
            "returns HTTP 400 `temperature is deprecated for this model`. "
            "TEMPERATURE=0.0 is a REGISTERED parameter (PREREGISTRATION.md 9), so a "
            "panel member that cannot honour it would sample differently from the "
            "other eight and confound model differences with sampling differences. "
            "Sonnet 4.6 is the newest Anthropic model that still accepts "
            "temperature, at identical $3/$15 pricing."
        ),
    ),
    ModelSpec(
        key="claude_haiku",
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        family="anthropic",
        price=Price(input_per_mtok=1.00, output_per_mtok=5.00),
        tier="mid",
        notes="Same family as claude_sonnet -- this pair is a within-family H3 control.",
    ),
    ModelSpec(
        key="gpt_mid",
        provider="openai",
        model_id="gpt-4.1-mini-2025-04-14",
        family="openai",
        price=Price(input_per_mtok=0.4, output_per_mtok=1.6),
        tier="mid",
        supports_logprobs=True,
        notes=(
            "Within-family pair with gpt_small. VERIFIED 19 Aug 2026 by live call: temperature=0 honoured (5 identical responses to a high-entropy prompt) and logprobs returned. NOT the gpt-5 line: those are reasoning models that reject temperature=0 outright ('Only the default (1) value is supported') and refuse logprobs. Worse, routing them via OpenRouter SILENTLY DROPS temperature -- HTTP 200, sampling at 1, every log reading 0."
        ),
    ),
    ModelSpec(
        key="gemini_flash",
        provider="google",
        model_id="gemini-3.5-flash-lite",
        family="google",
        price=Price(input_per_mtok=0.30, output_per_mtok=2.50),
        tier="small",
        notes=(
            "VERIFIED 19 Aug 2026 by live call. The pinned gemini-2.5-flash-lite "
            "returned HTTP 404 'no longer available to new users'. Price is from "
            "Google's official pricing page, not the roster's original estimate, "
            "which was 3x low on input and 6x low on output."
        ),
    ),
    ModelSpec(
        key="gpt_small",
        provider="openai",
        model_id="gpt-4.1-nano-2025-04-14",
        family="openai",
        price=Price(input_per_mtok=0.1, output_per_mtok=0.4),
        tier="small",
        supports_logprobs=True,
        notes=(
            "Second within-family pair (with gpt_mid). VERIFIED 19 Aug 2026 by live call: temperature=0 honoured (5 identical responses to a high-entropy prompt) and logprobs returned. NOT the gpt-5 line: those are reasoning models that reject temperature=0 outright ('Only the default (1) value is supported') and refuse logprobs. Worse, routing them via OpenRouter SILENTLY DROPS temperature -- HTTP 200, sampling at 1, every log reading 0."
        ),
    ),
    ModelSpec(
        key="gemini_flash_pro",
        provider="google",
        model_id="gemini-3.5-flash",
        family="google",
        price=Price(input_per_mtok=1.50, output_per_mtok=9.00),
        tier="mid",
        thinking_budget=0,
        notes=(
            "Third within-family pair (with gemini_flash). VERIFIED 19 Aug 2026 "
            "by live call. Deliberately SAME generation (3.5) as its pair partner "
            "so the pair isolates TIER while holding generation fixed -- Google's "
            "own 404 message suggested gemini-3.6-flash, which would have "
            "confounded tier with generation in H6's capability regression. "
            "THINKING DISABLED (thinking_budget=0): this is a reasoning model and "
            "`maxOutputTokens` is a budget SHARED between thinking and the visible "
            "answer. At the collection budget of 400 it spent 383 tokens thinking "
            "and 13 answering, returning `{\"probability\": 0.92,` -- truncated and "
            "unparseable. The 21 Aug pilot scored it 0/8 usable, which over 15 "
            "weeks is below the 80% coverage floor of PREREGISTRATION.md 3.3 and "
            "would have dropped it from the primary panel, taking one of H3's "
            "three within-family pairs with it. Thinking off: 71 visible tokens, "
            "parses cleanly, 7x cheaper. Its pair partner gemini-3.5-flash-lite "
            "REJECTS thinkingConfig with HTTP 400, which is why this is a "
            "per-model field and not a provider default."
        ),
    ),
    ModelSpec(
        key="llama",
        provider="openrouter",
        model_id="meta-llama/llama-3.3-70b-instruct",
        family="meta",
        price=Price(input_per_mtok=0.10, output_per_mtok=0.32),
        tier="mid",
        supports_logprobs=True,
        notes=(
            "Open-weight, hosted. VERIFIED 19 Aug 2026 by live call; price read "
            "from OpenRouter's own /models endpoint, not documentation."
        ),
    ),
    ModelSpec(
        key="qwen",
        provider="openrouter",
        model_id="qwen/qwen-2.5-72b-instruct",
        family="alibaba",
        price=Price(input_per_mtok=0.36, output_per_mtok=0.40),
        tier="mid",
        supports_logprobs=False,
        notes=(
            "Open-weight, hosted. VERIFIED 19 Aug 2026 by live call; price read "
            "from OpenRouter's own /models endpoint, not documentation."
        ),
    ),
    ModelSpec(
        key="deepseek",
        provider="openrouter",
        model_id="deepseek/deepseek-v3.2",
        family="deepseek",
        price=Price(input_per_mtok=0.269, output_per_mtok=0.40),
        tier="mid",
        supports_logprobs=True,
        notes=(
            "Open-weight, hosted. VERIFIED 19 Aug 2026 by live call. Repinned from "
            "`deepseek/deepseek-chat`, which is a FLOATING ALIAS with no version -- "
            "exactly the silent mid-panel model swap this module's header warns "
            "against. OpenRouter retains old versions (v3-0324 is still served), so "
            "a dated pin carries little retirement risk over 15 weeks."
        ),
    ),
    # --- SECONDARY frontier panel (primary=False) --------------------------
    # Collected daily alongside the primary nine, but EXCLUDED from the primary
    # panel, because H4 matches human forecasters at M = 9 against measured SPF
    # headroom of 0.112-0.171 AT THAT PANEL SIZE. Folding this in would make the
    # panel M = 10 and invalidate that baseline.
    #
    # Why it exists: the primary panel has exactly ONE frontier model, and it is
    # Anthropic -- so at the frontier, tier is perfectly confounded with family and
    # "frontier models behave differently" cannot be told apart from "Anthropic
    # behaves differently". This is the same structural defect that took the panel
    # from seven models to nine for H3.
    #
    # Why now rather than after the Week-5 read: §9 freezes the roster, but a model
    # not collected cannot be collected retroactively. A model that turns out to be
    # unnecessary can simply be ignored in analysis; the reverse is impossible.
    ModelSpec(
        key="gpt_frontier",
        provider="openai",
        model_id="gpt-4.1-2025-04-14",
        family="openai",
        price=Price(input_per_mtok=2.00, output_per_mtok=8.00),
        tier="frontier",
        supports_logprobs=True,
        primary=False,
        notes=(
            "Secondary frontier panel. " + "VERIFIED 19 Aug 2026: temperature=0 honoured, logprobs returned. "
            "Originally pinned to openai/gpt-5.1 via OpenRouter; that combination "
            "SILENTLY DROPPED temperature (HTTP 200, sampling at 1), which would "
            "have violated a registered parameter invisibly for 15 weeks. Direct "
            "OpenAI at least fails loudly. Google frontier rejected: 2.5-pro 404s "
            "for new accounts, 3.1-pro is a PREVIEW id."
        ),
    ),
]


def enabled_panel() -> List[ModelSpec]:
    """Everything we COLLECT -- primary panel plus secondary arms.

    Collection is deliberately wider than analysis: an uncollected day cannot be
    recovered, whereas a collected model can always be excluded later.
    """
    return [m for m in PANEL if m.enabled]


def primary_panel() -> List[ModelSpec]:
    """The registered M = 9 panel that the PRIMARY analysis runs on.

    H4 matches human forecasters at M = 9 against SPF headroom measured at that
    exact panel size (PREREGISTRATION.md §4, H4). Anything that silently grew this
    list would invalidate that baseline, so analysis defaults here rather than to
    `enabled_panel()`.
    """
    return [m for m in PANEL if m.enabled and m.primary]


def secondary_panel() -> List[ModelSpec]:
    """Models collected but held out of the primary panel."""
    return [m for m in PANEL if m.enabled and not m.primary]


def panel_by_key() -> Dict[str, ModelSpec]:
    return {m.key: m for m in PANEL}


def families() -> Dict[str, List[str]]:
    """Family -> model keys, over the PRIMARY panel only.

    H3 and H6 are defined on the primary panel's within-family pairs, which are
    deliberately symmetric: exactly one pair per vendor, each the same vendor at
    two tiers. Counting secondary-arm models here would give one vendor three
    models and C(3,2) = 3 within-family pairs, silently destroying that symmetry.
    """
    out: Dict[str, List[str]] = {}
    for m in primary_panel():
        out.setdefault(m.family, []).append(m.key)
    return out


# --- collection constants ---------------------------------------------------

# Sampling is pinned so that cross-model differences reflect the models rather
# than our sampling noise. temperature=0 is deliberate: we want each model's
# modal judgement. Prompt-variant diversity (H3) is manipulated explicitly at
# the prompt level, never accidentally through sampling randomness.
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 400

# !! ROSTER CONSTRAINT, discovered 19 Aug 2026.
# Newer reasoning models are REMOVING the sampling parameters: temperature,
# top_p and top_k all return HTTP 400 on Claude Sonnet 5 / Opus 5 / Opus 4.8 /
# 4.7 / Fable 5. Any model added to PANEL must accept TEMPERATURE above, because
# a member that samples differently from the rest confounds model differences
# with sampling differences -- and temperature is registered in
# PREREGISTRATION.md 9, so this is a frozen commitment, not a preference.
# `python -m neff.verify` makes one real call per model and fails loudly on this.

# Structured output keeps cost down AND removes measurement noise: free-text
# rationale length varies wildly across families, and we correlate decisions,
# not prose.
RESPONSE_SCHEMA_VERSION = "v1"

# 10% of prospective calls also collect extended reasoning, for the H2
# shared-prior mechanism analysis.
REASONING_SUBSAMPLE_RATE = 0.10

TASKS_PER_DAY = 25

# --- test-retest replicates -------------------------------------------------
# TEMPERATURE = 0.0 is registered in section 9 so that cross-model differences
# reflect the models rather than our sampling. Measured 22 Aug 2026 (3 prompts x
# 4 repetitions) it holds for only five of ten models; the other five move their
# probability by 0.033-0.093 on average against an IDENTICAL prompt. Which models
# vary shifts between runs, so it is infrastructure -- batched inference, and
# backend routing on OpenRouter -- not a model property.
#
# The noise is idiosyncratic, so it inflates apparent independence: rho_bar down,
# N_eff up. Conservative for our hypothesis, but unmeasured. These replicates
# measure it: REPLICATES_PER_DAY tasks are asked to every model twice, and the
# spread gives each model's noise floor (PREREGISTRATION.md 5.4d).
#
# Stored at a RESERVED prompt_variant so they cannot contaminate anything:
# panel.load_panel filters to variant 0, and H3's registered variants are 0-4.
REPLICATE_VARIANT = 99
REPLICATES_PER_DAY = 2

COLLECTION_START = "2026-08-24"
CALIBRATION_END = "2026-09-27"   # end of Week 5: prediction is frozen after this
DATA_FREEZE = "2026-12-06"

# Market-state variables for the H1 conditional test. This list must match
# PREREGISTRATION.md 4 EXACTLY -- "fixed, no additions permitted" -- because its
# length also sets the Benjamini-Hochberg denominator and therefore the
# falsification threshold. It previously did not match in three ways at once:
# `news_volume` appeared here but was never registered, the registered
# days-to-resolution was absent, and both documents said "six" while the list
# held seven.
#
# COLLECTED AT ASK TIME (irrecoverable if missed -- they describe the world as it
# stood when the question was put):
#   ladder_distance   experimentally varied ambiguity; available EVERY day, and
#                     the only H1 leg that does not depend on markets supplying a
#                     stress event. Needs the live strike ladder, so it cannot be
#                     reconstructed later.
#   vix_level         from the FRED snapshot
#   realized_vol_20d  from the FRED snapshot
#   days_out          days to resolution; also the registered handling for the
#                     horizon-drift threat in 5.4(b)
#
# DERIVED AT ANALYSIS TIME (safe to compute later; no collection dependency):
#   expectation_dispersion  cross-model dispersion of the panel's own forecasts
#   abs_surprise            |macro surprise| from FRED vintages vs consensus
#   novelty_score           question novelty against the accumulated task corpus
STATE_VARIABLES = [
    "ladder_distance",
    "vix_level",
    "realized_vol_20d",
    "expectation_dispersion",
    "abs_surprise",
    "days_out",
    "novelty_score",
]

# The subset that must be present on the task record at collection time. Checked
# by tests and by neff.verify, because a missing one is unrecoverable after the
# fact whereas a derived one is merely unfinished.
STATE_COLLECTED_AT_ASK = [
    "ladder_distance",
    "vix_level",
    "realized_vol_20d",
    "days_out",
]

USER_AGENT = "neff-research (educational research; contact: rajankhiani@gmail.com)"


@dataclass
class RunConfig:
    """Per-run knobs. Kept separate from the pinned panel so that operational
    changes (concurrency, dry-run) can never be confused with scientific ones."""

    arm: str = "ws1_prospective"
    dry_run: bool = False
    concurrency: int = 4
    tasks_per_day: int = TASKS_PER_DAY
    seed: int = 0
    prompt_variants: int = 1
    replicates_per_day: int = REPLICATES_PER_DAY
    model_keys: Optional[List[str]] = field(default=None)

    def models(self) -> List[ModelSpec]:
        panel = enabled_panel()
        if self.model_keys is None:
            return panel
        keys = set(self.model_keys)
        return [m for m in panel if m.key in keys]
