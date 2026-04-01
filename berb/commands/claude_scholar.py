"""Claude Scholar enhancement commands for Berb CLI.

Provides 10 core commands:
1. /research-init - Start Zotero-integrated research
2. /zotero-review - Review Zotero collection
3. /zotero-notes - Batch-read papers → notes
4. /obsidian-ingest - Ingest Markdown files
5. /analyze-results - Experiment analysis + report
6. /rebuttal - Generate rebuttal from reviews
7. /mine-writing-patterns - Extract writing patterns
8. /verify-citations - Verify citation accuracy
9. /anti-ai-editing - Remove AI phrasing
10. /obsidian-init - Bootstrap Obsidian knowledge base

Author: Georgios-Chrysovalantis Chatzivantsidis

Usage:
    berb research-init --topic "Your topic"
    berb zotero-review --collection "My Collection"
    berb zotero-notes --papers paper1.pdf paper2.pdf
    berb obsidian-ingest --input Writing/ --output ~/Vault/
    berb analyze-results --data results.csv --output report.md
    berb rebuttal --manuscript paper.pdf --reviews reviews.txt
    berb mine-writing-patterns --corpus papers/
    berb verify-citations --paper paper.pdf
    berb anti-ai-editing --input draft.md --output revised.md
    berb obsidian-init --vault ~/Vault/
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Command: research-init
# =============================================================================

def cmd_research_init(args: argparse.Namespace) -> int:
    """Start Zotero-integrated research project."""
    from berb.literature.zotero_integration import ZoteroMCPClient, ZoteroConfig

    print(f"Initializing research project: {args.topic}")

    # Initialize Zotero client
    config = ZoteroConfig(
        mcp_url=args.mcp_url,
        api_key=args.zotero_api_key,
    )

    try:
        client = ZoteroMCPClient(config)

        # List collections
        print("\nFetching Zotero collections...")
        collections = client.list_collections_sync()

        print(f"Found {len(collections)} collections:")
        for i, coll in enumerate(collections[:10], 1):
            print(f"  {i}. {coll.get('name', 'Unknown')} ({coll.get('count', 0)} papers)")

        if len(collections) > 10:
            print(f"  ... and {len(collections) - 10} more")

        # Create project directory
        project_dir = Path(args.output) / args.topic.replace(" ", "_").lower()
        project_dir.mkdir(parents=True, exist_ok=True)

        print(f"\nProject directory created: {project_dir}")

        # Initialize subdirectories
        (project_dir / "Knowledge").mkdir(exist_ok=True)
        (project_dir / "Literature").mkdir(exist_ok=True)
        (project_dir / "Writing").mkdir(exist_ok=True)
        (project_dir / "Results").mkdir(exist_ok=True)

        print("Subdirectories initialized:")
        print("  - Knowledge/")
        print("  - Literature/")
        print("  - Writing/")
        print("  - Results/")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: zotero-review
# =============================================================================

def cmd_zotero_review(args: argparse.Namespace) -> int:
    """Review Zotero collection."""
    from berb.literature.zotero_integration import ZoteroMCPClient, ZoteroConfig

    print(f"Reviewing Zotero collection: {args.collection}")

    config = ZoteroConfig()
    client = ZoteroMCPClient(config)

    try:
        # Get collection
        collections = client.list_collections_sync()
        collection_id = None

        for coll in collections:
            if args.collection.lower() in coll.get('name', '').lower():
                collection_id = coll.get('id')
                break

        if not collection_id:
            print(f"Collection not found: {args.collection}")
            return 1

        # Get papers
        papers = client.get_collection_papers_sync(collection_id)

        print(f"\nCollection contains {len(papers)} papers:")
        for i, paper in enumerate(papers[:20], 1):
            title = paper.get('title', 'Unknown')[:80]
            year = paper.get('year', 'n.d.')
            print(f"  {i:2d}. [{year}] {title}")

        if len(papers) > 20:
            print(f"  ... and {len(papers) - 20} more")

        # Generate summary statistics
        years = [p.get('year') for p in papers if p.get('year')]
        if years:
            print(f"\nYear range: {min(years)} - {max(years)}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: zotero-notes
# =============================================================================

def cmd_zotero_notes(args: argparse.Namespace) -> int:
    """Batch-read papers and generate notes."""
    from berb.literature.zotero_integration import ZoteroMCPClient, ZoteroConfig

    print(f"Generating notes for {len(args.papers)} papers...")

    config = ZoteroConfig()
    client = ZoteroMCPClient(config)

    try:
        notes = []

        for paper_path in args.papers:
            paper = Path(paper_path)
            if not paper.exists():
                print(f"Warning: Paper not found: {paper}")
                continue

            print(f"Processing: {paper.name}")

            # Extract annotations
            annotations = client.export_annotations_sync(paper.stem)

            if annotations:
                note = f"# Notes for {paper.name}\n\n"
                note += "## Annotations\n\n"
                for ann in annotations[:10]:
                    note += f"- {ann.get('text', '')} (page {ann.get('page', '?')})\n"

                notes.append(note)
                print(f"  Extracted {len(annotations)} annotations")
            else:
                print(f"  No annotations found")

        # Write notes
        if args.output:
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("\n\n---\n\n".join(notes))

            print(f"\nNotes written to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: obsidian-ingest
# =============================================================================

def cmd_obsidian_ingest(args: argparse.Namespace) -> int:
    """Ingest Markdown files into Obsidian vault."""
    from berb.knowledge.obsidian_export import ObsidianExporter, ObsidianConfig

    print(f"Ingesting Markdown files from {args.input}")

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        return 1

    # Find all Markdown files
    md_files = list(input_dir.glob("**/*.md"))

    if not md_files:
        print("No Markdown files found")
        return 1

    print(f"Found {len(md_files)} Markdown files")

    # Configure Obsidian exporter
    config = ObsidianConfig(vault_path=args.vault)
    exporter = ObsidianExporter(config)

    try:
        ingested = 0

        for md_file in md_files:
            print(f"Processing: {md_file.name}")

            # Read content
            content = md_file.read_text(encoding='utf-8')

            # Extract metadata
            title = md_file.stem.replace("_", " ").title()

            # Ingest
            exporter.ingest_markdown_sync(
                content=content,
                title=title,
                source_file=str(md_file),
            )

            ingested += 1

        print(f"\nSuccessfully ingested {ingested} files into Obsidian vault")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: analyze-results
# =============================================================================

def cmd_analyze_results(args: argparse.Namespace) -> int:
    """Analyze experiment results and generate report."""
    from berb.agents.specialized import ExperimentAnalystAgent, AgentConfig

    print("Analyzing experiment results...")

    # Load data files
    data_files = [Path(f) for f in args.data]
    for df in data_files:
        if not df.exists():
            print(f"Error: Data file not found: {df}")
            return 1

    # Create agent
    config = AgentConfig(
        llm_client=None,  # Will use default
        verbose=args.verbose,
    )
    agent = ExperimentAnalystAgent(config)

    try:
        # Load data
        import pandas as pd

        dataframes = []
        for df_path in data_files:
            if df_path.suffix == '.csv':
                df = pd.read_csv(df_path)
            elif df_path.suffix in ('.xlsx', '.xls'):
                df = pd.read_excel(df_path)
            else:
                print(f"Warning: Unsupported format: {df_path}")
                continue

            dataframes.append(df)

        if not dataframes:
            print("No valid data files loaded")
            return 1

        print(f"Loaded {len(dataframes)} data files")

        # Generate analysis
        # Note: This would normally call the agent, but we'll create a simple report
        report = "# Experiment Analysis Report\n\n"
        report += f"## Data Summary\n\n"
        report += f"Analyzed {len(dataframes)} data files:\n\n"

        for i, df in enumerate(dataframes, 1):
            report += f"### Dataset {i}\n"
            report += f"- Shape: {df.shape[0]} rows × {df.shape[1]} columns\n"
            report += f"- Columns: {', '.join(df.columns[:10])}"
            if len(df.columns) > 10:
                report += f" ... and {len(df.columns) - 10} more"
            report += "\n\n"

        # Write report
        if args.output:
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(report, encoding='utf-8')
            print(f"Report written to: {output_file}")
        else:
            print(report)

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: rebuttal (already exists in CLI, but enhanced version here)
# =============================================================================

def cmd_rebuttal_enhanced(args: argparse.Namespace) -> int:
    """Generate enhanced rebuttal letter."""
    from berb.writing.rebuttal_generator import RebuttalGenerator
    from berb.writing.anti_ai import AntiAIEncoder

    print("Generating rebuttal letter...")

    manuscript = Path(args.manuscript)
    reviews_file = Path(args.reviews)

    if not manuscript.exists():
        print(f"Error: Manuscript not found: {manuscript}")
        return 1

    if not reviews_file.exists():
        print(f"Error: Reviews file not found: {reviews_file}")
        return 1

    try:
        # Read reviews
        reviews_text = reviews_file.read_text(encoding='utf-8')

        # Parse reviews (simple format: one review per section)
        reviews = []
        current_review = {"reviewer": "Unknown", "comments": []}

        for line in reviews_text.split('\n'):
            line = line.strip()
            if not line:
                continue

            if line.startswith('Reviewer'):
                if current_review["comments"]:
                    reviews.append(current_review)
                current_review = {"reviewer": line, "comments": []}
            elif line.startswith('-'):
                current_review["comments"].append(line[1:].strip())

        if current_review["comments"]:
            reviews.append(current_review)

        print(f"Parsed {len(reviews)} reviewer comments")

        # Generate rebuttal
        generator = RebuttalGenerator()

        # Simple rebuttal generation (would use LLM in full implementation)
        rebuttal = "# Rebuttal Letter\n\n"
        rebuttal += "Dear Area Chair and Reviewers,\n\n"
        rebuttal += "We thank the reviewers for their constructive feedback on our manuscript. "
        rebuttal += "Below we provide point-by-point responses to all comments.\n\n"
        rebuttal += "---\n\n"

        for review in reviews:
            rebuttal += f"## {review['reviewer']}\n\n"

            for i, comment in enumerate(review['comments'], 1):
                rebuttal += f"**Comment {i}:** {comment}\n\n"
                rebuttal += "**Response:** We appreciate this comment. "
                rebuttal += "[Detailed response would be generated by LLM]\n\n"

            rebuttal += "---\n\n"

        # Anti-AI editing
        if args.no_ai_check:
            encoder = AntiAIEncoder()
            import asyncio
            result = asyncio.run(encoder.analyze(rebuttal))

            if result.phrases:
                print(f"\nFound {len(result.phrases)} AI-like phrases to revise")
                rebuttal = result.revised_text

        # Write rebuttal
        output = Path(args.output) if args.output else Path("rebuttal.md")
        output.write_text(rebuttal, encoding='utf-8')
        print(f"Rebuttal letter written to: {output}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: mine-writing-patterns
# =============================================================================

def cmd_mine_writing_patterns(args: argparse.Namespace) -> int:
    """Extract writing patterns from corpus."""
    from berb.writing.pattern_memory import WritingPatternMiner

    print(f"Mining writing patterns from {args.corpus}")

    corpus_dir = Path(args.corpus)
    if not corpus_dir.exists():
        print(f"Error: Corpus directory not found: {corpus_dir}")
        return 1

    # Find all text files
    text_files = list(corpus_dir.glob("**/*.txt")) + list(corpus_dir.glob("**/*.md"))

    if not text_files:
        print("No text files found in corpus")
        return 1

    print(f"Found {len(text_files)} text files")

    try:
        # Load texts
        texts = []
        for tf in text_files[:args.max_files]:
            content = tf.read_text(encoding='utf-8')
            texts.append(content)

        print(f"Loaded {len(texts)} texts")

        # Mine patterns
        miner = WritingPatternMiner()

        patterns = miner.mine_patterns_batch(texts)

        print(f"\nMined {len(patterns)} writing patterns:")
        for i, pattern in enumerate(list(patterns)[:10], 1):
            print(f"  {i}. {pattern.get('type', 'unknown')}: {pattern.get('example', '')[:60]}")

        # Save patterns
        if args.output:
            import json
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(patterns, f, indent=2, ensure_ascii=False)

            print(f"\nPatterns saved to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: verify-citations
# =============================================================================

def cmd_verify_citations(args: argparse.Namespace) -> int:
    """Verify citation accuracy."""
    from berb.pipeline.citation_verification import CitationVerifier, VerifierConfig

    print(f"Verifying citations in {args.paper}")

    paper_file = Path(args.paper)
    if not paper_file.exists():
        print(f"Error: Paper not found: {paper_file}")
        return 1

    try:
        # Read paper
        paper_text = paper_file.read_text(encoding='utf-8')

        # Extract citations (simple regex for DOIs)
        import re
        doi_pattern = r'10\.\d{4,9}/[-._;()/:A-Z0-9]+'
        dois = re.findall(doi_pattern, paper_text, re.IGNORECASE)

        print(f"Found {len(dois)} DOI citations")

        # Verify citations
        config = VerifierConfig(
            enable_format_check=True,
            enable_api_check=not args.no_api_check,
            enable_info_check=True,
            enable_content_check=False,  # Skip LLM check for speed
        )

        verifier = CitationVerifier(config)

        results = []
        for doi in dois[:args.max_citations]:
            result = verifier.verify_doi_sync(doi)
            results.append(result)

            status = "✓" if result.get('valid', False) else "✗"
            print(f"  {status} {doi[:50]}")

        # Summary
        valid_count = sum(1 for r in results if r.get('valid', False))
        print(f"\nVerification complete: {valid_count}/{len(results)} valid citations")

        if args.output:
            import json
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2)

            print(f"Results saved to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: anti-ai-editing
# =============================================================================

def cmd_anti_ai_editing(args: argparse.Namespace) -> int:
    """Remove AI phrasing from text."""
    from berb.writing.anti_ai import AntiAIEncoder

    print(f"Editing {args.input} for AI-like phrasing...")

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        return 1

    try:
        # Read text
        text = input_file.read_text(encoding='utf-8')

        # Analyze and edit
        encoder = AntiAIEncoder(
            sensitivity=args.sensitivity,
            auto_replace=True,
        )

        import asyncio
        result = asyncio.run(encoder.analyze(text))

        print(f"Found {len(result.phrases)} AI-like phrases")
        print(f"AI score: {result.ai_score:.2f}")

        if result.suggestions:
            print("\nSuggestions:")
            for sug in result.suggestions:
                print(f"  - {sug}")

        # Write revised text
        output_file = Path(args.output) if args.output else input_file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(result.revised_text, encoding='utf-8')

        print(f"\nRevised text written to: {output_file}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command: obsidian-init
# =============================================================================

def cmd_obsidian_init(args: argparse.Namespace) -> int:
    """Bootstrap Obsidian knowledge base."""
    from berb.knowledge.obsidian_export import ObsidianExporter, ObsidianConfig

    vault_path = Path(args.vault).expanduser()

    print(f"Initializing Obsidian vault at: {vault_path}")

    if not vault_path.exists():
        print(f"Error: Vault directory not found: {vault_path}")
        print("Please create the directory first or check the path")
        return 1

    try:
        # Create Berb-specific folders
        folders = [
            "Knowledge",
            "Literature",
            "Writing",
            "Results",
            "Papers",
            "Templates",
        ]

        for folder in folders:
            (vault_path / folder).mkdir(exist_ok=True)
            print(f"  Created: {folder}/")

        # Create templates
        templates_dir = vault_path / "Templates"

        # Knowledge card template
        kc_template = """---
