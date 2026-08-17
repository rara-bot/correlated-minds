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

# Sub-caps per workstream, so one arm cannot quietly consume the whole budget.
# These sum to less than the cap on purpose -- the remainder is reserve, released
# only against the Week-5 interim read.
ARM_CAPS_USD = {
    "pilot": 10.0,
    "ws1_prospective": 70.0,
    "ws2_retrospective": 40.0,
    "ws5_mitigation": 25.0,
    "h2_reasoning": 40.0,
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
    notes: str = ""


# --- the panel --------------------------------------------------------------
# Seven models across SIX families => 21 pairs. The two Anthropic models are a
# deliberate within-family control: H3 asks whether cross-family diversity buys
# real independence where same-family and prompt-level diversity do not.
#
# !! model_id values MUST be verified against each provider's live model list
#    before collection starts. `python -m neff.verify` does this and fails loudly.
#    Prices are USD per million tokens and must be re-checked at purchase time.

PANEL: List[ModelSpec] = [
    ModelSpec(
        key="claude_sonnet",
        provider="anthropic",
        model_id="claude-sonnet-5",
        family="anthropic",
        price=Price(input_per_mtok=3.00, output_per_mtok=15.00),
        tier="frontier",
        notes="Frontier anchor: lets us test whether capability tier affects correlation.",
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
        model_id="gpt-5-mini",
        family="openai",
        price=Price(input_per_mtok=0.25, output_per_mtok=2.00),
        tier="mid",
        supports_logprobs=True,
        notes="VERIFY id and price before launch.",
    ),
    ModelSpec(
        key="gemini_flash",
        provider="google",
        model_id="gemini-2.5-flash-lite",
        family="google",
        price=Price(input_per_mtok=0.10, output_per_mtok=0.40),
        tier="mid",
        notes="Free tier may cover much of the pilot. VERIFY id and price.",
    ),
    ModelSpec(
        key="llama",
        provider="openrouter",
        model_id="meta-llama/llama-3.3-70b-instruct",
        family="meta",
        price=Price(input_per_mtok=0.20, output_per_mtok=0.60),
        tier="mid",
        supports_logprobs=True,
        notes="Open-weight, hosted. VERIFY id and price.",
    ),
    ModelSpec(
        key="qwen",
        provider="openrouter",
        model_id="qwen/qwen-2.5-72b-instruct",
        family="alibaba",
        price=Price(input_per_mtok=0.20, output_per_mtok=0.60),
        tier="mid",
        supports_logprobs=True,
        notes="Open-weight, hosted. VERIFY id and price.",
    ),
    ModelSpec(
        key="deepseek",
        provider="openrouter",
        model_id="deepseek/deepseek-chat",
        family="deepseek",
        price=Price(input_per_mtok=0.30, output_per_mtok=0.90),
        tier="mid",
        supports_logprobs=True,
        notes="Open-weight, hosted. VERIFY id and price.",
    ),
]


def enabled_panel() -> List[ModelSpec]:
    return [m for m in PANEL if m.enabled]


def panel_by_key() -> Dict[str, ModelSpec]:
    return {m.key: m for m in PANEL}


def families() -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for m in enabled_panel():
        out.setdefault(m.family, []).append(m.key)
    return out


# --- collection constants ---------------------------------------------------

# Sampling is pinned so that cross-model differences reflect the models rather
# than our sampling noise. temperature=0 is deliberate: we want each model's
# modal judgement. Prompt-variant diversity (H3) is manipulated explicitly at
# the prompt level, never accidentally through sampling randomness.
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 400

# Structured output keeps cost down AND removes measurement noise: free-text
# rationale length varies wildly across families, and we correlate decisions,
# not prose.
RESPONSE_SCHEMA_VERSION = "v1"

# 10% of prospective calls also collect extended reasoning, for the H2
# shared-prior mechanism analysis.
REASONING_SUBSAMPLE_RATE = 0.10

TASKS_PER_DAY = 25
COLLECTION_START = "2026-08-24"
CALIBRATION_END = "2026-09-27"   # end of Week 5: prediction is frozen after this
DATA_FREEZE = "2026-12-06"

# Market-state variables used for the H1 conditional test. Registered here so the
# analysis cannot quietly grow new ones after seeing results.
STATE_VARIABLES = [
    "vix_level",
    "realized_vol_20d",
    "expectation_dispersion",
    "abs_surprise",
    "news_volume",
    "novelty_score",
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
    model_keys: Optional[List[str]] = field(default=None)

    def models(self) -> List[ModelSpec]:
        panel = enabled_panel()
        if self.model_keys is None:
            return panel
        keys = set(self.model_keys)
        return [m for m in panel if m.key in keys]
