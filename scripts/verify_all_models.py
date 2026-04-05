#!/usr/bin/env python3
"""
Verify all recommended models are available on OpenRouter.

This script checks the availability of all 27 recommended models
across 11 providers for the extended reasoning implementation.

Usage:
    python scripts/verify_all_models.py

Output:
    - Console summary of available/unavailable models
    - JSON report: scripts/model_verification_report.json
    - Markdown report: docs/MODEL_VERIFICATION_REPORT.md

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Models to verify (from EXTENDED_MODEL_COMPARISON.md)
MODELS_TO_VERIFY = {
    # =========================================================================
    # BUDGET TIER (FREE) - P0 Priority
    # =========================================================================
    "minimax/minimax-m2.5:free": {
        "provider": "MiniMax",
        "priority": "P0",
        "use_case": "Budget everything (80.2% SWE-Bench)",
    },
    "z-ai/glm-4.5-air:free": {
        "provider": "GLM",
        "priority": "P0",
        "use_case": "Free general tasks (131K context)",
    },
    "qwen/qwen3-coder-480b-a35b:free": {
        "provider": "Qwen",
        "priority": "P0",
        "use_case": "Free premium coding (480B params)",
    },
    
    # =========================================================================
    # VALUE TIER - P0 Priority
    # =========================================================================
    "qwen/qwen3.5-flash": {
        "provider": "Qwen",
        "priority": "P0",
        "use_case": "Best value long-context (1M, $0.065/$0.26)",
    },
    "qwen/qwen3-coder-next": {
        "provider": "Qwen",
        "priority": "P0",
        "use_case": "Best coding value ($0.12/$0.75)",
    },
    "xiaomi/mimo-v2-flash": {
        "provider": "MiMo",
        "priority": "P0",
        "use_case": "#1 open-source SWE-bench ($0.09/$0.29)",
    },
    "minimax/minimax-m2.5": {
        "provider": "MiniMax",
        "priority": "P0",
        "use_case": "Paid tier same model ($0.19/$1.15)",
    },
    
    # =========================================================================
    # PREMIUM TIER - P0 Priority
    # =========================================================================
    "xiaomi/mimo-v2-pro": {
        "provider": "MiMo",
        "priority": "P0",
        "use_case": "Best premium value (~Opus 4.6, $1/$3)",
    },
    "qwen/qwen3.5-397b-a17b": {
        "provider": "Qwen",
        "priority": "P0",
        "use_case": "Elite performance ($0.39/$2.34)",
    },
    "qwen/qwen3-max-thinking": {
        "provider": "Qwen",
        "priority": "P0",
        "use_case": "Complex reasoning ($0.78/$3.90)",
    },
    "moonshotai/kimi-k2.5": {
        "provider": "Kimi",
        "priority": "P0",
        "use_case": "Visual coding ($0.42/$2.20)",
    },
    
    # =========================================================================
    # SPECIALIZED - P0 Priority
    # =========================================================================
    "x-ai/grok-4.20-multi-agent-beta": {
        "provider": "xAI",
        "priority": "P0",
        "use_case": "Multi-agent Jury (2M context, $2/$6)",
    },
    "x-ai/grok-4.20-beta": {
        "provider": "xAI",
        "priority": "P0",
        "use_case": "Low hallucination ($2/$6)",
    },
    "perplexity/sonar-pro-search": {
        "provider": "Perplexity",
        "priority": "P0",
        "use_case": "Built-in search ($3/$15 + $18/1k)",
    },
    "perplexity/sonar-reasoning-pro": {
        "provider": "Perplexity",
        "priority": "P0",
        "use_case": "Search + reasoning ($2/$8)",
    },
    
    # =========================================================================
    # FALLBACK (Existing) - P2 Priority
    # =========================================================================
    "deepseek/deepseek-v3.2": {
        "provider": "DeepSeek",
        "priority": "P2",
        "use_case": "Fallback value ($0.26/$0.38)",
    },
    "deepseek/deepseek-r1": {
        "provider": "DeepSeek",
        "priority": "P2",
        "use_case": "Fallback reasoning ($0.70/$2.50)",
    },
    "google/gemini-3.1-flash-lite-preview": {
        "provider": "Google",
        "priority": "P2",
        "use_case": "Fallback long-context ($0.25/$1.50)",
    },
    "anthropic/claude-sonnet-4.6": {
        "provider": "Anthropic",
        "priority": "P3",
        "use_case": "Premium fallback ($3/$15)",
    },
    "anthropic/claude-opus-4.6": {
        "provider": "Anthropic",
        "priority": "P3",
        "use_case": "Elite fallback ($5/$25)",
    },
    "openai/gpt-5.2-codex": {
        "provider": "OpenAI",
        "priority": "P3",
        "use_case": "Coding fallback ($1.75/$14)",
    },
    
    # =========================================================================
    # ADDITIONAL VALUE MODELS - P1 Priority
    # =========================================================================
    "z-ai/glm-4.7-flash": {
        "provider": "GLM",
        "priority": "P1",
        "use_case": "Budget long-context ($0.06/$0.40)",
    },
    "z-ai/glm-5": {
        "provider": "GLM",
        "priority": "P1",
        "use_case": "Agent flagship ($0.72/$2.30)",
    },
    "qwen/qwen3.5-plus": {
        "provider": "Qwen",
        "priority": "P1",
        "use_case": "Balanced value ($0.26/$1.56)",
    },
    "qwen/qwen3.5-35b-a3b": {
        "provider": "Qwen",
        "priority": "P1",
        "use_case": "MoE value ($0.16/$1.30)",
    },
    "moonshotai/kimi-k2-thinking": {
        "provider": "Kimi",
        "priority": "P1",
        "use_case": "Reasoning ($0.47/$2.00)",
    },
    "x-ai/grok-4.1-fast": {
        "provider": "xAI",
        "priority": "P1",
        "use_case": "Budget 2M context ($0.20/$0.50)",
    },
}


async def verify_model(
    client: httpx.AsyncClient,
    model_id: str,
    api_key: str,
) -> dict:
    """Verify single model availability."""
    try:
        response = await client.get(
            f"https://openrouter.ai/api/v1/models/{model_id}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/georgehadji/berb",
                "X-Title": "Berb Reasoner Model Verification",
            },
            timeout=15.0,
        )
        
        if response.status_code == 200:
            data = response.json()
            pricing = data.get("pricing", {})
            return {
                "model": model_id,
                "status": "available",
                "context_window": data.get("context_length", "unknown"),
                "input_price": pricing.get("prompt", "unknown"),
                "output_price": pricing.get("completion", "unknown"),
                "description": data.get("description", "")[:100] if data.get("description") else "",
            }
        elif response.status_code == 404:
            return {
                "model": model_id,
                "status": "not_found",
                "error": "Model not found on OpenRouter",
            }
        elif response.status_code == 401:
            return {
                "model": model_id,
                "status": "auth_error",
                "error": "Invalid API key",
            }
        else:
            return {
                "model": model_id,
                "status": "error",
                "error": f"HTTP {response.status_code}: {response.text[:100]}",
            }
            
    except httpx.TimeoutException:
        return {
            "model": model_id,
            "status": "timeout",
            "error": "Request timed out",
        }
    except httpx.RequestError as e:
        return {
            "model": model_id,
            "status": "network_error",
            "error": str(e)[:100],
        }
    except Exception as e:
        return {
            "model": model_id,
            "status": "error",
            "error": f"Unexpected: {str(e)[:100]}",
        }


async def verify_all_models(api_key: str) -> List[dict]:
    """Verify all models concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [
            verify_model(client, model_id, api_key)
            for model_id in MODELS_TO_VERIFY.keys()
        ]
        results = await asyncio.gather(*tasks)
    return list(results)


