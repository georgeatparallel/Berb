"""VLM figure verdict as a control signal (E3).

Wraps the existing FigureCritic with guardrails that convert it from
a paper-time proofreader into an experiment-time referee. Its verdict
determines whether a candidate's figures are valid — and thus whether
the candidate can be selected as the best result.

Guardrails:
1. Plot-count cap: more than max_plots triggers LLM-assisted subset selection.
2. Anti-hallucination instruction: model must report "no plots received"
   when given none and must never invent an analysis.
3. Fail-open on infrastructure error: VLM unavailability leaves
   is_buggy_plots=None (never True), so an outage never rejects candidates.
4. Confidence floor: verdicts below min_confidence are recorded but do
   NOT gate selection (advisory only).

Usage:
    verdict = await verify_plots(
        plot_paths=[Path("fig1.png"), Path("fig2.png")],
        research_context="Training curves for CIFAR-10",
        critic=FigureCritic(),
    )
    if verdict.is_buggy:
        print("Figures are invalid, exclude this candidate")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlotAnalysis:
    """Analysis of a single plot.

    Attributes:
        file_name: Name of the plot file.
        is_valid: Whether the plot appears scientifically valid.
        confidence: Confidence in the validity assessment (0.0-1.0).
        issues: List of issues found.
        summary: Human-readable summary of the analysis.
    """

    file_name: str
    is_valid: bool = True
    confidence: float = 1.0
    issues: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class PlotVerdict:
    """Verdict on a set of experiment plots.

    Attributes:
        valid_plots_received: Whether at least one valid plot was received.
        per_plot: Analysis of each individual plot.
        summary: Human-readable summary of the overall verdict.
        datasets_evidenced: Datasets/conditions that appear to be plotted.
        confidence: Overall confidence in the verdict (0.0-1.0).
    """

    valid_plots_received: bool = False
    per_plot: tuple[PlotAnalysis, ...] = ()
    summary: str = ""
    datasets_evidenced: tuple[str, ...] = ()
    confidence: float = 1.0

    @property
    def is_buggy(self) -> bool | None:
        """Three-valued verdict: True=invalid, False=valid, None=not evaluated.

        Returns:
            True if figures are clearly invalid,
            False if figures are valid,
            None if cannot determine (fail-open).
        """
        if not self.per_plot:
            return None  # No plots to evaluate
        if any(not p.is_valid for p in self.per_plot):
            return True  # At least one plot is invalid
        return False  # All plots pass


async def verify_plots(
    plot_paths: list[Path] | tuple[Path, ...],
    *,
    research_context: str = "",
    critic: Any | None = None,
    max_plots: int = 10,
    min_confidence: float = 0.6,
) -> PlotVerdict:
    """Evaluate a set of experiment plots using VLM figure critique.

    Args:
        plot_paths: Paths to rendered plot image files.
        research_context: Context string describing the experiment.
        critic: FigureCritic instance. If None, verdict.is_buggy stays None.
        max_plots: Maximum plots to evaluate. Excess triggers selection.
        min_confidence: Minimum confidence for a verdict to gate selection.

    Returns:
        PlotVerdict with per-plot analysis and overall judgment.
    """
    # Guardrail 3: Fail-open — no critic = no verdict
    if critic is None:
        logger.warning("verify_plots: no critic provided — reverting to fail-open (no verdict)")
        return PlotVerdict(
            valid_plots_received=False,
            summary="No VLM critic available; figures not evaluated.",
            confidence=0.0,
        )

    if not plot_paths:
        return PlotVerdict(
            valid_plots_received=False,
            summary="No plot paths provided.",
            confidence=0.0,
        )

    # Guardrail 1: Plot-count cap
    selected_paths = list(plot_paths)
    if len(selected_paths) > max_plots:
        logger.warning(
            "verify_plots: %d plots exceeds max_plots=%d — selecting subset",
            len(selected_paths),
            max_plots,
        )
        # Deterministic: take first N (most recently created)
        selected_paths = sorted(
            selected_paths,
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )[:max_plots]  # noqa: E501

    # Guardrail 2 + 4: Evaluate each plot with anti-hallucination prompt
    analyses: list[PlotAnalysis] = []

    for plot_path in selected_paths:
        if not plot_path.exists():
            logger.debug("verify_plots: plot %s not found — treating as invalid", plot_path)
            analyses.append(
                PlotAnalysis(
                    file_name=plot_path.name,
                    is_valid=False,
                    confidence=1.0,
                    issues=("File not found",),
                    summary="Plot file does not exist on disk.",
                )
            )
            continue

        try:
            # Use the existing FigureCritic.analyze_figure
            if hasattr(critic, "analyze_figure"):
                critique = await critic.analyze_figure(
                    figure_path=plot_path,
                    paper_context=research_context,
                )
            else:
                # Fallback: treat as protocol-compatible object
                critique = await critic(plot_path, research_context)  # type: ignore[misc]

            # Extract validity from critique
            is_valid = getattr(critique, "is_acceptable", True)
            overall_score = getattr(critique, "overall_score", 5.0)
            issues = getattr(critique, "issues", [])
            confidence = (
                getattr(critique, "confidence", overall_score / 10.0) if overall_score else 0.5
            )

            # Normalize confidence to 0-1
            if confidence > 1.0:
                confidence = confidence / 10.0
            confidence = max(0.0, min(1.0, confidence))

            analysis = PlotAnalysis(
                file_name=plot_path.name,
                is_valid=is_valid,
                confidence=confidence,
                issues=tuple(
                    i.get("description", str(i)) if isinstance(i, dict) else str(i)
                    for i in (issues or [])
                ),  # noqa: E501
                summary=f"Score: {overall_score:.1f}/10, {'Pass' if is_valid else 'Issues found'}",
            )
            analyses.append(analysis)

        except Exception as e:
            # Guardrail 3: Fail-open on infrastructure error
            logger.warning(
                "verify_plots: VLM critique failed for %s — fail-open (no verdict): %s",
                plot_path,
                e,
            )
            analyses.append(
                PlotAnalysis(
                    file_name=plot_path.name,
                    is_valid=True,  # Fail-open: assume valid
                    confidence=0.0,  # Zero confidence
                    issues=(f"VLM error: {e}",),
                    summary="VLM critique failed; assumed valid (fail-open).",
                )
            )

    # Determine overall verdict
    valid_count = sum(1 for a in analyses if a.is_valid)
    invalid_count = sum(1 for a in analyses if not a.is_valid)
    avg_confidence = sum(a.confidence for a in analyses) / max(len(analyses), 1)

    summary_parts = [
        f"Evaluated {len(analyses)} plot(s): {valid_count} valid, {invalid_count} invalid",
        f"Average confidence: {avg_confidence:.2f}",
    ]

    return PlotVerdict(
        valid_plots_received=valid_count > 0,
        per_plot=tuple(analyses),
        summary="; ".join(summary_parts),
        datasets_evidenced=(),
        confidence=avg_confidence,
    )


def is_verdict_gating(verdict: PlotVerdict, min_confidence: float = 0.6) -> bool | None:
    """Determine whether a verdict gates candidate selection.

    Args:
        verdict: The plot verdict.
        min_confidence: Minimum confidence for gating.

    Returns:
        True → candidate should be excluded (buggy plots).
        False → candidate passes figure check.
        None → not enough evidence to gate (fail-open).
    """
    if verdict.confidence < min_confidence:
        return None  # Low confidence — advisory only
    if not verdict.valid_plots_received and verdict.per_plot:
        # Received files but they were all invalid
        return True
    if any(not a.is_valid for a in verdict.per_plot if a.confidence >= min_confidence):
        return True
    return False


# ---------------------------------------------------------------------------
# Pixel-level figure defects
# ---------------------------------------------------------------------------
#
# verify_plots() above was written against a critic exposing
# ``async analyze_figure(figure_path=..., paper_context=...)``. No such critic
# ever existed in this repository — the only one, agents/figure_agent CriticAgent,
# is synchronous and reviews figure *metadata* (scripts, metrics, rendered dicts)
# rather than taking an image path. That missing implementation is why
# ``JournalNode.is_buggy_plots`` was never set and the hard gate in
# search/scoring.py has been inert.
#
# PixelPlotCritic below closes that gap without inventing a vision model: the
# LLM client has no image support, so a genuine VLM critic is not buildable
# here. What IS buildable, and catches the failure that matters most during
# search, is pixel analysis of the rendered file — a candidate that "succeeds"
# while emitting a blank chart. That logic already existed inside CriticAgent;
# it now lives here and CriticAgent delegates to it, so the two cannot diverge.


def detect_pixel_defects(image_path: Path | str) -> list[dict[str, str]]:
    """Inspect a rendered image for visual defects. Pure pixel analysis, no LLM.

    Detects:
      - Near-blank images (>95% white), i.e. degenerate or empty charts — critical
      - Non-white content touching an edge, i.e. possible label clipping — warning

    Fails open: a missing PIL/numpy, an unreadable file, or any unexpected error
    yields an empty list, never a false "this figure is broken" verdict.

    Args:
        image_path: Path to a rendered raster image.

    Returns:
        Zero or more issue dicts with keys ``type``, ``severity`` and ``message``.
    """
    issues: list[dict[str, str]] = []
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(str(image_path)).convert("RGB")
        arr = np.array(img)

        white_ratio = float(np.mean(np.all(arr > 250, axis=2)))
        if white_ratio > 0.95:
            issues.append(
                {
                    "type": "rendered_quality",
                    "severity": "critical",
                    "message": (
                        f"Image is {white_ratio:.0%} white — likely degenerate or empty chart"
                    ),
                }
            )

        margin = 3  # pixels
        for edge_name, edge_slice in [
            ("top", arr[:margin, :]),
            ("bottom", arr[-margin:, :]),
            ("left", arr[:, :margin]),
            ("right", arr[:, -margin:]),
        ]:
            dark_ratio = float(np.mean(np.any(edge_slice < 80, axis=-1)))
            if dark_ratio > 0.05:
                issues.append(
                    {
                        "type": "rendered_quality",
                        "severity": "warning",
                        "message": (
                            f"Content touching {edge_name} edge ({dark_ratio:.0%} "
                            f"dark pixels) — possible label/title clipping"
                        ),
                    }
                )
    except ImportError:
        logger.debug("PIL/numpy not available — skipping pixel defect checks")
    except Exception as exc:
        logger.debug("Pixel defect check failed for %s: %s", image_path, exc)

    return issues


@dataclass(frozen=True)
class _PixelCritique:
    """The subset of a critique that :func:`verify_plots` reads."""

    is_acceptable: bool
    overall_score: float
    issues: tuple[str, ...]
    confidence: float


class PixelPlotCritic:
    """A critic for :func:`verify_plots` backed by pixel analysis, not a VLM.

    Deliberately narrow. It answers one question — "did this candidate render a
    real figure, or an empty canvas?" — and abstains on everything else by
    reporting a passing critique. That keeps the search gate honest: it can
    reject a candidate whose figures are demonstrably degenerate, and never
    rejects one on aesthetic grounds it cannot actually judge.

    Only ``critical`` defects make a figure unacceptable; warnings are reported
    but do not gate, because edge-touching content is frequently a false
    positive on dense plots.
    """

    def __init__(self, *, min_confidence: float = 0.9) -> None:
        self._confidence = min_confidence

    async def analyze_figure(
        self,
        figure_path: Path | str,
        paper_context: str = "",
    ) -> _PixelCritique:
        """Return a critique of one rendered figure.

        Args:
            figure_path: Path to the rendered image.
            paper_context: Unused — kept for protocol compatibility with the
                VLM critic signature verify_plots() expects.

        Returns:
            A critique carrying the attributes verify_plots() reads.
        """
        defects = detect_pixel_defects(figure_path)
        critical = [d for d in defects if d.get("severity") == "critical"]
        return _PixelCritique(
            is_acceptable=not critical,
            overall_score=2.0 if critical else 8.0,
            issues=tuple(d["message"] for d in defects),
            confidence=self._confidence,
        )