created: {{date}}
type: knowledge-card
tags: []
source: ""
---

# {{title}}

## Summary

<!-- One-paragraph summary -->

## Key Concepts

<!-- Bullet points of key concepts -->

## Related

<!-- Links to related notes -->

## References

<!-- Bibliographic references -->
"""

        (templates_dir / "Knowledge Card.md").write_text(kc_template, encoding='utf-8')

        # Literature note template
        lit_template = """---
created: {{date}}
type: literature-note
tags: []
doi: ""
zotero_link: ""
---

# {{title}}

## Citation

<!-- Full citation -->

## Summary

<!-- Paper summary -->

## Key Contributions

<!-- Bullet points -->

## Methods

<!-- Methodology description -->

## Results

<!-- Key results -->

## Notes

<!-- Your notes and critique -->

## Related

<!-- Links to related papers -->
"""

        (templates_dir / "Literature Note.md").write_text(lit_template, encoding='utf-8')

        # Experiment report template
        exp_template = """---
created: {{date}}
type: experiment-report
tags: []
experiment_id: ""
---

# {{title}}

## Hypothesis

<!-- What was tested -->

## Methods

<!-- Experimental setup -->

## Results

<!-- Results with figures -->

## Analysis

<!-- Statistical analysis -->

## Conclusion

