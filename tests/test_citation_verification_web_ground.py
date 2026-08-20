# pyright: reportPrivateUsage=false
"""Tests for CitationVerifier's Layer 5 (Perplexity web-grounding check).

Layer 5 answers a different question than Layer 4: does this citation
exist and get corroborated by live web search, vs. does it support this
specific claim. See berb/pipeline/citation_verification.py.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from berb.pipeline.citation_verification import (
    CitationVerifier,
    VerificationLayer,
    VerifierConfig,
)


class TestWebGroundLayerNoOp:
    """No PERPLEXITY_API_KEY configured — Layer 5 must no-op, not fail."""

    @pytest.mark.asyncio
    async def test_no_api_key_skips_layer_silently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
            enable_web_check=True,
        )
        verifier = CitationVerifier(config)

        result = await verifier.verify({"doi": "10.1038/s41586-021-03819-2"})

        assert VerificationLayer.WEB_GROUND not in result.layers_passed
        assert VerificationLayer.WEB_GROUND not in result.layers_failed

    @pytest.mark.asyncio
    async def test_disabled_flag_skips_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PERPLEXITY_API_KEY", "fake-key")
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
            enable_web_check=False,
        )
        verifier = CitationVerifier(config)

        result = await verifier.verify({"doi": "10.1038/s41586-021-03819-2"})

        assert VerificationLayer.WEB_GROUND not in result.layers_passed
        assert VerificationLayer.WEB_GROUND not in result.layers_failed


class TestWebGroundLayerWithKey:
    """PERPLEXITY_API_KEY configured — Layer 5 should actually run."""

    def _config(self, api_key: str = "fake-key") -> VerifierConfig:
        return VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
            enable_web_check=True,
            perplexity_api_key=api_key,
        )

    @pytest.mark.asyncio
    async def test_verified_passes_layer(self) -> None:
        verifier = CitationVerifier(self._config())

        with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_client_cls:
            mock_client_cls.return_value.verify_citation.return_value = {
                "status": "verified",
                "evidence": "Confirmed via search.",
                "citations": [],
            }
            result = await verifier.verify(
                {"doi": "10.1038/s41586-021-03819-2", "title": "Real Paper"}
            )

        assert VerificationLayer.WEB_GROUND in result.layers_passed
        assert VerificationLayer.WEB_GROUND not in result.layers_failed

    @pytest.mark.asyncio
    async def test_inaccurate_fails_layer_with_error(self) -> None:
        verifier = CitationVerifier(self._config())

        with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_client_cls:
            mock_client_cls.return_value.verify_citation.return_value = {
                "status": "inaccurate",
                "evidence": "Paper exists but finding is misrepresented.",
                "citations": [],
            }
            result = await verifier.verify(
                {"doi": "10.1038/s41586-021-03819-2", "title": "Misrepresented Paper"}
            )

        assert VerificationLayer.WEB_GROUND in result.layers_failed
        assert any("inaccurate" in e.lower() for e in result.errors)

    @pytest.mark.asyncio
    async def test_unverified_fails_layer_with_warning_not_error(self) -> None:
        verifier = CitationVerifier(self._config())

        with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_client_cls:
            mock_client_cls.return_value.verify_citation.return_value = {
                "status": "unverified",
                "evidence": "Could not find corroborating sources.",
                "citations": [],
            }
            result = await verifier.verify(
                {"doi": "10.1038/s41586-021-03819-2", "title": "Obscure Paper"}
            )

        assert VerificationLayer.WEB_GROUND in result.layers_failed
        assert not any("inaccurate" in e.lower() for e in result.errors)
        assert any("could not verify" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_client_exception_no_ops_gracefully(self) -> None:
        """A Perplexity API failure shouldn't crash verify() or count against
        the citation — matches the no-op-on-missing-key behavior."""
        verifier = CitationVerifier(self._config())

        with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_client_cls:
            mock_client_cls.return_value.verify_citation.side_effect = RuntimeError(
                "API down"
            )
            result = await verifier.verify(
                {"doi": "10.1038/s41586-021-03819-2", "title": "Some Paper"}
            )

        assert VerificationLayer.WEB_GROUND not in result.layers_passed
        assert VerificationLayer.WEB_GROUND not in result.layers_failed


class TestIsValidToleranceScaling:
    """is_valid's failure tolerance should scale with enabled layer count,
    not stay hardcoded at "allow 1 failure" as layers grow from 4 to 5."""

    @pytest.mark.asyncio
    async def test_four_layers_matches_original_tolerance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With Layer 5 disabled, behavior must match the pre-Layer-5 system:
        format passes + at most 1 other layer fails => valid."""
        monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=True,
            enable_info_check=False,
            enable_content_check=False,
            enable_web_check=False,
        )
        verifier = CitationVerifier(config)

        with patch.object(verifier, "_check_api", return_value=None):
            result = await verifier.verify({"doi": "10.1038/s41586-021-03819-2"})

        assert VerificationLayer.FORMAT in result.layers_passed
        assert VerificationLayer.API in result.layers_failed
        assert result.is_valid is True  # 1 failure out of 2 enabled layers

    @pytest.mark.asyncio
    async def test_format_failure_always_invalid(self) -> None:
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=False,
            enable_info_check=False,
            enable_content_check=False,
            enable_web_check=False,
        )
        verifier = CitationVerifier(config)

        result = await verifier.verify({"doi": "not-a-real-doi"})

        assert VerificationLayer.FORMAT in result.layers_failed
        assert result.is_valid is False
