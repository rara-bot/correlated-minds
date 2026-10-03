"""Which stored logprobs can carry the 5.4(a) leg, and the probability they imply.

Deviation 19. The positions below are copied from rows served between 2026-09-09
and 2026-09-13: OpenAI's for gpt_mid, and the only two deepseek hosts that send
logprobs at all. DigitalOcean answered 0.57 while listing four alternatives four
nats likelier than the "57" it emitted. Google listed, at the decimals of 0.95,
the alternatives of the position before them.
"""

import math
from types import SimpleNamespace

import pytest

from neff import logprobs


def row(raw, positions, forecast, model="gpt_mid", provider="openai", host=None):
    return {"model_key": model, "provider": provider, "upstream_provider": host,
            "raw_response": raw, "forecast": forecast, "logprobs": positions}


OPENAI = row(
    '{"probability":0.3,"direction":"no","confidence":0.7,'
    '"rationale":"Current yields and spread suggest moderate tightening"}',
    [{"t": "0", "lp": -0.0006, "top": [["0", -0.0006], [" ", -7.5006], ["۰", -26.2506],
                                       ["-", -26.3756], ["０", -26.8756]]},
     {"t": "3", "lp": -0.4977, "top": [["3", -0.4977], ["35", -1.1227], ["25", -3.7477],
                                       ["4", -3.9977], ["2", -4.8727]]},
     {"t": "0", "lp": 0.0, "top": [["0", 0.0], [" ", -28.0], ["۰", -29.875],
                                   ["０", -31.375], ["٠", -32.375]]},
     {"t": "7", "lp": -0.0087, "top": [["7", -0.0087], ["6", -5.2587], ["75", -6.2587],
                                       ["65", -6.5087], ["8", -9.5087]]}],
    0.3)

DIGITALOCEAN = row(
    '{"probability": 0.57, "direction": "yes", "confidence": 0.6, '
    '"rationale": "Recent trend is upward, but economic conditions create uncertainty."}',
    [{"t": "0", "lp": -0.0006, "top": [["0", -0.0006], ["1", -7.5006], ["2", -15.0006],
                                       ["9", -15.5006], ["5", -15.5006]]},
     {"t": "57", "lp": -6.1827, "top": [["57", -6.1827], ["75", -2.1827], ["7", -2.1827],
                                        ["65", -2.1827], ["85", -2.1827]]}],
    0.57, model="deepseek", provider="openrouter", host="DigitalOcean")

GOOGLE = row(
    '{"probability": 0.95, "direction": "yes", "confidence": 0.8, '
    '"rationale": "Recent quarterly revenue is $96.22B, far above the $70.60B threshold."}',
    [{"t": "0", "lp": -0.0025, "top": [["0", -0.0025], ["1", -6.0025], ["9", -16.0025],
                                       ["2", -16.5025], ["3", -17.5025]]},
     {"t": "95", "lp": -1.391, "top": [["0", -0.0025], ["1", -6.0025], ["9", -16.0025],
                                       ["2", -16.5025], ["3", -17.5025]]}],
    0.95, model="deepseek", provider="openrouter", host="Google")


def expectation(weights):
    return sum(math.exp(lp) * v for v, lp in weights.items()) / sum(math.exp(lp) for lp in weights.values())


class TestConsistency:
    def test_a_greedy_answer_is_consistent(self):
        assert logprobs.consistent(OPENAI)

    def test_an_emitted_token_less_likely_than_its_alternatives_is_not(self):
        assert not logprobs.consistent(DIGITALOCEAN)

    def test_alternatives_that_do_not_list_the_emitted_token_are_not(self):
        assert not logprobs.consistent(GOOGLE)

    def test_a_tie_is_still_greedy(self):
        tied = dict(OPENAI, logprobs=[OPENAI["logprobs"][0],
                                      {"t": "3", "lp": -0.6931, "top": [["35", -0.6931], ["3", -0.6931]]}])
        assert logprobs.consistent(tied)

    def test_a_row_without_logprobs_is_never_consistent(self):
        assert not logprobs.consistent(dict(OPENAI, logprobs=None))

    def test_reads_observations_as_well_as_dicts(self):
        assert logprobs.consistent(SimpleNamespace(**OPENAI))
        assert not logprobs.consistent(SimpleNamespace(**GOOGLE))


