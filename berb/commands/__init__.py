"""Claude Scholar enhancement commands for Berb CLI.

This module provides 10 core commands for enhanced research workflow:
1. research-init - Start Zotero-integrated research
2. zotero-review - Review Zotero collection
3. zotero-notes - Batch-read papers → notes
4. obsidian-ingest - Ingest Markdown files
5. analyze-results - Experiment analysis + report
6. rebuttal-enhanced - Generate rebuttal with AI-checking
7. mine-writing-patterns - Extract writing patterns
8. verify-citations - Verify citation accuracy
9. anti-ai-editing - Remove AI phrasing
10. obsidian-init - Bootstrap Obsidian knowledge base

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from berb.commands.claude_scholar import (
    cmd_research_init,
    cmd_zotero_review,
    cmd_zotero_notes,
    cmd_obsidian_ingest,
    cmd_analyze_results,
    cmd_rebuttal_enhanced,
    cmd_mine_writing_patterns,
    cmd_verify_citations,
    cmd_anti_ai_editing,
    cmd_obsidian_init,
    setup_claude_scholar_commands,
)

__all__ = [
    # Command handlers
    "cmd_research_init",
    "cmd_zotero_review",
    "cmd_zotero_notes",
    "cmd_obsidian_ingest",
    "cmd_analyze_results",
    "cmd_rebuttal_enhanced",
    "cmd_mine_writing_patterns",
    "cmd_verify_citations",
    "cmd_anti_ai_editing",
    "cmd_obsidian_init",
    # Setup function
    "setup_claude_scholar_commands",
]
