# Discover seed papers with Parallel Search MCP

Use [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
in Claude Code to find candidate papers, inspect their landing pages, and locate
public PDFs before starting a Berb run. Search uses Fast mode on the free anonymous
endpoint; no Parallel account or API key is required. Free access has rate limits.

This is a manual preparation workflow. Parallel runs in Claude Code, outside
Berb's pipeline. Berb continues to use its configured scholarly search and LLM
settings. The handoff is a set of PDFs passed to the existing `berb run --upload`
option; adding the server does not make Berb call Parallel automatically.

## 1. Connect Claude Code

You need [Claude Code](https://code.claude.com/docs/en/overview) installed and
configured, plus a working [Berb installation](../README.md#installation) and LLM
configuration. Run these commands from your Berb checkout:

```bash
claude mcp add --transport http --scope local parallel-search https://search.parallel.ai/mcp
claude mcp get parallel-search
```

Local scope keeps this server configuration private to you in this project. If
`parallel-search` is already configured, inspect it with `claude mcp get` before
adding anything; keep an existing setup or choose a different server name.

Start `claude` from the same directory and run `/mcp` to check the connection.
The server exposes `web_search` for finding sources and `web_fetch` for reading
specific URLs. See the [Claude Code MCP guide](https://code.claude.com/docs/en/mcp)
for connection and configuration details.

## 2. Find and check candidate sources

For example, ask Claude Code:

```text
Use the parallel-search web_search tool to find primary papers on evaluating
retrieval-augmented generation, including retrieval quality and groundedness.
Use related queries for benchmark datasets and evaluation methods. Prefer
publisher, arXiv, and author or project pages.

Use web_fetch on the most relevant landing pages when search excerpts are not
enough. For each candidate, report its title, authors, publication or submission
date, DOI or arXiv ID, landing-page URL, and any public PDF link. Distinguish
preprints from peer-reviewed papers and project documentation. Check dates
against the page text, and mark missing information instead of guessing.

Suggest a small seed-paper shortlist and a focused research question. Keep
source URLs and short supporting excerpts in the notes so I can review them.
Do not start a Berb run yet.
```

Review the shortlist yourself. Follow the primary links to confirm the paper's
identity, version, relevance, and PDF availability. A search result or fetched
excerpt is a lead, not proof that a citation or scientific claim is correct.

Download the selected, publicly accessible paper PDFs from their source sites
into a local directory such as `inputs/papers/`. Keep a separate record of the
landing-page URLs, identifiers, versions, and access dates for citation checks.
Fetching a landing page through MCP does not save a PDF to disk.

## 3. Include the reviewed PDFs in Berb

In your existing Berb virtual environment, install PDF support from the checkout:

```bash
pip install -e ".[pdf]"
```

After downloading a paper as `inputs/papers/seed-paper.pdf`, run:

```bash
berb run --topic "Evaluate retrieval quality and groundedness in retrieval-augmented generation" \
  --upload inputs/papers/seed-paper.pdf
```

Replace the topic and filename with your reviewed choices. `--upload` accepts
multiple file paths. Berb uses your existing config; pass `--config path/to/config.yaml`
if you normally select one explicitly. Your configured approval behavior still
applies.

During `LITERATURE_COLLECT` (stage 4), Berb ingests the uploaded PDFs alongside its
search candidates and skips titles already present in the candidate list. They
still go through downstream literature screening. Uploading a paper does not
guarantee that it will appear in the final bibliography.

Use readable, text-based PDFs. PDF ingestion needs PyMuPDF from the `pdf` extra;
scanned documents need OCR outside this workflow. Markdown source notes and URLs
are not PDF uploads and are not imported by this option. Keep the source record
for manual citation verification, since extracted metadata can be incomplete.

## Troubleshooting and removal

- If the server is missing or disconnected, run `claude mcp get parallel-search`
  from the same checkout and check `/mcp` in Claude Code.
- If a search or fetch is rate limited, wait before retrying. Higher limits and
  authentication options are covered in the [Parallel setup guide](https://docs.parallel.ai/integrations/mcp/search-mcp).
- If a PDF is skipped, check that the path exists, ends in `.pdf`, and opens as a
  readable document. Install the `pdf` extra in the environment running Berb.

To remove only the local server added above:

```bash
claude mcp remove --scope local parallel-search
```
