# Security Fixes Migration Guide

## Overview

This document describes the migration steps for three security fixes implemented in the Berb autonomous research pipeline:

| Fix | Severity | Description |
|-----|----------|-------------|
| **Fix #1** | Critical | HyperAgent Docker Sandbox |
| **Fix #2** | High | API Key Env Var Enforcement |
| **Fix #6** | Medium | LLM Rate Limiting |

---

## Fix #1: HyperAgent Docker Sandbox

### What Changed

The `TaskAgent` in `berb/hyperagent/task_agent.py` now executes all code in isolated Docker containers instead of running directly on the host system.

### Security Benefits

- **No network access**: Containers run with `network_disabled=True`
- **Read-only filesystem**: Code mounted as read-only
- **Memory/CPU limits**: Prevents resource exhaustion
- **No privilege escalation**: `no-new-privileges` security option
- **Dropped capabilities**: All Linux capabilities dropped

### Migration Steps

#### Step 1: Install Docker

```bash
# Windows
# Download and install Docker Desktop from https://www.docker.com/products/docker-desktop

# macOS
brew install --cask docker

# Linux (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install docker.io
sudo usermod -aG docker $USER
```

#### Step 2: Install Python Docker Library

```bash
pip install docker
```

#### Step 3: Pull Default Image

```bash
docker pull python:3.12-slim
```

#### Step 4: Update Configuration (Optional)

If you want to customize the sandbox settings, add to your `config.berb.yaml`:

```yaml
hyperagent:
  task_agent:
    docker_image: "python:3.12-slim"  # Or your custom image
    docker_memory_mb: 512             # Memory limit
    docker_cpu_quota: 50000           # 50% of 1 CPU
    docker_network_disabled: true     # No network access
    sandbox_enabled: true             # Enable sandboxing
    fallback_to_simulated: true       # Fallback if Docker unavailable
```

#### Step 5: Verify Docker is Working

```bash
# Test Docker connectivity
docker run --rm python:3.12-slim python -c "print('Docker OK')"

# Run Berb doctor to verify
berb doctor
```

### Backward Compatibility

- If Docker is unavailable, the system falls back to simulated execution
- The `sandbox_enabled` flag can be set to `false` for development (not recommended for production)

---

## Fix #2: API Key Env Var Enforcement

### What Changed

The configuration validation now **rejects** plaintext API keys stored in config files. All API keys must be referenced via environment variable names.

### Security Benefits

- **No credential leakage**: API keys never stored in config files
- **Git-safe**: Config files can be committed without secrets
- **Audit-friendly**: Environment variables are standard practice

### Migration Steps

#### Step 1: Remove Plaintext Keys from Config

**BEFORE (INSECURE):**
```yaml
llm:
  provider: "openai"
  base_url: "https://api.openai.com/v1"
  api_key: "sk-proj-abc123..."  # ❌ SECURITY VIOLATION
  primary_model: "gpt-4o"
```

**AFTER (SECURE):**
```yaml
llm:
  provider: "openai"
  base_url: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"  # ✅ Reference env var
  primary_model: "gpt-4o"
```

#### Step 2: Set Environment Variables

**Windows (PowerShell):**
```powershell
# Permanent (user scope)
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-proj-abc123...", "User")

# Temporary (current session)
$env:OPENAI_API_KEY = "sk-proj-abc123..."
```

**macOS/Linux:**
```bash
# Permanent (add to ~/.bashrc or ~/.zshrc)
export OPENAI_API_KEY="sk-proj-abc123..."

# Temporary (current session)
export OPENAI_API_KEY="sk-proj-abc123..."
```

#### Step 3: Verify Configuration

```bash
# Check config validation
berb doctor

# Should show:
# ✅ No plaintext API keys detected
```

### Error Messages

If you try to run with a plaintext key, you'll see:

```
SECURITY VIOLATION: Plaintext API key in llm.api_key.
Remove this field and use llm.api_key_env instead.
Example: api_key_env: "OPENAI_API_KEY"
```

### Other API Keys

The validation also warns about other plaintext keys:

| Field | Status | Recommendation |
|-------|--------|----------------|
| `llm.s2_api_key` | ⚠️ Warning | Use env var |
| `web_search.tavily_api_key` | ⚠️ Warning | Use `tavily_api_key_env` |
| `metaclaw_bridge.fallback_api_key` | ⚠️ Warning | Use env var |

---

## Fix #6: LLM Rate Limiting

### What Changed

The `LLMClient` now includes a token bucket rate limiter to prevent quota exhaustion from runaway pipelines.

### Security Benefits

- **Cost protection**: Prevents accidental API overuse
- **Quota preservation**: Ensures pipeline doesn't exhaust daily limits
- **Graceful degradation**: Waits when limits hit instead of failing

### Migration Steps

#### Step 1: Default Configuration (No Changes Needed)

The rate limiter is enabled by default with reasonable limits:

- **60 requests per minute**
- **90,000 tokens per minute**

#### Step 2: Customize Limits (Optional)

Add to your `config.berb.yaml`:

```yaml
llm:
  rate_limit_enabled: true
  rate_limit_requests_per_minute: 30   # Lower for budget-conscious
  rate_limit_tokens_per_minute: 40000  # ~$0.10/min with GPT-4o
```

#### Step 3: Disable Rate Limiting (Not Recommended)

```yaml
llm:
  rate_limit_enabled: false  # ⚠️ Not recommended for production
```

### Monitoring Rate Limits

You can check rate limiter status programmatically:

```python
from berb.llm.client import LLMClient

client = LLMClient(config)
status = client.get_rate_limiter_status()

print(f"Requests available: {status['request_tokens_available']}")
print(f"Tokens available: {status['token_tokens_available']}")
```

### Error Messages

When rate limit is exceeded:

```
Rate limit exceeded. Would need to wait 45.2s (exceeds timeout of 300s).
Consider reducing request frequency or increasing limits.
```

---

## Verification Checklist

After migration, verify all fixes are working:

```bash
# 1. Run security tests
pytest tests/test_security_fixes.py -v

# 2. Run Berb doctor
berb doctor

# 3. Check Docker connectivity
docker ps

# 4. Verify env vars are set
echo $OPENAI_API_KEY  # macOS/Linux
echo %OPENAI_API_KEY%  # Windows
```

---

## Rollback Instructions

If you need to rollback any fix:

### Fix #1 Rollback (Docker Sandbox)

```yaml
hyperagent:
  task_agent:
    sandbox_enabled: false  # ⚠️ Security risk
```

### Fix #2 Rollback (API Key Enforcement)

Not recommended - the validation will reject plaintext keys. To bypass:

1. Edit `berb/config.py`
2. Remove the plaintext key check in `validate_config()`
3. ⚠️ This removes security protection

### Fix #6 Rollback (Rate Limiting)

```yaml
llm:
  rate_limit_enabled: false
```

---

## Support

For questions or issues:

1. Check `docs/SECURITY_FIXES.md` for detailed documentation
2. Run `berb doctor` for environment diagnostics
3. Review test failures in `tests/test_security_fixes.py`

---

## Changelog

| Date | Fix | Change |
|------|-----|--------|
| 2026-03-28 | #1 | Added Docker sandbox to TaskAgent |
| 2026-03-28 | #2 | Added API key env var enforcement |
| 2026-03-28 | #6 | Added LLM rate limiting |
| 2026-03-28 | Tests | Added 25 security tests |