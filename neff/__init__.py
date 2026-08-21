"""Correlated Minds: measuring effective independence across an LLM panel.

Importing the package loads `.env` so that every entrypoint -- neff.verify,
neff.collect, the analysis helpers -- sees the API keys the setup instructions
told you to put there. Real env vars take precedence; see neff/env.py.
"""

from .env import load_env

load_env()
