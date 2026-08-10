"""Unit tests for berb.review.interrogation (P2-02).

The technical-soundness half of ScholarPeer's Q&A engine — ScholarPeer's
own stated weak spot (external verification prioritized over internal
logic checks) is exactly what this targets, using evidence Berb owns that
neither PAT nor ScholarPeer has access to: the actual experiment run data.
"""

from __future__ import annotations

import json

from berb.integrity.claims import ClaimRecord, ClaimType, ClaimVerdict
from berb.integrity.evidence import EvidenceRecord, EvidenceSource, EvidenceType, make_evidence_id
from berb.integrity.registry import VerifiedEvidenceRegistry
from berb.llm.client import LLMResponse
from berb.review.interrogation import (
    MAX_ADJUDICATED_CLAIMS,
    Verdict,
    adjudicate_claim,
    adjudicate_claims,
)


class _FakeLLM:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[list[dict]] = []

    def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append(messages)
        return LLMResponse(content=self.response_text, model="fake")


def _claim(claim_id: str, verdict: ClaimVerdict = ClaimVerdict.NOT_CHECKED) -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        text=f"Claim {claim_id}: our method outperforms the baseline.",
        claim_type=ClaimType.COMPARATIVE,
        verdict=verdict,
    )


class TestAdjudicateClaim:
    def test_supported_verdict_parsed(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "supported", "reasoning": "matches evidence"}))
        result = adjudicate_claim(llm, _claim("c1"), "- accuracy: 0.95")
        assert result == Verdict(claim_id="c1", status=ClaimVerdict.SUPPORTED, reasoning="matches evidence")

    def test_unsupported_verdict_parsed(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "unsupported", "reasoning": "no such evidence"}))
        result = adjudicate_claim(llm, _claim("c1"), "- accuracy: 0.50")
        assert result.status == ClaimVerdict.UNSUPPORTED

    def test_unknown_status_defaults_to_cannot_determine(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "maybe", "reasoning": "unclear"}))
        result = adjudicate_claim(llm, _claim("c1"), "")
        assert result.status == ClaimVerdict.CANNOT_DETERMINE

    def test_malformed_response_does_not_raise(self) -> None:
        llm = _FakeLLM("not valid json")
        result = adjudicate_claim(llm, _claim("c1"), "")
        assert result.status == ClaimVerdict.CANNOT_DETERMINE
        assert result.claim_id == "c1"

    def test_llm_exception_does_not_raise(self) -> None:
        class _BrokenLLM:
            def chat(self, messages, **kwargs):  # noqa: ANN001, ANN003
                raise RuntimeError("unavailable")

        result = adjudicate_claim(_BrokenLLM(), _claim("c1"), "")
        assert result.status == ClaimVerdict.CANNOT_DETERMINE


class TestAdjudicateClaims:
    def test_skips_already_resolved_claims(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "supported", "reasoning": "ok"}))
        claims = [_claim("c1", ClaimVerdict.SUPPORTED), _claim("c2", ClaimVerdict.UNSUPPORTED)]
        registry = VerifiedEvidenceRegistry()

        verdicts = adjudicate_claims(llm, claims, registry)

        assert verdicts == []
        assert llm.calls == []

    def test_adjudicates_not_checked_claims(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "supported", "reasoning": "ok"}))
        claims = [_claim("c1", ClaimVerdict.NOT_CHECKED)]
        registry = VerifiedEvidenceRegistry()
        registry.add_record(
            EvidenceRecord(
                evidence_id=make_evidence_id(),
                evidence_type=EvidenceType.METRIC,
                value=0.95,
                source=EvidenceSource(stage=14, artifact_path="experiment_summary.json"),
                label="accuracy",
            )
        )

        verdicts = adjudicate_claims(llm, claims, registry)

        assert len(verdicts) == 1
        assert verdicts[0].claim_id == "c1"
        assert "accuracy" in llm.calls[0][-1]["content"]

    def test_caps_at_max_adjudicated_claims(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "supported", "reasoning": "ok"}))
        claims = [_claim(f"c{i}") for i in range(MAX_ADJUDICATED_CLAIMS + 5)]
        registry = VerifiedEvidenceRegistry()

        verdicts = adjudicate_claims(llm, claims, registry)

        assert len(verdicts) == MAX_ADJUDICATED_CLAIMS

    def test_empty_claims_no_llm_calls(self) -> None:
        llm = _FakeLLM(json.dumps({"status": "supported", "reasoning": "ok"}))
        verdicts = adjudicate_claims(llm, [], VerifiedEvidenceRegistry())
        assert verdicts == []
        assert llm.calls == []
