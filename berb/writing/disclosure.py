"""AI-usage disclosure statement generator (tasks/ars_integration_plan.md W8.2).

Berb writes papers with LLMs and, until now, emitted no disclosure
statement. Most venues today require one — this is a submission blocker
at many venues, not a nicety.

Design boundary (matches the plan's format_profile precedent): this
module ships the *mechanism* and a *generic* statement template. It never
ships a specific institution's or journal's required wording — that
content is venue-specific, changes over time, and binding it into this
repo would mean carrying stale legal-ish text someone trusts by mistake.
A scholar adapts the generated generic statement to their target venue's
exact policy.

The statement is built from facts Berb can state with actual confidence
— ``config.llm.provider`` / ``primary_model`` (the model driving the
whole run; Berb has no reliable per-stage LLM-usage ledger to draw a
finer-grained claim from) and whether cross-model verification
(tasks/ars_integration_plan.md W5) actually ran. It does not claim
anything Berb cannot back up from its own config.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DisclosureFacts:
    """What this module is willing to assert. Every field must be
    something the run's own config can attest to directly — this is a
    disclosure, not a boilerplate template."""

    provider: str
    model: str
    cross_model_verification_used: bool = False


def generate_disclosure_statement(facts: DisclosureFacts) -> str:
    """Build a generic, factual AI-assistance disclosure statement.

    Pure string builder — no venue-specific policy content, no network,
    no LLM call. The caller is expected to adapt wording to their venue's
    actual required disclosure policy; this is a starting point stating
    only what actually happened in this run.
    """
    lines = [
        "## AI Usage Disclosure",
        "",
        "This manuscript was drafted with the assistance of a large "
        f"language model ({facts.model}, via {facts.provider}) as part of "
        "an automated research pipeline. The AI-generated content was "
        "reviewed and is the responsibility of the authors.",
    ]
    if facts.cross_model_verification_used:
        lines.append("")
        lines.append(
            "An independent, different-provider language model was used "
            "to adversarially cross-check integrity-sensitive claims "
            "(citation support and related checks) in this manuscript."
        )
    lines.append("")
    lines.append(
        "This statement is auto-generated from the pipeline's own "
        "configuration and is a starting point, not a substitute for "
        "the target venue's specific AI-disclosure policy — adapt the "
        "wording to match what your venue actually requires."
    )
    return "\n".join(lines) + "\n"
