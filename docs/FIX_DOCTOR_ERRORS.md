# Fix Berb Doctor Errors - Quick Guide

**Status:** 3 errors, 2 warnings  
**Time to fix:** 5 minutes

---

## Error 1: Config YAML Parse Error ❌

**Problem:** API keys added incorrectly (like environment variables instead of YAML)

**Fix:**

1. **Backup current config:**
   ```bash
   copy config.berb.yaml config.berb.yaml.backup
   ```

2. **Use the production config:**
   ```bash
   copy config.berb.production.yaml config.berb.yaml
   ```

3. **Or fix manually:** Open `config.berb.yaml` and remove lines like:
   ```yaml
   # REMOVE THESE (wrong format)
   PERPLEXITY_API_KEY=pplx-xxxxx
   OPENAI_API_KEY=sk-xxxxx
   ```

   API keys should be in `.env` file or set as environment variables, NOT in the YAML config.

---

## Error 2: LLM Base URL Empty ❌

**Fix:** Add to `config.berb.yaml`:

```yaml
llm:
  base_url: "https://openrouter.ai/api/v1"
```

---

## Error 3: API Key Empty ❌

**Option A: Set in .env file (Recommended)**

Create/edit `.env` file:
```bash
OPENROUTER_API_KEY=sk_or_xxxxx...
```

**Option B: Set in config**

Add to `config.berb.yaml`:
```yaml
llm:
  api_key: "sk_or_xxxxx..."  # Not recommended for production
```

**Option C: Set as environment variable**

```bash
set OPENROUTER_API_KEY=sk_or_xxxxx...  # Windows
export OPENROUTER_API_KEY=sk_or_xxxxx...  # Linux/Mac
```

---

## Warning 1: No Models Configured ⚠️

**Fix:** Add to `config.berb.yaml`:

```yaml
llm:
  primary_model: "qwen/qwen3.5-flash"
  fallback_models:
    - "minimax/minimax-m2.5:free"
    - "z-ai/glm-4.5-air:free"
```

---

## Warning 2: Sandbox Python Path Empty ⚠️

**Fix:** Add to `config.berb.yaml`:

```yaml
experiment:
  sandbox:
    # Windows:
    python_path: ".venv/Scripts/python.exe"
    
    # Linux/Mac:
    # python_path: ".venv/bin/python3"
```

---

## Quick Fix (All-in-One)

Run these commands:

```bash
cd E:\Documents\Vibe-Coding\Berb

# Backup old config
copy config.berb.yaml config.berb.yaml.backup

# Use production config
copy config.berb.production.yaml config.berb.yaml

# Set API key (get one at https://openrouter.ai)
set OPENROUTER_API_KEY=sk_or_xxxxx...

# Verify
berb doctor
```

---

## Get API Keys

### OpenRouter (Recommended - 11 providers, 1 key)

1. Go to: https://openrouter.ai
2. Sign up / Login
3. Go to: https://openrouter.ai/keys
4. Create key
5. Copy key
6. Set in `.env` or environment

### Alternative: Direct Providers

| Provider | Get Key At |
|----------|------------|
| Anthropic | https://console.anthropic.com |
| OpenAI | https://platform.openai.com |
| Google | https://makersuite.google.com |
| Perplexity | https://www.perplexity.ai/api |
| xAI (Grok) | https://console.x.ai |

---

## Verify Fix

After fixing, run:

```bash
berb doctor
```

Expected output:
```
✅ python_version: Python 3.12.10
✅ yaml_import: PyYAML import ok
✅ config_valid: Config YAML parse ok
✅ llm_connectivity: LLM base URL ok
✅ api_key_valid: API key valid
✅ model_chain: Models configured
✅ sandbox_python: Sandbox python path ok
✅ matplotlib: matplotlib import ok
✅ experiment_mode: Experiment mode: sandbox
✅ disk_space: Disk space OK
Result: PASS
```

---

## Still Having Issues?

### Check YAML Syntax

Use a YAML validator: https://www.yamllint.com/

### Check .env File

Make sure `.env` is in project root:
```
E:\Documents\Vibe-Coding\Berb\.env
```

With content:
```bash
OPENROUTER_API_KEY=sk_or_xxxxx...
```

### Check Python Path

Find your Python path:
```bash
where python
```

Use that path in config:
```yaml
experiment:
  sandbox:
    python_path: "C:\path\to\python.exe"
```

---

**Need help? Run:** `berb doctor` **after each fix to verify!**