def generate_summary(results: List[dict]) -> dict:
    """Generate verification summary."""
    by_priority = {"P0": [], "P1": [], "P2": [], "P3": []}
    by_provider = {}
    by_status = {"available": [], "not_found": [], "error": [], "other": []}
    
    for result in results:
        model_id = result["model"]
        info = MODELS_TO_VERIFY.get(model_id, {})
        priority = info.get("priority", "P3")
        provider = info.get("provider", "Unknown")
        
        # Group by priority
        by_priority[priority].append(result)
        
        # Group by provider
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(result)
        
        # Group by status
        status = result["status"]
        if status == "available":
            by_status["available"].append(result)
        elif status == "not_found":
            by_status["not_found"].append(result)
        elif status.endswith("_error"):
            by_status["error"].append(result)
        else:
            by_status["other"].append(result)
    
    return {
        "total_models": len(results),
        "available_count": len(by_status["available"]),
        "unavailable_count": len(by_status["not_found"]) + len(by_status["error"]),
        "by_priority": by_priority,
        "by_provider": by_provider,
        "by_status": by_status,
    }


def print_console_report(summary: dict) -> None:
    """Print summary to console."""
    print("\n" + "=" * 70)
    print("MODEL VERIFICATION REPORT")
    print("=" * 70)
    print(f"\nTotal Models: {summary['total_models']}")
    print(f"✅ Available: {summary['available_count']} ({summary['available_count']/summary['total_models']*100:.1f}%)")
    print(f"❌ Unavailable: {summary['unavailable_count']} ({summary['unavailable_count']/summary['total_models']*100:.1f}%)")
    
    # By priority
    print("\n" + "-" * 70)
    print("BY PRIORITY")
    print("-" * 70)
    for priority in ["P0", "P1", "P2", "P3"]:
        models = summary["by_priority"][priority]
        available = sum(1 for m in models if m["status"] == "available")
        print(f"\n{priority} ({len(models)} models): {available} available")
        for m in models:
            icon = "✅" if m["status"] == "available" else "❌"
            print(f"  {icon} {m['model']}: {m['status']}")
    
    # By provider
    print("\n" + "-" * 70)
    print("BY PROVIDER")
    print("-" * 70)
    for provider, models in sorted(summary["by_provider"].items()):
        available = sum(1 for m in models if m["status"] == "available")
        print(f"\n{provider} ({len(models)} models): {available} available")
        for m in models:
            icon = "✅" if m["status"] == "available" else "❌"
            print(f"  {icon} {m['model']}: {m['status']}")
    
    # Unavailable details
    unavailable = summary["by_status"]["not_found"] + summary["by_status"]["error"]
    if unavailable:
        print("\n" + "-" * 70)
        print("UNAVAILABLE MODELS (Action Required)")
        print("-" * 70)
        for m in unavailable:
            info = MODELS_TO_VERIFY.get(m["model"], {})
            print(f"\n❌ {m['model']}")
            print(f"   Priority: {info.get('priority', 'N/A')}")
            print(f"   Use Case: {info.get('use_case', 'N/A')}")
            print(f"   Error: {m.get('error', 'Unknown')}")
            print(f"   Fallback: Consider {info.get('fallback', 'See documentation')}")
    
    print("\n" + "=" * 70)


