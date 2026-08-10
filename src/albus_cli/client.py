"""Albus SDK client construction from the shell environment."""

import os

import httpx
from albus_sdk import Albus, models

API_KEY_ENV = "ALBUS_API_KEY"
BASE_URL_ENV = "ALBUS_BASE_URL"


class MissingAPIKey(Exception):
    def __init__(self) -> None:
        super().__init__(
            f"{API_KEY_ENV} is not set. Export an Albus API key, e.g. "
            f"`export {API_KEY_ENV}=...`."
        )


def client(base_url: str | None, timeout: float | None) -> Albus:
    """Build an SDK client. A timeout of None disables the read timeout."""
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise MissingAPIKey

    return Albus(
        security=models.Security(api_key_auth=api_key),
        server_url=base_url,
        client=httpx.Client(follow_redirects=True, timeout=timeout),
    )
