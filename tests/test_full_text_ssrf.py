"""S0-6 (tasks/arch_hardening_plan.md): SSRF guard for full-text extraction.

Never had its own acceptance test when it shipped — this file is that test,
added per S-8 (tasks/hardening_plan_2026-08-13.md). Covers both halves of
the original spec: a direct fetch of a blocked address is refused, AND a
URL that redirects to a blocked address is refused (the actual bypass the
guard exists to close — an allowlisted host redirecting to
169.254.169.254 cloud metadata).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from berb.literature.full_text import FullTextExtractor


class TestSSRFGuard:
    def test_direct_fetch_of_metadata_ip_is_blocked(self):
        extractor = FullTextExtractor()
        result = asyncio.run(
            extractor.extract("http://169.254.169.254/latest/meta-data/")
        )

        assert result.success is False
        assert "ssrf" in (result.error or "").lower()

    def test_direct_fetch_of_loopback_is_blocked(self):
        extractor = FullTextExtractor()
        result = asyncio.run(extractor.extract("http://127.0.0.1:8080/secrets"))

        assert result.success is False
        assert "ssrf" in (result.error or "").lower()

    def test_redirect_to_metadata_ip_is_blocked(self):
        """The actual bypass: an allowlisted host's response redirects to a
        blocked address. follow_redirects=False means _extract_basic must
        re-check the Location header itself before following it."""
        extractor = FullTextExtractor()

        redirect_response = MagicMock()
        redirect_response.is_redirect = True
        redirect_response.headers = {
            "location": "http://169.254.169.254/latest/meta-data/"
        }

        fake_client = MagicMock()
        fake_client.get = AsyncMock(return_value=redirect_response)
        extractor._http_client = fake_client

        # First hop (the original URL) passes the SSRF check; the second
        # (redirect target) does not — this is what the loop must catch.
        with patch(
            "berb.literature.full_text.check_url_ssrf",
            side_effect=[None, "Blocked internal/private URL: 169.254.169.254"],
        ):
            result = asyncio.run(
                extractor._extract_basic("https://allowlisted.example.com/paper")
            )

        assert result.success is False
        assert "ssrf" in (result.error or "").lower()
        # Only the first hop was actually fetched — the redirect target
        # never reached http_client.get() because the SSRF check on it
        # failed first.
        assert fake_client.get.call_count == 1
