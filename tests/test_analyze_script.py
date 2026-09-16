"""scripts/analyze.py composes every registered analysis, and no test ran it until 2026-09-14."""

import importlib.util
import json
from pathlib import Path

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
