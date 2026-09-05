#!/usr/bin/env python3
"""Block commits that add a plaintext API key.

Scans only ADDED lines in the staged diff, so a pre-existing key elsewhere
in a touched file does not block unrelated work. Exits non-zero on a hit;
`git commit --no-verify` is the deliberate bypass.

The generic `key = "value"` rule is the one that produces false positives,
so it ignores the three shapes this repo actually writes: an empty string,
an env var NAME (api_key_env: "OPENROUTER_API_KEY"), and a placeholder.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Vendor formats. Each is specific enough to stand alone as a finding.
VENDOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenRouter", re.compile(r"sk-or-v1-[a-f0-9]{32,}")),
    ("Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI", re.compile(r"sk-(?!or-v1-|ant-)[A-Za-z0-9_\-]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
)

# key = "value" / key: "value". The quotes are REQUIRED: an unquoted value is
# an identifier or expression (api_key=config.api_key, os.environ.get(...)),
# never a plaintext secret. Matching bare values produced 133 false positives
# against this repo's own history and would have blocked ordinary commits.
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b (?P<key> [a-z0-9_\-]* (?: api[_\-]?key | secret | token | password | passwd ) )
    \s* [:=] \s*
    (?P<quote>['"]) (?P<value> [^'"]{16,}) (?P=quote)
    """
)

# Words a real credential does not contain, but a fixture does.
FAKE_MARKER = re.compile(r"(?i)fake|dummy|example|placeholder|redacted|notreal|invalid")

# Values that look like a secret by length but are not one.
ENV_VAR_NAME = re.compile(r"^[A-Z][A-Z0-9_]{5,}$")
PLACEHOLDER = re.compile(
    r"(?i)^(your|xxx|todo|changeme|placeholder|example|dummy|fake|test|sample|redacted|\.\.\.)"
    r"|^\$|^\{\{|^<|^%|\.\.\.$|^\*+$"
)
# An env var name is the SAFE thing to commit, so a key named *_env is fine.
ENV_KEY_SUFFIX = re.compile(r"(?i)(_env|_env_var|_var|_name)$")

# Per-line opt out, for test fixtures and documented examples. Narrower than
# --no-verify, which switches the whole scan off for the entire commit.
ALLOWLIST_PRAGMA = "pragma: allowlist secret"


def is_placeholder(value: str) -> bool:
    return bool(
        not value
        or ENV_VAR_NAME.match(value)
        or PLACEHOLDER.search(value)
        or FAKE_MARKER.search(value)
        or set(value) <= {"x", "X", "0", "*", "."}
    )


def staged_additions() -> list[tuple[str, str]]:
    """Return (path, added_line) for every line the commit adds."""
    diff = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        errors="replace",
    ).stdout

    out: list[tuple[str, str]] = []
    path = "?"
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            out.append((path, line[1:]))
    return out


def findings(additions: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Return (path, reason, evidence) per suspected key."""
    hits: list[tuple[str, str, str]] = []
    for path, line in additions:
        if ALLOWLIST_PRAGMA in line:
            continue

        vendor_hit = False
        for vendor, pattern in VENDOR_PATTERNS:
            if match := pattern.search(line):
                if FAKE_MARKER.search(match.group(0)):
                    continue  # sk-fake-test-key and friends
                hits.append((path, f"{vendor} key", redact(match.group(0))))
                vendor_hit = True

        if vendor_hit:
            # A named vendor format is the better message; the generic rule
            # would only repeat the same secret with a vaguer reason.
            continue

        for match in ASSIGNMENT.finditer(line):
            key, value = match.group("key"), match.group("value")
            if ENV_KEY_SUFFIX.search(key) or is_placeholder(value):
                continue
            hits.append((path, f"{key} assigned a literal value", redact(value)))
    return hits


def redact(secret: str) -> str:
    """Never print a full key: the hook output lands in terminal scrollback."""
    return secret[:4] + "..." + secret[-2:] if len(secret) > 12 else "***"


def main() -> int:
    hits = findings(staged_additions())
    if not hits:
        return 0

    print("\nBlocked: staged changes look like they contain plaintext secrets.\n")
    seen = set()
    for path, reason, evidence in hits:
        if (path, reason, evidence) in seen:
            continue
        seen.add((path, reason, evidence))
        print(f"  {path}: {reason} ({evidence})")
    print(
        "\nMove the value to an environment variable and commit the variable NAME.\n"
        "If this is a false positive, commit with --no-verify.\n"
    )
    return 1


def _self_check() -> None:
    """Run with --self-check. Asserts the two cases that matter."""
    # Fixtures are built by concatenation so this file does not trip its own
    # scan; the pragma case below is checked explicitly instead.
    blocked = [
        ("config.yaml", 'api_key: "sk-or-v1-' + "a" * 40 + '"'),
        ("s.py", 'AWS = "AKIA' + "A" * 16 + '"'),
        ("s.py", 'password = "hunter2-' + 'correct-horse-battery"'),
    ]
    allowed = [
        ("config.yaml", 'api_key_env: "OPENROUTER_API_KEY"'),
        ("config.yaml", 'api_key: ""'),
        ("config.yaml", 'api_key: "your-key-here-goes-in-this-slot"'),
        ("s.py", 'token = os.environ["GITHUB_TOKEN"]'),
        ("s.py", 'password = "hunter2-' + 'correct-horse"  # ' + ALLOWLIST_PRAGMA),
        # Real lines from this repo's history that the first version wrongly
        # flagged: an unquoted value is an expression, not a secret.
        ("novelty.py", "topic, hypotheses_text, api_key=perplexity_api_key"),
        ("_literature.py", "s2_api_key=config.llm.s2_api_key,"),
        ("_literature.py", 'perplexity_api_key=os.environ.get(_pplx.api_key_env, ""),'),
        ("client.py", "api_key=str(config.llm.api_key)"),
        ("t.py", '"OPENAI_API_KEY": "sk-' + 'fake-test-key-should-not-leak",'),
    ]
    for path, line in blocked:
        assert findings([(path, line)]), f"should have blocked: {line}"
    for path, line in allowed:
        assert not findings([(path, line)]), f"false positive: {line}"
    print("self-check passed")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(main())