def generate_json_report(summary: dict, results: List[dict]) -> dict:
    """Generate JSON report."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "results": results,
        "models_config": MODELS_TO_VERIFY,
    }


def generate_markdown_report(summary: dict, results: List[dict]) -> str:
    """Generate Markdown report for docs/."""
    md = []
    md.append("# Model Verification Report")
    md.append("")
    md.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}")
    md.append("")
    md.append("## Summary")
    md.append("")
    md.append(f"- **Total Models:** {summary['total_models']}")
    md.append(f"- **✅ Available:** {summary['available_count']} ({summary['available_count']/summary['total_models']*100:.1f}%)")
    md.append(f"- **❌ Unavailable:** {summary['unavailable_count']} ({summary['unavailable_count']/summary['total_models']*100:.1f}%)")
    md.append("")
    
    # By priority table
    md.append("## By Priority")
    md.append("")
    md.append("| Priority | Total | Available | Unavailable |")
    md.append("|----------|-------|-----------|-------------|")
    for priority in ["P0", "P1", "P2", "P3"]:
        models = summary["by_priority"][priority]
        available = sum(1 for m in models if m["status"] == "available")
        unavailable = len(models) - available
        md.append(f"| {priority} | {len(models)} | {available} | {unavailable} |")
    md.append("")
    
    # Detailed results
    md.append("## Detailed Results")
    md.append("")
    md.append("| Model | Provider | Priority | Status | Context | Price (In/Out) |")
    md.append("|-------|----------|----------|--------|---------|----------------|")
    for result in results:
        model_id = result["model"]
        info = MODELS_TO_VERIFY.get(model_id, {})
        status_icon = "✅" if result["status"] == "available" else "❌"
        context = result.get("context_window", "N/A")
        pricing = f"${result.get('input_price', 'N/A')}/${result.get('output_price', 'N/A')}" if result["status"] == "available" else "N/A"
        md.append(f"| {model_id} | {info.get('provider', 'N/A')} | {info.get('priority', 'N/A')} | {status_icon} {result['status']} | {context} | {pricing} |")
    md.append("")
    
    # Unavailable models
    unavailable = summary["by_status"]["not_found"] + summary["by_status"]["error"]
    if unavailable:
        md.append("## Unavailable Models - Action Required")
        md.append("")
        for m in unavailable:
            info = MODELS_TO_VERIFY.get(m["model"], {})
            md.append(f"### ❌ {m['model']}")
            md.append(f"- **Priority:** {info.get('priority', 'N/A')}")
            md.append(f"- **Use Case:** {info.get('use_case', 'N/A')}")
            md.append(f"- **Error:** {m.get('error', 'Unknown')}")
            md.append(f"- **Recommended Fallback:** See EXTENDED_MODEL_COMPARISON.md")
            md.append("")
    
    return "\n".join(md)


async def main():
    """Main entry point."""
    # Get API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Try to load from .env file
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    
    if not api_key or api_key.startswith("sk_or_xxx"):
        print("ERROR: OPENROUTER_API_KEY not set.")
        print("")
        print("Please set your OpenRouter API key:")
        print("  1. Copy .env.example to .env")
        print("  2. Edit .env and set OPENROUTER_API_KEY=sk_or_xxxxx...")
        print("  3. Re-run this script")
        print("")
        print("Sign up at: https://openrouter.ai")
        sys.exit(1)
    
    print("Verifying models on OpenRouter...")
    print(f"API Key: {api_key[:10]}...{api_key[-5:]}")
    print("")
    
    # Verify all models
    results = await verify_all_models(api_key)
    
    # Generate summary
    summary = generate_summary(results)
    
    # Print console report
    print_console_report(summary)
    
    # Save JSON report
    json_report = generate_json_report(summary, results)
    json_path = Path(__file__).resolve().parent / "model_verification_report.json"
    json_path.write_text(json.dumps(json_report, indent=2))
    print(f"\nJSON report saved to: {json_path}")
    
    # Save Markdown report
    md_report = generate_markdown_report(summary, results)
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)
    md_path = docs_dir / "MODEL_VERIFICATION_REPORT.md"
    md_path.write_text(md_report)
    print(f"Markdown report saved to: {md_path}")
    
    # Exit with error if P0 models unavailable
    p0_unavailable = [
        m for m in summary["by_priority"]["P0"]
        if m["status"] != "available"
    ]
    if p0_unavailable:
        print(f"\n⚠️  WARNING: {len(p0_unavailable)} P0 models unavailable!")
        print("Review the report and update fallback configurations.")
        sys.exit(1)
    else:
        print("\n✅ All P0 models available! Ready for implementation.")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
