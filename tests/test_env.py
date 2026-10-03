"""The `.env` -> os.environ path, which SETUP.md depends on.

Found in the audit: nothing loaded `.env`, so `preflight.py` (which reads the
file from disk) reported all four keys present while `neff.verify` (which reads
os.environ) failed immediately. These tests pin the contract so the two agree.
"""

import os

from neff.env import load_env


def _write(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text)
    return p


class TestLoadEnv:
    def test_loads_plain_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert load_env(_write(tmp_path, "ANTHROPIC_API_KEY=sk-ant-123\n")) == 1
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-123"

    def test_real_env_wins(self, tmp_path, monkeypatch):
        """CI secrets must never be overridden by a stale file on disk."""
        monkeypatch.setenv("OPENAI_API_KEY", "from-ci")
        load_env(_write(tmp_path, "OPENAI_API_KEY=from-file\n"))
        assert os.environ["OPENAI_API_KEY"] == "from-ci"

    def test_tolerates_quotes_export_comments_and_blanks(self, tmp_path, monkeypatch):
        for k in ("GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
            monkeypatch.delenv(k, raising=False)
        n = load_env(_write(tmp_path, """
# a comment
export GOOGLE_API_KEY="quoted-value"

OPENROUTER_API_KEY = 'spaced-and-quoted'
MALFORMED_NO_EQUALS
"""))
        assert n == 2
        assert os.environ["GOOGLE_API_KEY"] == "quoted-value"
        assert os.environ["OPENROUTER_API_KEY"] == "spaced-and-quoted"

    def test_empty_value_is_not_set(self, tmp_path, monkeypatch):
        """`.env.example` ships with empty values; copying it must not create
        an empty key that then fails deep inside a provider call."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert load_env(_write(tmp_path, "ANTHROPIC_API_KEY=\n")) == 0
        assert "ANTHROPIC_API_KEY" not in os.environ

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert load_env(tmp_path / "nope.env") == 0