<!-- What we learned -->

## Next Steps

<!-- Follow-up experiments -->
"""

        (templates_dir / "Experiment Report.md").write_text(exp_template, encoding='utf-8')

        print("\nCreated templates:")
        print("  - Knowledge Card.md")
        print("  - Literature Note.md")
        print("  - Experiment Report.md")

        # Create config file
        config_content = f"""# Berb-Obsidian Configuration

vault_path: "{vault_path}"
auto_export: true
knowledge_base:
  obsidian:
    enabled: true
    vault_path: "{vault_path}"
    auto_export: true
"""

        config_file = vault_path / "berb-config.yaml"
        config_file.write_text(config_content, encoding='utf-8')

        print(f"\nConfiguration file created: {config_file}")
        print("\nObsidian vault initialized successfully!")
        print("\nNext steps:")
        print("  1. Open vault in Obsidian")
        print("  2. Install recommended plugins:")
        print("     - Dataview")
        print("     - Templater")
        print("     - QuickAdd")
        print("  3. Run: berb research-init --topic 'Your topic'")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# Command registration helpers
# =============================================================================

def setup_claude_scholar_commands(parser: argparse._SubParsersAction) -> None:
    """
    Setup Claude Scholar enhancement commands.

    Args:
        parser: ArgumentParser subparsers
    """
    # Research init
    cmd = parser.add_parser(
        "research-init",
        help="Start Zotero-integrated research project",
    )
    cmd.add_argument("--topic", "-t", required=True, help="Research topic")
    cmd.add_argument("--output", "-o", default=".", help="Output directory")
    cmd.add_argument("--mcp-url", default="http://localhost:8765", help="Zotero MCP URL")
    cmd.add_argument("--zotero-api-key", default="", help="Zotero API key")

    # Zotero review
    cmd = parser.add_parser(
        "zotero-review",
        help="Review Zotero collection",
    )
    cmd.add_argument("--collection", "-c", required=True, help="Collection name")
    cmd.add_argument("--mcp-url", default="http://localhost:8765", help="Zotero MCP URL")

    # Zotero notes
    cmd = parser.add_parser(
        "zotero-notes",
        help="Batch-read papers and generate notes",
    )
    cmd.add_argument("--papers", nargs="+", required=True, help="Paper files")
    cmd.add_argument("--output", "-o", help="Output notes file")

    # Obsidian ingest
    cmd = parser.add_parser(
        "obsidian-ingest",
        help="Ingest Markdown files into Obsidian vault",
    )
    cmd.add_argument("--input", "-i", required=True, help="Input directory")
    cmd.add_argument("--vault", "-v", required=True, help="Obsidian vault path")

    # Analyze results
    cmd = parser.add_parser(
        "analyze-results",
        help="Analyze experiment results and generate report",
    )
    cmd.add_argument("--data", nargs="+", required=True, help="Data files")
    cmd.add_argument("--output", "-o", help="Output report file")
    cmd.add_argument("--verbose", action="store_true", help="Verbose output")

    # Rebuttal (enhanced)
    cmd = parser.add_parser(
        "rebuttal-enhanced",
        help="Generate enhanced rebuttal letter with AI-checking",
    )
    cmd.add_argument("--manuscript", required=True, help="Manuscript PDF")
    cmd.add_argument("--reviews", required=True, help="Reviewer comments file")
    cmd.add_argument("--output", "-o", help="Output file")
    cmd.add_argument("--no-ai-check", action="store_true", help="Skip AI phrasing check")

    # Mine writing patterns
    cmd = parser.add_parser(
        "mine-writing-patterns",
        help="Extract writing patterns from corpus",
    )
    cmd.add_argument("--corpus", required=True, help="Corpus directory")
    cmd.add_argument("--output", "-o", help="Output patterns file")
    cmd.add_argument("--max-files", type=int, default=100, help="Max files to process")

    # Verify citations
    cmd = parser.add_parser(
        "verify-citations",
        help="Verify citation accuracy",
    )
    cmd.add_argument("--paper", required=True, help="Paper file")
    cmd.add_argument("--output", "-o", help="Output results file")
    cmd.add_argument("--max-citations", type=int, default=50, help="Max citations to verify")
    cmd.add_argument("--no-api-check", action="store_true", help="Skip API verification")

    # Anti-AI editing
    cmd = parser.add_parser(
        "anti-ai-editing",
        help="Remove AI phrasing from text",
    )
    cmd.add_argument("--input", "-i", required=True, help="Input file")
    cmd.add_argument("--output", "-o", help="Output file")
    cmd.add_argument("--sensitivity", type=float, default=0.7, help="Detection sensitivity")

    # Obsidian init
    cmd = parser.add_parser(
        "obsidian-init",
        help="Bootstrap Obsidian knowledge base",
    )
    cmd.add_argument("--vault", "-v", required=True, help="Obsidian vault path")
