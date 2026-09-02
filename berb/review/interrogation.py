"""P2-02: claim-vs-evidence adjudication — the technical-soundness half of
ScholarPeer's Multi-Aspect Q&A Engine (the ablation's single largest
component, -26%).

ScholarPeer's own limitation (per its Fig. 4) is that it prioritizes
external verification over internal logic checks — a competing system beat
it at catching things like mathematically impossible probability ratios.
Berb has an advantage neither PAT nor ScholarPeer has: it owns the
ground-truth experiment run data behind its own claims, in
VerifiedEvidenceRegistry. This module cross-references claim text against
that evidence via an LLM call, for claim types stage 17's numeric-regex
pass (_paper_writing.py's _extract_numeric_claims) cannot classify —
comparative and causal claims, not just bare numbers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from berb.integrity.claims import ClaimRecord, ClaimVerdict
from berb.integrity.registry import VerifiedEvidenceRegistry
from berb.llm.client import LLMClient

logger = logging.getLogger(__name__)

# ScholarPeer: Q&A gains saturate at N_QA=10 probing questions and are
# measurably worse at 15 (context dilution) — not a cost cap, a quality one.
MAX_ADJUDICATED_CLAIMS = 10


@dataclass(frozen=True)
class Verdict:
    claim_id: str
    status: ClaimVerdict
    reasoning: str


_STATUS_MAP = {
    "supported": ClaimVerdict.SUPPORTED,
    "unsupported": ClaimVerdict.UNSUPPORTED,
    "cannot_determine": ClaimVerdict.CANNOT_DETERMINE,
}


def adjudicate_claim(llm: LLMClient, claim: ClaimRecord, evidence_context: str) -> Verdict:
    """Cross-reference a single claim's text against recorded evidence."""
    prompt = (
        "You are auditing a scientific claim against the experiment's own "
        "recorded evidence. Determine whether the claim is SUPPORTED, "
        "UNSUPPORTED, or CANNOT_DETERMINE from the evidence given. Judge "
        "only against the evidence provided below — do not use outside "
        "knowledge about whether the claim is plausible in general.\n\n"
        f"Claim: {claim.text}\n\n"
        f"Evidence recorded from this experiment run:\n{evidence_context}\n\n"
        'Respond with a JSON object: {"status": '
        '"supported"|"unsupported"|"cannot_determine", "reasoning": "..."}'
    )
    try:
        resp = llm.chat([{"role": "user", "content": prompt}], json_mode=True, max_tokens=512)
        parsed = json.loads(resp.content)
        status = _STATUS_MAP.get(
            str(parsed.get("status", "")).lower(), ClaimVerdict.CANNOT_DETERMINE
        )
        return Verdict(
            claim_id=claim.claim_id,
            status=status,
            reasoning=str(parsed.get("reasoning", "")),
        )
    except Exception:  # noqa: BLE001
        logger.debug("Claim adjudication failed for %s", claim.claim_id, exc_info=True)
        return Verdict(
            claim_id=claim.claim_id,
            status=ClaimVerdict.CANNOT_DETERMINE,
            reasoning="adjudication failed",
        )


def adjudicate_claims(
    llm: LLMClient,
    claims: list[ClaimRecord],
    registry: VerifiedEvidenceRegistry,
    *,
    max_claims: int = MAX_ADJUDICATED_CLAIMS,
) -> list[Verdict]:
    """Adjudicate up to *max_claims* not-yet-checked claims against
    *registry*. Claims stage 17 already resolved (SUPPORTED/UNSUPPORTED via
    numeric regex matching) are skipped — this targets the gap: claims the
    regex pass couldn't classify at all.
    """
    to_check = [
        c for c in claims if c.verdict in (ClaimVerdict.NOT_CHECKED, ClaimVerdict.CANNOT_DETERMINE)
    ][:max_claims]
    if not to_check:
        return []
    evidence_lines = [f"- {r.label}: {r.value}" for r in registry.records.values()][:50]
    evidence_context = "\n".join(evidence_lines) if evidence_lines else "(no recorded evidence)"
    return [adjudicate_claim(llm, c, evidence_context) for c in to_check]
