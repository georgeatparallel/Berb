"""P2-03: diff experiment-design baselines against methods named in the
retrieved literature corpus, to catch SOTA comparisons the plan omitted.

No omitted-baseline detector existed before this — the nearest things were
reviewer prompt text asking for "missing baselines" and a zero-baseline-run
detector, neither of which cross-references the literature actually
retrieved. Nothing asked "did we compare against what we cited?"
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

# Common ML paper title convention: "MethodName: Descriptive Subtitle"
# (BERT, ResNet, CLIP, LLaMA, ViT, ...). Titles without a colon-prefixed
# name are skipped — deliberately conservative. No NLP/NER is available in
# this codebase, and scanning every capitalized word in a title produces
# far too many false positives from ordinary prose.
_LEADING_METHOD_NAME_RE = re.compile(r"^([A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*)\s*:")
_STOPWORDS = frozenset({"A", "An", "The", "We", "This", "Towards", "On", "Note"})


def extract_corpus_method_names(titles: Sequence[str]) -> tuple[str, ...]:
    """Heuristically extract method names from a list of paper titles.

    Returns names in first-seen order, deduplicated case-insensitively.
    """
    names: list[str] = []
    seen: set[str] = set()
    for title in titles:
        m = _LEADING_METHOD_NAME_RE.match(title.strip())
        if not m:
            continue
        name = m.group(1)
        if name in _STOPWORDS or len(name) <= 2:
            continue
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return tuple(names)


@dataclass(frozen=True)
class OmittedBaselines:
    missing: tuple[str, ...]
    corpus_size: int

    def to_dict(self) -> dict[str, object]:
        return {"missing": list(self.missing), "corpus_size": self.corpus_size}


def find_omitted_baselines(
    planned: Sequence[str], corpus_methods: Sequence[str]
) -> OmittedBaselines:
    """Diff *planned* experiment baselines against *corpus_methods* — method
    names extracted from the paper's own retrieved literature corpus via
    :func:`extract_corpus_method_names`.

    A method counts as covered if its name appears as a substring (case
    insensitive) of any planned baseline string — "resnet50" in the plan
    matches a corpus method named "ResNet".
    """
    planned_blob = " ".join(planned).lower()
    missing = tuple(m for m in corpus_methods if m.lower() not in planned_blob)
    return OmittedBaselines(missing=missing, corpus_size=len(corpus_methods))
