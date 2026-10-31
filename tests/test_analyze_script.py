"""scripts/analyze.py composes every registered analysis, and no test ran it until 2026-09-14."""

import importlib.util
import json
from pathlib import Path

from neff import config, h3
from neff.stats import family_partitions

ROOT = Path(__file__).resolve().parent.parent


def test_a_blind_run_carries_every_hypothesis_and_the_logprob_leg(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("analyze_script", ROOT / "scripts" / "analyze.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(script.h4, "HORIZONS", (1,))
    monkeypatch.setattr(script.h4, "HUMAN_DRAWS", 10)
    out = tmp_path / "run.json"
    assert script.main(["--n-boot", "3", "--out", str(out)]) == 0
    result = json.loads(out.read_text())
    assert result["blind"] is True
    assert {"primary", "report", "h1", "h2", "h3", "h4", "h5", "h6"} <= set(result)
    assert "logprob_leg" in result["report"]
    assert all(result[k]["blind"] is True for k in ("h2", "h3", "h4", "h5", "h6"))
    # Deviation 24's sensitivity, for every retired member, blind like everything else.
    retired = result["before_retirement"]["gpt_small"]
    assert retired["asked_before"] == "2026-10-23"
    assert all(retired[k]["blind"] is True for k in ("primary", "h3", "h6"))
    # Deviation 27: H3 and H6 are judged before the first retirement; the primary runs stay.
    confirmatory = result["h3_h6_confirmatory"]
    assert confirmatory["asked_before"] == "2026-10-10"
    assert confirmatory["h3"] == result["before_retirement"]["gemini_flash_pro"]["h3"]
    assert confirmatory["h6"] == result["before_retirement"]["gemini_flash_pro"]["h6"]


def test_seven_models_leave_one_pair_which_is_why_deviation_27_exists():
    family = {spec.key: spec.family for spec in config.primary_panel()}
    survivors = [key for key in family if key not in config.RETIREMENTS]
    assert len(survivors) == 7
    pairs = h3.arm_pairs(survivors, family)
    assert len(pairs["within_family"]) == 1
    assert pairs["cross_family_matched"] == []
    assert len(family_partitions([family[key] for key in survivors])) == 21
    nine = h3.arm_pairs(list(family), family)
    assert len(nine["within_family"]) == 3 and len(nine["cross_family_matched"]) == 12
    assert len(family_partitions(list(family.values()))) == 1260
