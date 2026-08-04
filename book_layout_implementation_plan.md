# Berb — 17×24 cm Book Layout Implementation Plan

**Document ID:** BERB-IP-002
**Version:** 1.0
**Date:** 2026-07-21
**Status:** Draft for review
**Scope:** New book-format output target — 17×24 cm, **Greek (monotonic)**, New Computer Modern Book 9/14.173 bp, 5 mm indent, flush full-width

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Specification Analysis](#2-specification-analysis)
3. [Typographic Assessment](#3-typographic-assessment)
4. [Current Architecture — What Breaks](#4-current-architecture--what-breaks)
5. [Target Architecture](#5-target-architecture)
6. [The Derived Type Scale](#6-the-derived-type-scale)
7. [Reference Implementation](#7-reference-implementation) — class, fonts, Greek, flush rules, justification
8. [Implementation Plan & WBS](#8-implementation-plan--wbs)
9. [Suggested Additional Changes](#9-suggested-additional-changes)
10. [Risk Matrix](#10-risk-matrix)
11. [Validation & QA Strategy](#11-validation--qa-strategy)
12. [Acceptance Checklist](#12-acceptance-checklist)
- [Appendix A — Typeface Selection Research](#appendix-a--typeface-selection-research)

---

> **Revision 1.3 (2026-07-21) — decisions locked**
>
> 1. **Paragraphs indent 5 mm; no paragraph spacing.** First paragraph after a heading is not indented. Supersedes the `\parskip` decision in §2.3 and **resolves M-9 entirely** — see §2.3a.
> 2. **The body text is Greek, monotonic.** This re-ranked the entire typeface field and invalidated rev 1's Latin-driven recommendation. Appendix A is rewritten from measured glyph-coverage and metric data. Greek adds hard requirements to hyphenation, punctuation, math-Greek disambiguation, and the sans/mono companions — see §7.3, A.7, A.8.
> 3. **Typeface decided: New Computer Modern Book, 08 optical size.** OFL, matched `NewCMMath-Book`, full monotonic + polytonic Greek, installed locally and on Overleaf. **Closes blocker B-3 and risk R-01**; deletes the Caladea fallback chain (−1.5 d).
> 4. **Effort revised to 20 engineer-days** (+2 for Greek: WBS 2.6, 2.7, 4.4, 6.5; −1.5 from the deleted fallback work).
>
> **Three decisions remain open:** §2.2 (running heads), §2.3 (list-hang variant), §11.2 (9 pt confirmation after the Greek measure test).

---

## 1. Executive Summary

### 1.1 What was requested

A book-format output for a **Greek-language book with mathematics**: 170 × 240 mm trim, 9 pt body on 14.173 pt leading, mirrored margins (top 20 / bottom 30 / inside 25 / outside 20 mm), all text flush to the outside margin at full measure, with every other size derived from the 9 pt body.

### 1.2 Three blockers found in the codebase

These are not risks — they are hard blocks. Each must be resolved before a single page renders correctly.

**B-1 — The compiler cannot use an OpenType text font.**
`compiler.py:807` hardcodes `["pdflatex", "-interaction=nonstopmode", tex_name]`. NewCM (like Cambria) is OpenType, and Greek text plus `unicode-math` require a Unicode engine; pdfLaTeX cannot do this. This requires XeLaTeX or LuaLaTeX with `fontspec`. **Engine selection must be added to the compiler**, and the pdfLaTeX-specific fixup routines (`inputenc`/`fontenc`/T2A injection, `compiler.py:718-760`) must be *disabled* under Unicode engines — loading `inputenc` alongside `fontspec` is an error, not a no-op.

**B-2 — `14.173pt` is not the leading you want; `14.173bp` is.**
14.173 in PostScript points (bp, 1/72″ — what InDesign calls "points") is exactly 5.000 mm. LaTeX's `pt` is 1/72.27″, so `14.173pt` = 4.981 mm. That 0.019 mm/line error accumulates to **0.71 mm over a 38-line page** — enough to visibly break a baseline grid across a spread. The spec value is almost certainly InDesign-derived. **Write it as `14.173bp` or `5mm`.**

**B-3 — ~~Cambria is proprietary and cannot ship in an Overleaf export.~~ CLOSED.**
The original spec named Cambria, which is licensed with Windows/Office, is absent from Overleaf, and whose only metric-compatible substitute (Caladea) has **no math companion** — forcing Caladea text against Times-flavoured STIX Two Math on every equation.

> **Resolved by decision, not by mitigation: the typeface is now New Computer Modern Book.**
> NewCM is OFL, on CTAN, installed locally, and present on Overleaf. It carries full monotonic *and* polytonic Greek, and ships a matched OpenType MATH companion drawn in the same weight. This deletes the Caladea fallback chain, the metric-compatibility CI double-compile, the licensing manifest, and the text/math mismatch — **~1.5 days removed**.
> Set from the **08 optical size**, which is drawn for 8 pt rather than scaled from 10 pt: sturdier stems and 6 % wider Greek, which helps both 9 pt legibility and the long measure. Full comparison and measured data in **Appendix A**.

### 1.3 The good news

The spec is internally coherent and the numbers are clean:

- Text block = 170 − 25 − 20 = **125 mm wide**; 240 − 20 − 30 = **190 mm tall**.
- 190 mm ÷ 5 mm = **exactly 38 lines**. This is a deliberate baseline grid, and it works.
- Leading:body ratio = 14.226 pt / 9 pt = **1.58** — unusually generous, and correctly so, because it compensates for a wide measure (§3.1).

Whoever wrote this spec knew what they were doing. The plan below preserves that intent rather than second-guessing it.

### 1.4 Scope reality

Berb currently emits **conference papers only** — NeurIPS/ICLR/ICML, A4/Letter, one- or two-column, via `berb/templates/conference.py` and `converter.py`. There is no book target, no `\geometry` control, no mirrored margins, no engine choice.

This is **a new output target added alongside the existing ones**, not a modification of them. Existing conference templates must remain byte-identical in output.

**Estimated effort: 15–18 engineer-days.** Roughly half is the layout itself; the other half is the downstream figure-pipeline breakage (§4.3), which is the part most likely to be underestimated.

---

## 2. Specification Analysis

### 2.1 Resolved values

| Parameter | Given | Resolved | Note |
|---|---|---|---|
| Trim size | 17 × 24 cm | 170 × 240 mm = **481.890 × 680.315 bp** | Validate against PDF MediaBox |
| Leading | 14.173 pt | **14.173 bp = 5.000 mm = 14.2261 TeX pt** | See B-2 |
| Body font | Cambria | **NewCM08-Book** (decided) — no fallback | See A.5, B-3 closed |
| Body size | 9 pt | 9 pt | LaTeX `pt`; ratio to leading 1.58 |
| Margins | T20 / B30 / I25 / O20 mm | as given, **mirrored** (`twoside`) | Inside > outside = binding-aware ✓ |
| Text block | derived | **125 × 190 mm** | 38 lines exactly |
| Type area ratio | derived | **58.2%** of page | Dense; typical books are 45–55% |

### 2.2 Open decision — "top margin" measured to what?

`geometry` measures `top` to the top of the **header** when `includehead` is set, and to the top of the **text block** otherwise (the default).

- **Option A (recommended):** margins measured to the type area. Running head, if any, sits *inside* the 20 mm top margin, so visible white above the head is < 20 mm.
- **Option B:** `includehead` — the 20 mm contains head + gap + text, shrinking the type area below 190 mm and **breaking the 38-line grid**.

**Recommendation: Option A, and omit running heads entirely.** Use a folio in the bottom margin only (30 mm is ample). This honours "top: 2 cm" literally, keeps the grid exact, and suits the flush/minimal aesthetic the rest of the spec implies. Running heads can be added later as a config flag.

### 2.3 Open decision — "start from the outside margin"

This phrase has three possible readings. The distinction matters and cannot be resolved from the spec alone.

**Reading 1 — Literal directional.** Text begins at the outside edge: right-aligned on recto pages, left-aligned on verso. This is not sensible for left-to-right text and produces an unreadable book. **Rejected.**

**Reading 2 — Full measure, zero indentation *(recommended)*.** Every block-level element begins flush at the type-area edge and spans the full 125 mm. No first-line indent, no list indent, no quote indent, no centred display math, no centred captions, no bibliography hang. On a verso page that edge *is* the outside margin, which is almost certainly the mental model behind the phrasing.

**Reading 3 — Marginalia layout.** Body text starts at the outside margin with a marginal column reserved. **Rejected** — the outside margin here (20 mm) is *narrower* than the inside (25 mm), so there is no room for marginalia. The asymmetry is binding compensation, not a side column.

**Proceeding with Reading 2**, as amended by §2.3a. Every consequence is enumerated in §7.3.

**Sub-decision — list wrapping.** Under the strict rule, wrapped list lines return flush to the margin (`leftmargin=0pt`), losing the hanging indent that normally aids scanning. Both variants are implemented in §7.3; strict is the default, `layout.list_hang=true` restores the hang.

### 2.3a Paragraph model *(amended — supersedes the `\parskip` decision above)*

| Rule | Value |
|---|---|
| First-line indent | **5 mm** |
| Paragraph spacing | **0** |
| First paragraph after a heading | **not indented** |

This is the classical book paragraph model, and it is the right call. Three consequences:

**1. It resolves M-9 completely.** The earlier plan was forced into `\parskip = 1 line` because zero indent left no other way to separate paragraphs, costing ~20% of each page. Indent-based separation costs **zero vertical space**. The grid is now preserved *by construction* — with `\parskip = 0`, there is no inter-paragraph space left to quantise, so paragraphs can never knock the text off the baseline grid. This is strictly better than the previous design on every axis.

**2. It narrows the flush rule.** The amended rule reads:

> All **block-level elements** are flush at the type-area edge and span the full 125 mm measure. Within running text, **paragraph first lines indent 5 mm**, except immediately after a heading.

Lists, captions, block quotes, display math, footnotes, bibliography entries, figures and tables remain flush — §2.3 Reading 2 still governs them. Only the paragraph first line is exempted.

**3. The indent size is well chosen.** 5 mm at 9 pt is **1.57 em**. The classical range is 1–2 em, with the upper end preferred at long measures — and 125 mm is a long measure (§3.1). 5 mm also happens to equal one leading unit, which is a traditional indent rule and makes the value easy to reason about. No change recommended.

**Implementation note — no package needed.** LaTeX's *default* behaviour is to suppress the indent on the first paragraph after a sectioning command. The requirement is met by **not** loading the `indentfirst` package, and by using `titlesec`'s **starred** `\titlespacing*` (the star is what suppresses the following indent). The reference implementation in §7.3 already uses the starred form. The failure mode here is silent: loading `indentfirst`, or dropping the star, produces an indent that most readers will not consciously notice but that reads as subtly wrong.

**Open sub-decision — indent after displayed material.** After a display equation, list, or block quote, LaTeX indents the following paragraph only if the source has a blank line before it. Two conventions:

- *(recommended)* **Continuation is not indented; a genuinely new paragraph is.** Semantically correct, and it is LaTeX's default given clean source. Requires the Markdown→LaTeX converter to preserve the distinction — see WBS 3.5.
- **Always indent after displays.** Simpler, mechanically uniform, slightly wrong when the sentence continues across the display.

---

## 3. Typographic Assessment

### 3.1 The measure is long — and the leading already knows it

125 mm = 354.33 bp = 355.66 TeX pt of measure.

At 9 pt, average lowercase advance for a text serif runs ≈ 0.46–0.52 em, i.e. 4.14–4.68 pt. That yields **≈ 76–86 characters per line**. The conventional comfort band is 45–75; the classical target is 66.

So the measure is above the comfortable range. Four responses:

| Option | Effect | Verdict |
|---|---|---|
| Raise body to 10.5–11 pt | → 62–72 chars | Violates the 9 pt spec |
| Widen margins | → shorter measure | Violates the margin spec |
| Two columns | → ~38 chars/col | Too narrow; worse |
| **Keep 9 pt, rely on the 1.58 leading** | Long measure, generously led | **Recommended** |

Generous leading is precisely the classical remedy for a long measure — it keeps the eye's return sweep accurate. At 1.58 the spec is already doing this deliberately. **The combination is defensible and should be kept.**

Two mitigations are nonetheless strongly recommended, both in §9: **microtypography** (M-1) and **tuned justification parameters** (M-2). At this measure with justified, unindented text, rivers and loose lines are the dominant failure mode, and both are cheap to fix.

**Action:** run the empirical character-count test in §11.2 on real **Greek** NewCM08-Book output before locking the size. If it lands above 85, escalate to 9.5 pt as a negotiated exception.

### 3.2 The baseline grid is the asset — protect it

190 ÷ 5 = 38.000. Exact. This is worth defending, because a grid is only valuable if it survives every element on the page.

**Grid rule: every vertical dimension in the document must be a whole multiple of 14.173 bp — or an exact integer fraction that resolves to a whole multiple over its typical run.**

Applied:

| Element | Leading | Grid relationship |
|---|---|---|
| Body 9 pt | 14.173 bp | 1 unit |
| Caption / table / bib 8 pt | 10.630 bp (¾) | **4 lines = 3 units** ✓ |
| Footnote 7 pt | 9.449 bp (⅔) | **3 lines = 2 units** ✓ |
| `\parskip` | **0 bp** | trivially safe (§2.3a) |
| Space above headings | 14.173 bp × n | n units |
| Figure/table skips | 14.173 bp × n | n units |

The ¾ and ⅔ submultiples are the reason the derived sizes in §6 are 8 pt and 7 pt rather than arbitrary values — they produce clean grid re-synchronisation. This is not decoration; it is what makes a grid hold on a page containing a figure, a caption, and three footnotes.

**Use `\flushbottom`, not `\raggedbottom`.** With an exact grid, every page bottom should land on line 38.

---

## 4. Current Architecture — What Breaks

### 4.1 The LaTeX path today

```
paper_revised.md  (Stage 19)
   └─> Stage 22 EXPORT_PUBLISH  (_review_publish.py:1825)
         └─> paper_final.md                    ← canonical output is MARKDOWN
               └─> templates/converter.py       (68 KB md→tex, stdlib only)
                     └─> templates/conference.py (ConferenceTemplate.render_preamble)
                           └─> templates/compiler.py (pdflatex ×3 + bibtex)
                                 └─> PDF
   └─> export/latex_exporter.py                ← separate, simpler path
   └─> overleaf/formatter.py                   ← ZIP packaging
```

Two independent LaTeX generators exist (`converter.py` + `conference.py`, and `export/latex_exporter.py`). Both need the new target, or the second needs to delegate to the first. **Recommend delegation** — maintaining two book implementations guarantees divergence.

### 4.2 Direct breakages

| # | Component | Location | Break |
|---|---|---|---|
| D-1 | Engine | `compiler.py:807` | pdfLaTeX hardcoded; cannot load OpenType text fonts or `unicode-math` |
| D-2 | Encoding fixups | `compiler.py:718-760` | Injects `inputenc`/T2A; **fatal** under XeLaTeX |
| D-3 | Cyrillic transliteration | `compiler.py:~724` | A pdfLaTeX workaround. Under XeLaTeX, Cyrillic renders natively — transliteration becomes *lossy corruption of author names*. Must be engine-gated. |
| D-4 | Page geometry | `conference.py` | No `geometry` package anywhere; no paper size control |
| D-5 | `ConferenceTemplate` | `conference.py:22` | Frozen dataclass has no fields for trim, margins, leading, engine, or font |
| D-6 | Preamble assembly | `conference.py:38` `render_preamble` | Emits `\documentclass{article}` + style package. Books need `scrbook`-class output. |
| D-7 | Resizebox rewrite | `compiler.py:391-397` | Rewrites `\textwidth` → `\columnwidth` for 2-column conference layouts. **Wrong for a 1-column book** — silently narrows every wide float. |
| D-8 | Float centring | `converter.py:1229` | Emits `\columnwidth` + centring; violates the flush rule |
| D-9 | Export config | `latex_exporter.py:117-150` | `TEMPLATES` dict has no book entry; `_generate_preamble` hardcodes `lmodern` + `inputenc` |
| D-10 | Overleaf ZIP | `overleaf/formatter.py:25-27` | Injects `\documentclass{article}` if absent |

### 4.3 The underestimated breakage — figures

This is the part that will consume more time than the layout itself.

`berb/agents/figure_agent/style_config.py` hardcodes figure geometry for **IEEE/NeurIPS column widths**:

```python
FIGURE_WIDTH = {"single_column": 3.5, "double_column": 7.0, "full_page": 7.0}   # inches
FONT_SIZE_SINGLE_COL = {"title": 9, "axis_label": 8, "tick": 7, ...}            # "to match 10pt body"
```

The new measure is **125 mm = 4.921 in** — between the two presets and equal to neither. Consequences:

1. **Every generated figure is the wrong width.** A 7.0 in figure placed at `width=\textwidth` is scaled by 4.921/7.0 = **0.703×**. All internal type shrinks with it: a 9 pt title becomes 6.3 pt, a 7 pt tick label becomes 4.9 pt. Illegible, and inconsistent from figure to figure depending on which preset was used.
2. **Font sizes were tuned against a 10 pt body.** The body is now 9 pt. Even at native width the figures are proportionally too loud.
3. **`\resizebox` compounds it** (D-7).
4. **Figure typeface will not match the text — and in Greek the failure is silent.** Matplotlib defaults to DejaVu Sans, which *does* render Greek, so you get a legible chart in the wrong face rather than visible tofu.

**Required:** a `book_full` width preset at 4.92 in, a re-tuned font map for a 9 pt body, native-width emission (no `\resizebox`), and NewCM in `matplotlib.rcParams` with a Greek axis-label fixture. Detailed in WBS 4.x.

---

## 5. Target Architecture

### 5.1 Principle

> **Layout is data, not string concatenation.**

Today, layout knowledge is smeared across `conference.py` string templates, `compiler.py` regex fixups, and `style_config.py` constants. Adding a book by extending that pattern would triple the smear.

Introduce a single frozen `LayoutSpec` as the one source of geometric truth. Every consumer — LaTeX preamble, figure generator, validator, Overleaf packer — reads from it. This is the Single Source of Truth fix, and it is what makes the figure pipeline correctable at all.

### 5.2 Components

```
berb/templates/layout.py                    NEW — LayoutSpec (frozen), grid math, unit conversion
berb/templates/styles/book_17x24/
    berb-book.cls                           NEW — the document class
    berb-book-fonts.tex                     NEW — font chain w/ fallbacks
berb/templates/book.py                      NEW — BookTemplate (parallel to ConferenceTemplate)
berb/templates/engine.py                    NEW — engine detection + selection
berb/templates/compiler.py                  MOD — engine dispatch; gate pdfLaTeX-only fixups
berb/templates/converter.py                 MOD — flush float emission when layout.flush_all
berb/agents/figure_agent/style_config.py    MOD — layout-derived widths and font sizes
berb/export/latex_exporter.py               MOD — delegate to BookTemplate
berb/overleaf/formatter.py                  MOD — respect existing documentclass; bundle Caladea
berb/config.py                              MOD — LayoutConfig section
```

### 5.3 `LayoutSpec`

```python
@dataclass(frozen=True)
class LayoutSpec:
    """Single source of geometric truth for one output target."""

    name: str

    # Trim (mm)
    paper_width_mm: float
    paper_height_mm: float

    # Margins (mm) — inner/outer for two-sided, left/right otherwise
    margin_top_mm: float
    margin_bottom_mm: float
    margin_inner_mm: float
    margin_outer_mm: float
    twoside: bool = True

    # Type
    body_size_pt: float = 9.0
    leading_bp: float = 14.173          # bp — NOT pt. See B-2.
    main_font: str = "NewCM08-Book"      # 08 optical size — see Appendix A.3
    sans_font: str = "NewCMSans08-Book"
    mono_font: str = "NewCMMono10-Book"
    math_font: str = "NewCMMath-Book"
    # No fallback: NewCM is OFL and on CTAN. Absence is an error, not a
    # substitution — a different face reflows every page (see §7.2).
    language: str = "greek"
    language_variant: str = "monotonic"

    # Flush/full-width rules (§2.3 Reading 2)
    flush_all: bool = True
    list_hang: bool = False
    parskip_lines: float = 1.0

    engine: Literal["pdflatex", "xelatex", "lualatex"] = "xelatex"

    # ---- Derived ----
    @property
    def text_width_mm(self) -> float:
        return self.paper_width_mm - self.margin_inner_mm - self.margin_outer_mm

    @property
    def text_height_mm(self) -> float:
        return self.paper_height_mm - self.margin_top_mm - self.margin_bottom_mm

    @property
    def leading_mm(self) -> float:
        return self.leading_bp * 25.4 / 72.0

    @property
    def lines_per_page(self) -> float:
        return self.text_height_mm / self.leading_mm

    @property
    def text_width_in(self) -> float:
        """Native figure width — consumed by the figure pipeline."""
        return self.text_width_mm / 25.4

    def size(self, delta_pt: float) -> float:
        """Derived size: body ± delta. Implements the user's sizing rule."""
        return self.body_size_pt + delta_pt

    def grid(self, units: float) -> str:
        """Vertical dimension as a LaTeX length, snapped to the grid."""
        return f"{units * self.leading_bp:.4f}bp"

    def validate(self) -> list[str]:
        """Return warnings. Empty list = clean spec."""
        warns = []
        frac = self.lines_per_page % 1.0
        if min(frac, 1.0 - frac) > 0.01:
            warns.append(
                f"Text height {self.text_height_mm}mm is not an integer multiple "
                f"of leading {self.leading_mm:.4f}mm ({self.lines_per_page:.3f} lines) "
                f"— baseline grid will drift."
            )
        ratio = (self.leading_bp * 72.27 / 72.0) / self.body_size_pt
        if ratio < 1.15:
            warns.append(f"Leading ratio {ratio:.2f} is tight for body text.")
        est_chars = self.text_width_mm * 72.0 / 25.4 / (self.body_size_pt * 0.49)
        if est_chars > 80:
            warns.append(
                f"Measure ≈{est_chars:.0f} chars/line exceeds the 75-char comfort "
                f"band. Generous leading partially compensates; verify empirically."
            )
        return warns


BOOK_17X24 = LayoutSpec(
    name="book_17x24",
    paper_width_mm=170.0, paper_height_mm=240.0,
    margin_top_mm=20.0, margin_bottom_mm=30.0,
    margin_inner_mm=25.0, margin_outer_mm=20.0,
    twoside=True,
    body_size_pt=9.0, leading_bp=14.173,
    engine="xelatex",
)
```

`validate()` is deliberately opinionated: it emits exactly the three warnings this spec triggers in the analysis above, so a future layout that regresses on grid, leading, or measure says so at construction time.

### 5.4 Engine selection

```python
_ENGINE_ARGS = {
    "pdflatex": ["pdflatex", "-interaction=nonstopmode"],
    "xelatex":  ["xelatex",  "-interaction=nonstopmode"],
    "lualatex": ["lualatex", "-interaction=nonstopmode"],
}

_UNICODE_ENGINE_MARKERS = (r"\usepackage{fontspec}", r"\setmainfont",
                           r"\usepackage{unicode-math}", r"\setmathfont")

def detect_required_engine(tex_source: str, declared: str | None = None) -> str:
    """Declared engine wins, unless the source demands a Unicode engine."""
    needs_unicode = any(m in tex_source for m in _UNICODE_ENGINE_MARKERS)
    if needs_unicode and declared in (None, "pdflatex"):
        return "xelatex"
    return declared or "pdflatex"
```

**Fixup gating (D-2, D-3).** Every pdfLaTeX-specific repair in `compiler.py` must become conditional:

```python
if engine == "pdflatex":
    tex = _inject_fontenc_if_missing(tex)
    bib = _transliterate_cyrillic(bib)       # D-3 — lossy; only needed for pdfLaTeX
else:
    tex = _strip_inputenc_fontenc(tex)       # fatal alongside fontspec
    # Cyrillic renders natively — do NOT transliterate
```

D-3 is worth calling out as a **quality improvement, not just a compatibility fix**: switching to XeLaTeX means Russian author names stop being mangled into Latin approximations.

---

## 6. The Derived Type Scale

Rule as specified: every size = body ± n pt. Body = 9 pt. Leadings snapped to grid submultiples (§3.2).

| Role | Rule | Size | Leading | Grid | Notes |
|---|---|---|---|---|---|
| **Body** | body | **9.0 pt** | 14.173 bp | 1 unit | Justified, flush, no indent |
| **Footnote** | body − 2 | **7.0 pt** | 9.449 bp (⅔) | 3 ln = 2 units | Per spec |
| Caption | body − 1 | 8.0 pt | 10.630 bp (¾) | 4 ln = 3 units | Flush, no centring |
| Table body | body − 1 | 8.0 pt | 10.630 bp | 4 ln = 3 units | `booktabs` |
| Bibliography | body − 1 | 8.0 pt | 10.630 bp | 4 ln = 3 units | `bibhang = 0` |
| Block quote | body − 0.5 | 8.5 pt | 14.173 bp | 1 unit | Flush; distinguish by space, not indent |
| Abstract | body − 0.5 | 8.5 pt | 14.173 bp | 1 unit | |
| Folio | body − 2 | 7.0 pt | — | — | Outer foot |
| Running head *(if enabled)* | body − 2 | 7.0 pt | — | — | Off by default (§2.2) |
| Run-in heading (H4) | body | 9.0 pt | 14.173 bp | 1 unit | Bold or small caps |
| Subsection (H3) | body + 1 | 10.0 pt | 14.173 bp | 1 + 1 above = 2 units | |
| Section (H2) | body + 3 | 12.0 pt | 14.173 bp | 1 + 1 above = 2 units | |
| Chapter title (H1) | body + 5 | 14.0 pt | 21.260 bp (1½) | 2 + 2 above = 4 units | |
| Part title | body + 15 | 24.0 pt | 28.346 bp (2) | 2 + 4 above = 6 units | |

**Every heading's total vertical consumption (space-above + leading + space-below) is a whole number of grid units.** This is what keeps line 38 landing on line 38 on a page containing headings.

---

## 7. Reference Implementation

Compile-tested skeleton. Treat as the starting artifact for WBS 2.1, not as final.

### 7.1 Document class — `berb-book.cls`

```latex
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{berb-book}[2026/07/21 Berb 17x24cm Greek book layout]

% parskip=never -> KOMA keeps indent-based paragraphs (§2.3a).
% Do NOT use parskip=full/half: that reintroduces inter-paragraph space.
\PassOptionsToClass{fontsize=9pt,twoside,open=right,parskip=never}{scrbook}
\LoadClass{scrbook}

% ── Geometry ────────────────────────────────────────────────────────────
% Text block: 125 x 190 mm.  190mm / 5mm = 38 lines exactly.
\RequirePackage[
  paperwidth  = 170mm,
  paperheight = 240mm,
  top         = 20mm,
  bottom      = 30mm,
  inner       = 25mm,
  outer       = 20mm,
  twoside,
  heightrounded,      % guarantee integer line count -> grid holds
]{geometry}

% ── Baseline grid ───────────────────────────────────────────────────────
% 14.173bp == 5.000mm.  Using `pt` here would give 4.981mm and drift
% 0.71mm over a 38-line page.  See plan section B-2.
\newlength{\berbleading}
\setlength{\berbleading}{14.173bp}

\renewcommand{\normalsize}{%
  \@setfontsize\normalsize{9pt}{\berbleading}%
  \abovedisplayskip      \berbleading
  \belowdisplayskip      \berbleading
  \abovedisplayshortskip \z@
  \belowdisplayshortskip \berbleading
}
\renewcommand{\small}       {\@setfontsize\small{8pt}{0.75\berbleading}}
\renewcommand{\footnotesize}{\@setfontsize\footnotesize{7pt}{0.6667\berbleading}}
\renewcommand{\large}       {\@setfontsize\large{10pt}{\berbleading}}
\renewcommand{\Large}       {\@setfontsize\Large{12pt}{\berbleading}}
\renewcommand{\LARGE}       {\@setfontsize\LARGE{14pt}{1.5\berbleading}}
\renewcommand{\huge}        {\@setfontsize\huge{24pt}{2\berbleading}}

\flushbottom   % every page bottom lands on line 38

\input{berb-book-fonts}
\input{berb-book-greek}
\endinput
```

### 7.2 Font chain — `berb-book-fonts.tex` *(New Computer Modern Book — decided)*

```latex
\RequirePackage{fontspec}
\RequirePackage{unicode-math}

% New Computer Modern, 08 optical size.  NewCM08 is DRAWN for 8pt, not
% scaled down from 10pt: sturdier stems, looser fit, and 6% wider Greek
% (0.5310 vs 0.5000 em).  That buys both 9pt legibility and ~5 fewer
% characters per line on the long 125mm measure.  See Appendix A.3.
\setmainfont{NewCM08-Book}[
  Extension      = .otf,
  UprightFont    = *,
  ItalicFont     = NewCM08-BookItalic,
  BoldFont       = NewCM10-Bold,
  BoldItalicFont = NewCM10-BoldItalic,
  Ligatures      = TeX,
]

% Sans and mono come from the SAME family — both are Greek-complete.
% A Greek caption set in a Greek-less sans falls back silently and
% breaks the page colour.  See Appendix A.8.
\setsansfont{NewCMSans08-Book}[
  Extension   = .otf,
  UprightFont = *,
  ItalicFont  = NewCMSans08-BookOblique,
  BoldFont    = NewCMSans10-Bold,
  Ligatures   = TeX,
]

\setmonofont{NewCMMono10-Book}[
  Extension   = .otf,
  UprightFont = *,
  ItalicFont  = NewCMMono10-BookItalic,
  BoldFont    = NewCMMono10-Bold,
  Scale       = MatchLowercase,   % mono reads large at 9pt; match x-height
]

\setmathfont{NewCMMath-Book.otf}

% math-style=ISO -> lowercase AND uppercase Greek italic in math.
% Critical in a Greek-language book: it is what visually separates a
% math variable from an ordinary Greek letter of the running text.
% (unicode-math's default `TeX` style leaves uppercase Greek upright,
%  which would make a math Σ indistinguishable from a text Σ.)
\unimathsetup{math-style=ISO, bold-style=ISO}
```

**No fallback chain.** NewCM is OFL, on CTAN, installed locally, and present on Overleaf. This deletes the Caladea chain, the metric-compatibility CI double-compile, the licensing manifest, and the text/math mismatch that the Cambria path forced. If NewCM is somehow absent the build should **fail loudly**, not silently substitute — a substitute would reflow every page and invalidate every cross-reference.

```latex
\IfFontExistsTF{NewCM08-Book.otf}{}{%
  \ClassError{berb-book}
    {New Computer Modern not found}
    {Install the `newcomputermodern' package. Do not substitute —
     a different face changes pagination and cross-references.}%
}
```

### 7.3 Greek language setup — `berb-book-greek.tex`

```latex
\RequirePackage{polyglossia}
\setmainlanguage[variant=monotonic]{greek}
\setotherlanguage{english}          % citations, code, Latin-script symbols

% Greek hyphenation is MANDATORY here, not cosmetic.  Greek words run long;
% at a 125mm justified measure without hyphenation the result is severe
% rivers and loose lines.  Verify `hyph-el` actually loaded — set a full
% page and confirm hyphens appear.  See Appendix A.7.
```

polyglossia also localises the generated strings — `Σχήμα`, `Πίνακας`, `Κεφάλαιο`, `Περιεχόμενα`, `Βιβλιογραφία`. Verify each against house style; the defaults are correct but not always the preferred form.

### 7.4 Flush / full-width rules — every consequence of §2.3 as amended by §2.3a

```latex
% ── 1. Paragraphs: 5mm indent, zero spacing (§2.3a) ─────────────────────
%     parskip=0 makes the baseline grid safe by construction — there is
%     no inter-paragraph space that could fall off the grid.
%     5mm == 1.57em at 9pt == one leading unit.
\setlength{\parindent}{5mm}
\setlength{\parskip}{0pt plus 0pt minus 0pt}   % rigid: no glue, no drift

%     First paragraph after a heading is NOT indented.  This is LaTeX's
%     default; it is preserved by (a) never loading `indentfirst`, and
%     (b) using the STARRED \titlespacing* below.  Both are silent
%     failure modes — dropping the star reintroduces the indent.
% \usepackage{indentfirst}   <-- MUST NOT be loaded

% ── 2. Display math flush left, not centred ─────────────────────────────
\RequirePackage[fleqn]{amsmath}
\setlength{\mathindent}{0pt}

% ── 3. Lists flush.  Strict: wrapped lines return to the margin. ────────
\RequirePackage{enumitem}
\setlist{
  leftmargin  = 0pt,
  itemindent  = 0pt,
  labelindent = 0pt,
  labelwidth  = 0pt,
  labelsep    = 0.5em,
  align       = left,
  topsep      = 0pt, partopsep = 0pt, parsep = 0pt, itemsep = 0pt,
}
% layout.list_hang=true instead emits:
%   \setlist{leftmargin=1.2em, labelsep=0.5em, ...}

% ── 4. Captions flush and full width.  singlelinecheck=false is the key: ─
%      without it, LaTeX silently centres any caption that fits one line.
\RequirePackage[
  format          = plain,
  justification   = raggedright,
  singlelinecheck = false,
  labelsep        = period,
  font            = small,
  labelfont       = bf,
  skip            = 0.75\berbleading,
]{caption}

% ── 5. Footnotes flush at the margin, marker not hanging ────────────────
\RequirePackage[flushmargin,hang=false]{footmisc}
\renewcommand{\footnoterule}{\noindent\rule{0.25\textwidth}{0.4pt}\vspace{2pt}}

% ── 6. Block quotes: separated by space, never by indent ────────────────
\renewenvironment{quote}
  {\par\vspace{\berbleading}\small\noindent\ignorespaces}
  {\par\vspace{\berbleading}}

% ── 7. Floats full width, flush left ────────────────────────────────────
\RequirePackage{graphicx}
\setlength{\intextsep}{\berbleading}
\setlength{\textfloatsep}{\berbleading}
\setlength{\floatsep}{\berbleading}
\makeatletter\renewcommand{\fps@figure}{tbp}\makeatother
% Converter emits:  \includegraphics[width=\textwidth]{...}   (no \centering)

% ── 8. Bibliography: no hanging indent ──────────────────────────────────
\setlength{\bibhang}{0pt}       % natbib
% biblatex: \defbibenvironment{...}{\list{}{\leftmargin=0pt\itemindent=0pt}}...

% ── 9. Headings flush left, grid-quantised ──────────────────────────────
%     The STAR on \titlespacing* suppresses the first-line indent of the
%     paragraph that follows the heading (§2.3a).  Do not remove it.
\RequirePackage[explicit]{titlesec}
\titlespacing*{\section}      {0pt}{\berbleading}{0pt}
\titlespacing*{\subsection}   {0pt}{\berbleading}{0pt}
\titlespacing*{\subsubsection}{0pt}{\berbleading}{0pt}

% ── 10. Folio at outer foot; no running head (§2.2) ─────────────────────
\RequirePackage[automark]{scrlayer-scrpage}
\clearpairofpagestyles
\setkomafont{pagefoot}{\fontsize{7pt}{9.449bp}\selectfont}
\ofoot*{\pagemark}
```

### 7.5 Justification and page-breaking

Non-negotiable at this measure, and more so in Greek than it would be in Latin. See §9 M-1/M-2.

```latex
\RequirePackage[
  protrusion = true,      % optical margin alignment
  expansion  = true,      % micro font expansion — kills rivers
  final,
]{microtype}

\tolerance           = 1500    % default 200 — too strict for 125mm justified
\emergencystretch    = 1.5em   % last resort before an overfull box
\hyphenpenalty       = 200
\hbadness            = 1500    % silence cosmetic warnings; keep real ones
\lefthyphenmin       = 3
\righthyphenmin      = 3
\clubpenalty         = 10000   % no orphans
\widowpenalty        = 10000   % no widows
\displaywidowpenalty = 10000
\brokenpenalty       = 10000   % no hyphen across a page break
```

`expansion=true` requires XeLaTeX ≥ 0.9999 or LuaLaTeX. Under XeLaTeX protrusion works fully and expansion is supported; if the local build rejects it, degrade to `protrusion=true, expansion=false` and record that in the compile log.

---

## 8. Implementation Plan & WBS

### 8.1 Phases

| Phase | Name | Days | Depends | Exit criterion |
|---|---|---|---|---|
| **A** | Layout model & engine | 3 | — | XeLaTeX compiles a hello-world at exact trim |
| **B** | Document class, type scale, Greek | 5 | A | Grid validator passes on a 20-page Greek fixture |
| **C** | Converter & flush rules | 3.5 | B | No centred/wrongly-indented element in the output |
| **D** | Figure pipeline realignment | 4 | A | Figures native-width, Greek labels, fonts match 9 pt body |
| **E** | Export, Overleaf, packaging | 2 | B, C | ZIP compiles clean on Overleaf with NewCM |
| **F** | Validation & docs | 2.5 | all | Automated PDF geometry + Greek assertions green |

### 8.2 Work Breakdown

| WBS | Task | Ph | d | Deliverable |
|---|---|---|---|---|
| **1** | **Layout model & engine** | A | **3** | |
| 1.1 | `LayoutSpec` + derived props + `validate()` | A | 1 | `templates/layout.py` |
| 1.2 | `BOOK_17X24` instance; unit tests on derived values | A | 0.5 | tests |
| 1.3 | `detect_required_engine` + `_ENGINE_ARGS` dispatch | A | 0.5 | `templates/engine.py` |
| 1.4 | Gate pdfLaTeX-only fixups (D-2, D-3) behind engine check | A | 1 | `compiler.py` |
| **2** | **Document class, type scale, Greek** | B | **5** | |
| 2.1 | `berb-book.cls` — geometry, grid, size cascade | B | 1.5 | `.cls` |
| 2.2 | `berb-book-fonts.tex` — NewCM08-Book + Sans + Mono + Math | B | 0.5 | `.tex` |
| 2.3 | `\unimathsetup{math-style=ISO}`; verify text-Greek vs math-Greek | B | 0.5 | test doc |
| 2.4 | Heading scale, grid-quantised spacing (§6) | B | 0.5 | `.cls` |
| 2.5 | Justification / penalty block (§7.5) | B | 0.5 | `.cls` |
| 2.6 | `berb-book-greek.tex` — polyglossia, monotonic, hyphenation | B | 1 | `.tex` |
| 2.7 | Verify polyglossia Greek caption/section strings vs house style | B | 0.5 | test doc |
| **3** | **Converter & flush rules** | C | **3.5** | |
| 3.1 | `BookTemplate` parallel to `ConferenceTemplate` | C | 1 | `templates/book.py` |
| 3.2 | Flush float emission; drop `\centering` when `flush_all` | C | 0.5 | `converter.py` |
| 3.3 | Suppress `\textwidth`→`\columnwidth` rewrite for 1-col (D-7) | C | 0.5 | `compiler.py` |
| 3.4 | Flush lists / captions / quotes / bib (§7.4) | C | 1 | `.cls` |
| 3.5 | Converter: preserve continuation-vs-new paragraph after displays (§2.3a) | C | 0.5 | `converter.py` |
| **4** | **Figure pipeline** *(the underestimated one — §4.3)* | D | **4** | |
| 4.1 | Derive `FIGURE_WIDTH` from `LayoutSpec.text_width_in` | D | 1 | `style_config.py` |
| 4.2 | Re-tune figure font map against a 9 pt body | D | 1 | `style_config.py` |
| 4.3 | Emit native-width figures; remove `\resizebox` on this path | D | 1 | `codegen.py` |
| 4.4 | NewCM in `matplotlib.rcParams`; **Greek axis-label fixture** | D | 1 | `codegen.py` |
| **5** | **Export & packaging** | E | **2** | |
| 5.1 | `latex_exporter.py` delegates to `BookTemplate` (kill dup) | E | 1 | `latex_exporter.py` |
| 5.2 | Overleaf: NewCM is preinstalled — verify, no font bundling needed | E | 0.5 | `overleaf/formatter.py` |
| 5.3 | `LayoutConfig` section + CLI `--layout book_17x24` | E | 0.5 | `config.py`, `cli.py` |
| **6** | **Validation & docs** | F | **2.5** | |
| 6.1 | PDF geometry assertions (MediaBox, margins, parity) | F | 0.75 | `test_book_layout.py` |
| 6.2 | Baseline-grid extraction assertion | F | 0.75 | tests |
| 6.3 | Font-embedding assertion (NewCM subset present) | F | 0.25 | tests |
| 6.4 | Regression: conference output byte-identical | F | 0.25 | tests |
| 6.5 | Greek assertions: hyphenation active, ς / `;` / `·` render | F | 0.5 | tests |

**Total: 20 engineer-days.** The +2 over the rev 1.0 estimate is Greek (WBS 2.6, 2.7, 4.4, 6.5), partly offset by the fallback chain that the NewCM decision deleted.

---

## 9. Suggested Additional Changes

Ranked by (quality gain) ÷ (cost). The first five are strongly recommended; **M-1, M-2 and M-3 should be treated as base scope, not extras.**

### Strongly recommended

**M-1 — Microtypography (protrusion + expansion).** *0.25 d.*
At 125 mm justified with a long measure, rivers and loose lines are the dominant defect, and Greek's longer words make it worse. `microtype` with both features is the single largest legibility gain available and costs one package line. Already in §7.5.

**M-2 — Tuned justification parameters.** *0.25 d.*
LaTeX's default `\tolerance=200` is calibrated for a ~345 pt measure with indents. At this measure it produces either overfull boxes or badly loose lines. The block in §7.5 is the fix. Without M-1 and M-2 the spec's generous leading is fighting a losing battle.

**M-3 — Greek hyphenation verification, as a test not a hope.** *0.25 d.*
Greek needs hyphenation more than English does, and a silently-unloaded pattern file produces a page that looks merely "a bit loose" rather than obviously broken. Assert it: set a known long Greek paragraph, extract the PDF text, require ≥ N hyphens. Cheap, and it catches the failure that is hardest to spot by eye.

**M-4 — Enforce the grid programmatically, not by convention.** *0.5 d.*
Expose `LayoutSpec.grid(units)` (§5.3) and require every vertical length in the class to be written as `\berbleading` multiples. Add a lint that greps the `.cls` for bare `pt`/`mm` vertical skips. A grid maintained by discipline decays; one maintained by a helper does not.

**M-5 — Two output profiles: `screen` and `press`.** *1 d.*
- `screen`: `hyperref` with `colorlinks`, RGB, no bleed, single pages.
- `press`: `hyperref` with `hidelinks`, CMYK-safe, **3 mm bleed → 176 × 246 mm media**, crop marks via the `crop` package, PDF/X-ready.

A 17 × 24 cm trim is a print size. Shipping only a screen PDF means the first thing a printer asks for does not exist.

### Recommended

**M-6 — Match figure typography to the page.** *(folded into WBS 4.4)*
Set `matplotlib.rcParams["font.family"]` to NewCM and `mathtext.fontset` to a serif set. **In Greek this is a correctness issue, not only an aesthetic one**: matplotlib's default DejaVu will render Greek, so the failure is silent — you get a legible chart in the wrong face rather than visible tofu. Add a Greek string to the figure fixture.

**M-7 — Drop the Cyrillic transliteration under Unicode engines.** *0.25 d.* (D-3)
`compiler.py` mangles "А. И. Колесников" into Latin because pdfLaTeX cannot set Cyrillic without T2A. XeLaTeX can. Gating this by engine turns a compatibility hack into a correctness improvement for every non-Latin author name in the bibliography — which matters more in a Greek book, whose bibliography is likely to be mixed-script already.

**M-8 — Use `scrbook`, not `book`.** *(in WBS 2.1)*
Standard `book` supports only 10/11/12 pt. Reaching 9 pt requires `extsizes` or manual `\@setfontsize` surgery. KOMA-Script takes `fontsize=9pt` directly, has correct two-sided handling, and `scrlayer-scrpage` gives clean outer-foot folios. `memoir` is an equally good alternative; `book` is not.

**M-9 — ~~Decide the `\parskip` question~~ — RESOLVED by the §2.3a amendment.** *0 d.*
Superseded. The 5 mm indent with zero paragraph spacing removes the problem rather than trading it off: no vertical space is consumed, and the grid is safe by construction. Recovers the ~20 % per-page cost the previous design would have incurred. **No sign-off needed.**

**M-9a — ~~Switch to a libre family with matched math~~ — DECIDED: New Computer Modern Book.** *−1.5 d (net saving).*
Deletes the Caladea fallback chain, the metric-compatibility CI double-compile, the licensing manifest, the Overleaf font-bundling question (R-10), and the text/math mismatch the Cambria path forced. Blocker B-3 is closed. See Appendix A.

**M-10 — Optical margin alignment for the flush edge.** *(comes free with M-1)*
With every block element flush, the left edge is conspicuous. `protrusion` pushes hyphens, quotes and periods slightly into the margin so the edge reads as optically straight. Greek punctuation (`·`, `;`) benefits from this as much as Latin.

### Worth considering

**M-11 — Front/back matter structure.** *1 d.* A 17 × 24 book implies half-title, title, colophon, TOC, and possibly an index. `scrbook` provides `\frontmatter`/`\mainmatter`/`\backmatter` with roman/arabic folio switching. Berb's Markdown → LaTeX converter has no concept of these; without them the output is a long article in book clothing. **Greek note:** roman-numeral front matter is conventional in Greek books too, but confirm — some houses use Greek numerals (αʹ, βʹ) instead.

**M-12 — `\cleardoublepage` chapter openings.** *0.25 d.* With `twoside`, chapters should open recto. `open=right` handles it; blank verso pages need a `\pagestyle{empty}` hook so a stray folio does not appear on them.

**M-13 — Greek hyphenation exception list.** *0.5 d.* Automatic patterns handle ordinary Greek well but break technical and transliterated vocabulary badly. Maintain a `\hyphenation{}` list for domain terms as they surface in proofs.

**M-14 — Table strategy for 125 mm.** *0.5 d.* Existing tables are sized for conference columns and rely on `\resizebox`, which scales type. At 125 mm prefer `tabularx` with `\small` (8 pt) and let columns wrap rather than shrinking type below the footnote size. Hard floor: no table type below 7 pt.

**M-15 — Reconsider 9 pt if the Greek measure test exceeds 85 chars.** *0 d — a decision, not work.* Appendix A.3 estimates ~80 chars/line for NewCM08. If §11.2 measures above 85, 9.5 pt (still expressible as "body", everything else re-derived) buys real comfort for a 0.5 pt concession.

---

## 10. Risk Matrix

| ID | Risk | P | I | Mitigation | Trigger / contingency |
|---|---|---|---|---|---|
| ~~R-01~~ | ~~Cambria absent on build host or Overleaf~~ | — | — | **Closed** by the NewCM decision — OFL, on CTAN, on Overleaf | n/a |
| R-02 | XeLaTeX not installed in the runtime | M | H | Engine detection returns a typed error, not a crash; document the TeX Live / MiKTeX requirement | Missing engine → fail fast with an actionable message |
| R-03 | pdfLaTeX fixups fire under XeLaTeX and break compilation (D-2) | **H** | **H** | Gate every fixup on engine (WBS 1.4); regression test per engine | Any `inputenc` in XeLaTeX output = test failure |
| R-04 | Figures illegible from double-scaling (§4.3) | **H** | M | Native-width emission; suppress `\resizebox` on this path; visual diff fixture | Effective figure type < 6 pt → fail validation |
| R-05 | Baseline grid drifts (`pt` vs `bp`) | M | H | `bp` throughout; `heightrounded`; automated grid assertion (WBS 6.2) | Measured line pitch ≠ 14.173 bp ± 0.05 → fail |
| R-06 | Conference output regresses | M | **H** | Book is a separate `LayoutSpec` + class; byte-identical regression test (WBS 6.4) | Any diff in NeurIPS/ICLR/ICML PDF → block merge |
| R-07 | Contract changes break `--from-stage` resume | M | H | `optional_output_files`; resume E2E test against a legacy fixture | Resume test fails → revert the contract change |
| R-08a | `indentfirst` loaded, or `\titlespacing` star dropped → indent appears after headings | M | L | Emitted-`.tex` assertion; visual fixture check | Indent detected after a heading → test failure |
| **R-09** | **Greek hyphenation silently inactive** | **M** | **H** | M-3 assertion: require ≥ N hyphens in a known Greek fixture paragraph | Hyphen count below threshold → fail build |
| R-10 | NewCM low x-height (0.431) reads small at 9 pt | M | M | 08 optical size mitigates; §11.2 measure + legibility proof | Proof rejected → escalate to 9.5 pt (M-15) |
| R-11 | Greek-less sans/mono substituted for captions or code | M | M | NewCM Sans/Mono are in-family and Greek-complete; A.2 coverage check on any substitute | Silent fallback detected → fail font assertion |
| R-12 | Scope creep from Berb's large surface area | H | M | Phase exit criteria are binary; new capability requires written justification | Phase slips > 20 % → cut M-11/M-13 to backlog |
| R-13 | Text-Greek and math-Greek visually indistinguishable | M | M | `math-style=ISO` (WBS 2.3); side-by-side proof page | Σ in text and Σ in math identical → fix unimathsetup |

---

## 11. Validation & QA Strategy

### 11.1 Automated PDF assertions

Berb already has `check_compiled_quality` in `compiler.py`. Extend it with a book profile.

```python
def assert_book_geometry(pdf: Path, spec: LayoutSpec) -> list[str]:
    """Returns failures. Empty = pass."""
    failures = []
    reader = PdfReader(pdf)

    # 1. Trim size — 170x240mm == 481.890 x 680.315 bp
    box = reader.pages[0].mediabox
    for actual, expected, label in (
        (float(box.width),  spec.paper_width_mm  * 72 / 25.4, "width"),
        (float(box.height), spec.paper_height_mm * 72 / 25.4, "height"),
    ):
        if abs(actual - expected) > 0.5:
            failures.append(f"MediaBox {label}: {actual:.2f}bp != {expected:.2f}bp")

    # 2. Mirrored margins — inner edge flips with page parity
    for i, page in enumerate(reader.pages):
        left, _right = _text_bbox_x(page)
        is_recto = (i % 2 == 0)
        expect_left = spec.margin_inner_mm if is_recto else spec.margin_outer_mm
        if abs(left * 25.4 / 72 - expect_left) > 0.5:
            failures.append(f"p{i+1}: left margin {left*25.4/72:.2f}mm != {expect_left}mm")

    # 3. Baseline grid — line pitch must equal the leading
    for p in _baseline_pitches(reader.pages[2]):
        if abs(p - spec.leading_bp) > 0.05:
            failures.append(f"Baseline pitch {p:.3f}bp != {spec.leading_bp}bp")

    # 4. Fonts embedded and subset
    if not _fonts_embedded(reader):
        failures.append("Non-embedded font detected")

    return failures
```

### 11.2 The Greek measure test *(run before locking 9 pt)*

Set ~500 words of real Greek prose in NewCM08-Book at 9 pt across 125 mm. Extract per-line character counts with `pdfplumber`; report mean and 90th percentile.

- Mean ≤ 78 → proceed at 9 pt.
- 78 < mean ≤ 85 → proceed, but confirm M-1/M-2 are active.
- Mean > 85 → escalate to 9.5 pt (M-15).

**The rev 1 Latin figures do not transfer** — Greek sets 2–8 % wider (A.3), so this must be measured in Greek.

### 11.3 Test matrix

| Test | Marker | Asserts |
|---|---|---|
| `LayoutSpec` derived values | unit | 125 × 190 mm; 38.00 lines; 4.921 in |
| `validate()` warnings | unit | Grid/leading/measure warnings fire correctly |
| `bp` vs `pt` regression | unit | `grid(1)` = 14.173 bp, never 14.173 pt |
| Engine detection | unit | `fontspec` present → xelatex, whatever was declared |
| Fixup gating | unit | No `inputenc` injected under xelatex; no transliteration |
| Trim size | integration | MediaBox within 0.5 bp |
| Mirrored margins | integration | Parity-correct on ≥ 10 pages |
| Baseline grid | integration | Pitch = 14.173 bp ± 0.05 on a text-only page |
| Paragraph model | integration | 5 mm indent present; **absent** after every heading level |
| Flush compliance | integration | Zero `\centering`; zero non-zero indent on block elements |
| **Greek hyphenation** | integration | ≥ N hyphens in a known long Greek paragraph |
| **Greek glyphs** | integration | ά ς `;`(U+037E) `·`(U+0387) present and correctly mapped |
| **Greek math distinction** | integration | Text Σ upright, math Σ italic |
| Font embedding | integration | NewCM08-Book, NewCMMath-Book subset and embedded |
| Figure width | integration | Emitted width = `\textwidth`; no `\resizebox` |
| Figure Greek | integration | Greek axis label renders in NewCM, not DejaVu |
| Conference regression | integration | NeurIPS/ICLR/ICML PDFs byte-identical to baseline |

---

## 12. Acceptance Checklist

### Geometry
- [ ] PDF MediaBox = 481.890 × 680.315 bp (±0.5)
- [ ] Recto: inside margin 25 mm left, outside 20 mm right
- [ ] Verso: outside margin 20 mm left, inside 25 mm right
- [ ] Top margin 20 mm to the type area; bottom 30 mm
- [ ] Text block measures 125 × 190 mm
- [ ] Exactly 38 body lines on a full text page

### Typography
- [ ] Body sets in **NewCM08-Book at 9 pt**
- [ ] Line pitch = 14.173 bp = 5.000 mm, verified from the PDF
- [ ] Footnotes at 7 pt; three footnote lines occupy exactly two body lines
- [ ] Captions, tables, bibliography at 8 pt; four lines = three body lines
- [ ] Every heading consumes a whole number of grid units
- [ ] All fonts embedded and subset
- [ ] `microtype` protrusion active (expansion active or documented as unavailable)
- [ ] No widows, no orphans, no hyphen across a page break

### Paragraphs (§2.3a)
- [ ] `\parindent` = 5 mm on running-text paragraphs
- [ ] `\parskip` = 0, rigid (no glue)
- [ ] First paragraph after every heading level is **not** indented
- [ ] `indentfirst` package is **not** loaded
- [ ] All `\titlespacing` calls use the starred form
- [ ] Text still lands on the baseline grid after 40 consecutive paragraphs

### Greek
- [ ] `polyglossia` main language = greek, `variant=monotonic`
- [ ] Greek hyphenation demonstrably active (M-3 assertion passes)
- [ ] Final sigma ς correct throughout; no σ at word end
- [ ] Greek question mark is U+037E, not Latin `;` (U+003B)
- [ ] Ano teleia is U+0387, not middot (U+00B7)
- [ ] Tonos renders as a tonos, not a borrowed Latin acute
- [ ] Text Greek upright; math Greek italic (`math-style=ISO`)
- [ ] Greek renders correctly in captions, footnotes, folios, and **figures**
- [ ] polyglossia's Greek strings (Σχήμα, Πίνακας, Κεφάλαιο) match house style

### Flush / full-width
- [ ] Block-level elements flush at the type-area edge (paragraph first lines exempt)
- [ ] Display math flush left, not centred
- [ ] Lists flush; wrapped lines return to the margin (or hang, if `list_hang` set)
- [ ] Captions flush left — including single-line captions
- [ ] Footnote text flush; marker does not hang
- [ ] Bibliography entries flush; no hanging indent
- [ ] Figures and tables at `\textwidth`, flush, not centred
- [ ] Folio at the outer foot, both parities

### Pipeline
- [ ] Compiler selects XeLaTeX when `fontspec` is present
- [ ] No `inputenc`/`fontenc`/T2A injected under Unicode engines
- [ ] Cyrillic author names render natively, untransliterated
- [ ] `\textwidth`→`\columnwidth` rewrite suppressed for one-column book output
- [ ] Figures generated at 4.921 in native width, never `\resizebox`-scaled
- [ ] Figure fonts tuned to a 9 pt body; nothing below 6 pt
- [ ] Matplotlib uses NewCM and renders Greek
- [ ] Overleaf ZIP compiles clean (NewCM preinstalled; no font bundling)
- [ ] Conference templates produce byte-identical output to the pre-change baseline

### Sign-offs required before build
- [x] Typeface — **New Computer Modern Book, 08 optical size** *(decided)*
- [x] Greek variant — **monotonic** *(decided)*
- [x] Paragraph model — 5 mm indent, zero spacing *(decided, §2.3a)*
- [ ] §2.2 — top margin measured to type area, running heads omitted
- [ ] §2.3 — flush Reading 2 confirmed; list-hang variant chosen
- [ ] §11.2 — Greek measure test run; 9 pt confirmed or escalated to 9.5 pt

---

# Appendix A — Typeface Selection Research *(rev 2 — Greek text)*

> **Revision 2 supersedes revision 1 entirely.** Rev 1 recommended **Erewhon**, chosen for Latin text. Measured glyph coverage shows Erewhon carries **47.9 % of modern Greek and 0 % of polytonic Greek** — it has the math-Greek alphabet only, and lacks Ά ά ϊ ΐ, the Greek question mark, and the ano teleia. **Erewhon is unusable for Greek body text.** The same applies to XCharter (same author, same design approach). Everything below is measured on this machine, not recalled.

## A.1 What Greek changes

Greek is not a coverage checkbox. It re-ranks the entire field for four reasons.

**1. Most Latin-first fonts ship "Greek" that is only the math alphabet.** Unaccented α–ω and Α–Ω are enough to set equations and nothing else. Greek *text* needs the accented range (ά έ ή ί ό ύ ώ ΐ ΰ), the final sigma ς, and two punctuation marks that are not Latin lookalikes: the Greek question mark **;** (U+037E, *erotimatiko*) and the **·** (U+0387, *ano teleia*). A font that substitutes a Latin semicolon and middot for those is wrong, not merely incomplete. This filter eliminated the previous top pick.

**2. Monotonic versus polytonic is a hard fork.** Monotonic (modern, single tonos) needs U+0386–U+03CE. Polytonic (ancient, katharevousa, liturgical, and most classical quotation) additionally needs Greek Extended, U+1F00–U+1FFF — roughly 230 precomposed glyphs with breathings, circumflex, and iota subscript. **Several otherwise-excellent candidates have full monotonic and zero polytonic.**

**3. Greek letters now live in both text and math.** This is the defining problem of Greek-language mathematical typesetting and it has no counterpart in English. In an English book, α appears only in equations, so text face and math face never compete. In a Greek book, α is both a variable and an ordinary letter of the running text. If the text Greek and the math Greek come from unrelated fonts, the same letterform appears in two visibly different designs on the same page. **This is the single strongest argument for a family whose text and math halves were drawn together.**

**4. Greek needs hyphenation more than English does.** Modern Greek words average noticeably longer than English ones. At a 125 mm justified measure (§3.1) with no hyphenation, the result is rivers and loose lines. Greek patterns are mandatory, not optional — see A.7.

## A.2 Measured Greek coverage

Method: `fontTools`, cmap coverage of U+0386–U+03CE (monotonic) and U+1F00–U+1FFF (polytonic), plus a critical-glyph probe for Ά ά ϊ ΐ ς, U+037E, U+0387, and the variant forms ϕ ϱ.

| Text font | monotonic | polytonic | Critical glyphs missing |
|---|---:|---:|---|
| **New Computer Modern** (Book & Regular) | **95.9 %** | **91.4 %** | none |
| **Libertinus Serif** | **95.9 %** | **91.4 %** | none |
| **Cambria** | **95.9 %** | **91.4 %** | none |
| STIX Two Text | 95.9 % | **0 %** | none |
| **Erewhon** | **47.9 %** | **0 %** | Ά, ά, ϊ, ΐ, `;` erotimatiko, `·` ano teleia |

Math fonts (Erewhon-Math, XCharter-Math, TeX Gyre Pagella/Schola/Termes/Bonum Math) all measure **67.1 % monotonic / 0 % polytonic**. That is correct and expected — a math font needs only the unaccented alphabet. **It is not a defect in a math font; it is a fatal defect in a text font.**

**Consequences.** Erewhon is out. XCharter is out for the same reason (unverified but same author, same design approach — confirm before considering). STIX Two Text is viable for monotonic only. TeX Gyre Pagella and Schola were rev 1 runners-up; their text fonts are not installed here, and GUST's Greek coverage must be measured before they can be considered — do not assume it.

## A.3 Measured metrics

| Font | x-height/em | Greek adv (em) | Latin adv (em) | Greek/Latin |
|---|---:|---:|---:|---:|
| Cambria | **0.467** | 0.5272 | 0.4879 | 1.08 |
| STIX Two Text | **0.473** | 0.4885 | 0.4808 | 1.02 |
| NewCM08-Book | 0.431 | **0.5310** | 0.5189 | 1.02 |
| NewCM10-Book | 0.431 | 0.5000 | 0.4887 | 1.02 |
| Libertinus Serif | 0.429 | 0.5024 | 0.4668 | 1.08 |

Three findings.

**Greek sets 2–8 % wider than Latin in every candidate.** So the measure problem is marginally *less* severe in Greek than the rev 1 Latin analysis suggested — fewer characters per line for the same physical width. It does not disappear: including word spaces, all candidates land at roughly **80–87 characters per line** at 9 pt across 125 mm, still above the 45–75 comfort band. The spec's generous 1.58 leading (§3.1) remains the compensation, and choosing the widest available face is the strongest remaining lever.

**New Computer Modern has optical sizes, and this matters here.** `NewCM08` is drawn for 8 pt, not scaled from 10 pt: sturdier stems, looser spacing, and **6 % wider Greek** than `NewCM10` (0.5310 vs 0.5000 em). Setting 9 pt body from the **08 optical size** simultaneously improves small-size legibility and shortens the line by ~5 characters. This is the single most useful metric finding in this appendix, and it is free.

**x-height is where the free options lose.** Cambria (0.467) and STIX Two (0.473) sit ~8 % above NewCM (0.431) and Libertinus (0.429). At 9 pt that is an effective 4.20 pt versus 3.88 pt of reading height — visible, and it works directly against the small body size. This is a real cost of the libre options and should not be glossed over.

## A.4 Availability on this machine

MiKTeX 25.12, probed directly.

| Family | Text | Math | Status |
|---|---|---|---|
| New Computer Modern | ✅ 3 optical sizes × Book/Regular/Bold + Sans + Mono | ✅ `NewCMMath-Book/Regular/Bold` | **installed** |
| Libertinus | ✅ Serif/Sans/Mono + Display + Semibold | ✅ `LibertinusMath-Regular` | **installed** |
| STIX Two | ✅ | ✅ | installed |
| Cambria | ✅ `C:/Windows/Fonts/cambria.ttc` | ✅ same `.ttc` | this machine only |
| **GFS** (Greek Font Society) | Didot, Artemisia, Neohellenic, Bodoni, Baskerville, Complutum, DidotClassic | ❌ **none** | on CTAN, installable |
| `babel-greek`, `cbgreek` | — | — | installed |

## A.5 Candidates

### Recommended — New Computer Modern Book

Full monotonic and polytonic Greek, no missing critical glyphs. Matched OpenType MATH companion (`NewCMMath-Book`) in the same weight as the text. Three optical sizes. Complete family: serif, sans, mono. OFL. Already installed.

The decisive argument is authorship: NewCM is maintained by **Antonis Tsolomitis, a mathematician at the University of the Aegean**. The Greek is native design by someone who reads Greek and sets mathematics in it — not a Latin face with Greek bolted on afterwards. That shows in the tonos design and in the fact that text-Greek and math-Greek were reconciled deliberately, which is exactly the A.1 §3 problem.

*Against:* low x-height (0.431) — mitigated but not erased by using the 08 optical size. Computer Modern lineage still reads as "a TeX document" to some eyes, though the **Book** weight is materially heavier and less spindly than classic CM.

```latex
\setmainfont{NewCM08-Book}[      % 08 optical size at 9pt: sturdier + 6% wider
  Extension = .otf, UprightFont = *, ItalicFont = NewCM08-BookItalic,
  BoldFont = NewCM10-Bold, Ligatures = TeX,
]
\setmathfont{NewCMMath-Book.otf}
```

### Strong alternative — Libertinus

Identical Greek coverage (95.9 / 91.4, nothing critical missing), matched `LibertinusMath`, OFL, installed, and a more conventionally "book-like" Renaissance face than NewCM. Widely used in European academic publishing.

*Against:* lowest x-height measured (0.429) and finer strokes than NewCM Book — the weakest of the viable set **at 9 pt specifically**. At 10.5 pt it would be a clear first choice. Also the narrowest Greek advance of the three full-coverage options after NewCM08.

### Best typographic fit, if licensing allows — Cambria

Measured full polytonic coverage, no missing critical glyphs, **the highest x-height of any full-Greek candidate (0.467)**, wide Greek (0.5272 em → ~75 chars/line), low contrast, and **Cambria Math is the reference implementation of the OpenType MATH table**. For a 9 pt Greek mathematics book this is, on measured merit, the best fit in the field.

The objection is entirely legal and operational (B-3, A.6), not typographic. Worth noting plainly: the spec's original font choice was a good one for Greek, and better than the rev 1 Latin-driven substitute.

### Monotonic only — STIX Two

Highest x-height measured (0.473), full monotonic Greek, complete matched math, unmatched symbol coverage.

**Disqualified if any polytonic is needed — 0 % of Greek Extended.** Also the narrowest candidate (~87 chars/line), which is the wrong direction for this measure, and Times-derived so it sets thin at 9 pt.

### Best Greek, unsolved math — GFS

The Greek Font Society faces are the reference for Greek scholarly publishing. **GFS Didot** is the standard Greek academic book face; **GFS Artemisia** is highly readable at text sizes; **GFS Neohellenic** is the classicists' face; **GFS Porson** is the traditional face for ancient Greek quotation. All OFL, all on CTAN, none installed here.

**None has an OpenType MATH companion.** Adopting GFS means pairing it with an unrelated math font, which reintroduces the A.1 §3 collision — Greek in the text drawn by GFS, Greek in the equations drawn by someone else, on the same page. For a book *with* mathematics this is a significant regression, and it is the reason GFS is not the recommendation despite having the best Greek in the field.

Viable only if: mathematics is sparse and display-only, or you accept the mismatch deliberately.

## A.6 Recommendation

| Situation | Choose |
|---|---|
| **Default — Greek + math, libre, polytonic-safe** | **New Computer Modern Book**, set from the **08 optical size** |
| More conventional book feel, math still matched | Libertinus |
| Cambria licensing acceptable | **Cambria + Cambria Math** — measurably the best fit |
| Strictly monotonic, want maximum x-height | STIX Two (accept ~87 chars/line) |
| Greek authenticity above all, sparse math | GFS Didot + separately chosen math font |

Ranked by what this spec actually stresses — 9 pt legibility, polytonic safety, matched math, and a long measure — the order is **NewCM Book ≳ Cambria > Libertinus > STIX Two > GFS**, with Cambria first on pure merit and NewCM first once licensing is weighted.

## A.7 Required Greek setup *(independent of face)*

```latex
\usepackage{polyglossia}
\setmainlanguage[variant=monotonic]{greek}   % or variant=polytonic
\setotherlanguage{english}                    % for citations, code, symbols
```

Five things that must be verified, all of which are common failure modes:

1. **Hyphenation patterns must load.** Greek words are long; at 125 mm justified, unhyphenated Greek produces severe rivers. Confirm `hyph-el` (monotonic) or `hyph-el-polyton` is active — set a full page and check for hyphens.
2. **Final sigma.** With Unicode input, ς versus σ is the author's responsibility; there is no automatic conversion. Add a proofing check.
3. **Greek punctuation must be the Greek codepoints.** `;` = U+037E, `·` = U+0387. A Latin `;` (U+003B) or middot (U+00B7) will render but is typographically wrong; both look nearly identical in proof, so check the source, not the PDF.
4. **Tonos, not acute.** A proper Greek tonos is a distinct mark, not a borrowed Latin acute. All three recommended faces get this right; verify if you substitute another.
5. **Text Greek upright, math Greek italic.** ISO 80000-2 already requires italic math variables; in Greek this convention does double duty by distinguishing a variable from an ordinary letter. Enforce it, and do not let emphasis in Greek text be set in italic Greek where mathematics is nearby — use spacing, small caps, or semibold instead.

## A.8 Companion faces

| Role | With NewCM | With Libertinus | With Cambria |
|---|---|---|---|
| Sans | **NewCM Sans** (same family, Greek-complete) | Libertinus Sans | Calibri / Open Sans |
| Mono | **NewCM Mono** | Libertinus Mono | Consolas |

NewCM and Libertinus both ship Greek-capable sans and mono in-family — a real advantage, because a Greek caption or a Greek code comment set in a font without Greek will silently fall back and break the page colour. Verify Greek coverage of any substitute sans/mono with the A.2 method; **this is the most commonly missed step**, and captions are exactly where it shows.

**Figure text.** WBS 4.4 sets `matplotlib.rcParams["font.family"]`. Greek axis labels require a Greek-capable font there too, or matplotlib substitutes silently and figures show tofu or a mismatched face. Point it at the chosen family and add a Greek string to the figure regression fixture.

## A.9 Decisions required

- [ ] **Monotonic or polytonic?** Determines whether STIX Two is admissible at all
- [ ] Confirm typeface: **NewCM Book** *(recommended)* / Libertinus / Cambria / STIX Two / GFS
- [ ] If NewCM: confirm the **08 optical size** for 9 pt body
- [ ] If Cambria: accept A.6/B-3 licensing consequences in writing
- [ ] Verify Greek coverage of the chosen sans and mono (A.2 method)
- [ ] Re-run the §11.2 measure test **in Greek** — the rev 1 Latin figures do not transfer
- [ ] Add a Greek string (accented + final sigma + `;` + `·`) to the figure and PDF regression fixtures

---

**End of document.**