class TestSources:
    PASSING_DIGITALOCEAN = dict(DIGITALOCEAN, logprobs=DIGITALOCEAN["logprobs"][:1])

    def test_a_direct_vendor_api_is_its_own_host(self):
        assert logprobs.source(OPENAI) == ("gpt_mid", "openai")
        assert logprobs.source(GOOGLE) == ("deepseek", "Google")

    def test_one_inconsistent_row_condemns_its_whole_source(self):
        verdict = logprobs.usable_sources([self.PASSING_DIGITALOCEAN, DIGITALOCEAN, OPENAI])
        assert verdict == {("deepseek", "DigitalOcean"): False, ("gpt_mid", "openai"): True}

    def test_the_same_model_on_another_host_is_judged_on_its_own_rows(self):
        other = dict(self.PASSING_DIGITALOCEAN, upstream_provider="AtlasCloud")
        verdict = logprobs.usable_sources([DIGITALOCEAN, other])
        assert verdict == {("deepseek", "DigitalOcean"): False, ("deepseek", "AtlasCloud"): True}

    def test_rows_without_logprobs_make_no_source(self):
        assert logprobs.usable_sources([dict(OPENAI, logprobs=None)]) == {}


class TestTheDerivedProbability:
    def test_is_the_expectation_over_the_decimal_token(self):
        weights = {0.3: -0.4977, 0.35: -1.1227, 0.25: -3.7477, 0.4: -3.9977, 0.2: -4.8727}
        assert logprobs.derived_probability(OPENAI) == pytest.approx(expectation(weights))

    def test_a_token_that_carries_the_whole_number(self):
        merged = row('{"probability": 0.35}',
                     [{"t": " 0.35", "lp": -0.4, "top": [[" 0.35", -0.4], [" 0.3", -1.4],
                                                          [" 0.4", -2.4], ["x", -3.0]]}], 0.35)
        weights = {0.35: -0.4, 0.3: -1.4, 0.4: -2.4}
        assert logprobs.derived_probability(merged) == pytest.approx(expectation(weights))

    def test_look_alike_digits_are_not_numbers(self):
        lookalike = dict(OPENAI, logprobs=[OPENAI["logprobs"][0],
                                           {"t": "3", "lp": -0.1, "top": [["3", -0.1], ["۳", -2.5]]}])
        assert logprobs.derived_probability(lookalike) == pytest.approx(0.3)

    def test_none_when_other_digits_come_first(self):
        shifted = row('{"rationale": "Payrolls rose 22,000", "probability": 0.3}',
                      [{"t": "22", "lp": 0.0, "top": [["22", 0.0]]}] + OPENAI["logprobs"][:2], 0.3)
        assert logprobs.derived_probability(shifted) is None

    def test_none_without_a_decimal_part(self):
        whole = row('{"probability": 1, "direction": "yes"}',
                    [{"t": "1", "lp": 0.0, "top": [["1", 0.0]]}], 1.0)
        assert logprobs.derived_probability(whole) is None

    def test_none_when_the_numeral_disagrees_with_the_stored_forecast(self):
        assert logprobs.derived_probability(dict(OPENAI, forecast=0.35)) is None

    def test_none_when_the_decimals_span_two_tokens(self):
        split = row('{"probability": 0.35}',
                    [{"t": "0", "lp": 0.0, "top": [["0", 0.0]]},
                     {"t": "3", "lp": -0.1, "top": [["3", -0.1], ["4", -2.4]]},
                     {"t": "5", "lp": -0.2, "top": [["5", -0.2]]}], 0.35)
        assert logprobs.derived_probability(split) is None

    def test_never_falls_back_to_the_emitted_value(self):
        nothing_numeric = dict(OPENAI, logprobs=[OPENAI["logprobs"][0],
                                                 {"t": "3", "lp": -0.1, "top": [[" ", -0.1]]}])
        assert logprobs.derived_probability(nothing_numeric) is None


class TestSummary:
    def test_counts_what_the_leg_can_use(self):
        out = logprobs.summary([OPENAI, DIGITALOCEAN, GOOGLE, dict(OPENAI, logprobs=None)])
        assert out["gpt_mid"] == {"with_logprobs": 1, "inconsistent": 0, "usable": 1, "derived": 1,
                                  "hosts": {"openai": {"rows": 1, "inconsistent": 0, "usable": True}}}
        assert out["deepseek"]["with_logprobs"] == 2
        assert out["deepseek"]["usable"] == 0
        assert out["deepseek"]["hosts"]["Google"] == {"rows": 1, "inconsistent": 1, "usable": False}
