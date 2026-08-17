"""Shared HTTP client with retry, backoff, and honest failure.

Every external source in this project is a free public API. Free public APIs
rate-limit, go down, and occasionally return a 200 with a challenge page in the
body instead of data (Stooq does exactly this). So:

  - retry on transient status codes with exponential backoff
  - never retry on 4xx that will never succeed (400, 401, 403, 404)
  - verify the body looks like what we asked for, not just the status code
"""

import time
from typing import Any, Dict, Optional

import httpx

from ..config import USER_AGENT

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched after retries."""


def get_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    max_attempts: int = 4,
    backoff_base: float = 1.5,
) -> Any:
    """GET a URL and parse JSON, with retries.

    Raises FetchError rather than returning a sentinel, because a silently empty
    result on a collection day is indistinguishable from "nothing happened" and
    would quietly put a hole in the panel.
    """
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        merged.update(headers)

    last_error = ""
    for attempt in range(max_attempts):
        try:
            response = httpx.get(
                url, params=params, headers=merged, timeout=timeout, follow_redirects=True
            )
        except httpx.RequestError as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    # 200 with a non-JSON body: a challenge page, an HTML error,
                    # or a maintenance notice. Treat as failure, not as data.
                    snippet = response.text[:160].replace("\n", " ")
                    last_error = f"200 but body was not JSON: {snippet!r}"
            elif response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
            else:
                raise FetchError(
                    f"{url} -> HTTP {response.status_code} (not retryable): "
                    f"{response.text[:200]}"
                )

        if attempt < max_attempts - 1:
            time.sleep(backoff_base ** attempt)

    raise FetchError(f"{url} failed after {max_attempts} attempts: {last_error}")


def get_text(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
    max_attempts: int = 3,
) -> str:
    """GET a URL and return the body as text (for CSV downloads)."""
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)

    last_error = ""
    for attempt in range(max_attempts):
        try:
            response = httpx.get(
                url, params=params, headers=merged, timeout=timeout, follow_redirects=True
            )
        except httpx.RequestError as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code == 200:
                return response.text
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
            else:
                raise FetchError(f"{url} -> HTTP {response.status_code} (not retryable)")

        if attempt < max_attempts - 1:
            time.sleep(1.5 ** attempt)

    raise FetchError(f"{url} failed after {max_attempts} attempts: {last_error}")
