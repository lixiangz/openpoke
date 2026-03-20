"""Shared test configuration and safety fixtures."""

import pytest
import httpx


@pytest.fixture(autouse=True)
def block_network_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that attempts a real HTTP call.

    All LLM and external API calls route through httpx.AsyncClient.post.
    Patching it here ensures no test can accidentally trigger a billable
    request — tests must mock at the service layer instead.
    """

    async def _guard(self: httpx.AsyncClient, url: str, **kwargs: object) -> None:
        raise AssertionError(
            f"Test attempted a network request to {url!r}. "
            "Mock the relevant service function instead of letting the call reach the network."
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", _guard)
