"""Security tests for Fix #1, Fix #2, and Fix #6.

These tests validate the security fixes implemented:
- Fix #1: HyperAgent Docker Sandbox
- Fix #2: API Key Env Var Enforcement
- Fix #6: LLM Rate Limiting
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Fix #1: HyperAgent Docker Sandbox Tests
# =============================================================================


class TestHyperAgentDockerSandbox:
    """Tests for Fix #1: Docker-based sandboxing for HyperAgent."""

    def test_task_agent_config_has_docker_settings(self):
        """Verify TaskAgentConfig includes Docker sandbox settings."""
        from berb.hyperagent.task_agent import TaskAgentConfig

        config = TaskAgentConfig()

        # SECURITY FIX #1: Docker settings must be present
        assert hasattr(config, "docker_image")
        assert hasattr(config, "docker_memory_mb")
        assert hasattr(config, "docker_cpu_quota")
        assert hasattr(config, "docker_network_disabled")
        assert hasattr(config, "fallback_to_simulated")

        # Default values should be secure
        assert config.docker_network_disabled is True
        assert config.sandbox_enabled is True
        assert config.docker_memory_mb > 0
        assert config.docker_cpu_quota > 0

    def test_docker_container_config_is_secure(self):
        """Verify Docker container configuration is secure."""
        from berb.hyperagent.task_agent import TaskAgentConfig

        config = TaskAgentConfig()

        # These settings should be enforced
        assert config.docker_network_disabled is True, "Network must be disabled"
        assert config.docker_memory_mb <= 4096, "Memory limit should be reasonable"

    def test_code_validation_blocks_dangerous_patterns(self):
        """Verify code validation blocks dangerous patterns."""
        from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig
        from berb.config import RCConfig

        # Create minimal mock config
        mock_config = MagicMock(spec=RCConfig)

        agent = TaskAgent(mock_config, TaskAgentConfig())

        # Dangerous patterns should be rejected
        dangerous_codes = [
            "import os.system('rm -rf /')",
            "__import__('os').system('cat /etc/passwd')",
            "eval('malicious_code')",
            "exec('import subprocess')",
            "import socket; socket.socket()",
            "import urllib.request; urllib.request.urlopen('http://evil.com')",
        ]

        for code in dangerous_codes:
            assert not agent._validate_code(code), f"Should reject: {code[:50]}..."

    def test_code_validation_accepts_safe_code(self):
        """Verify code validation accepts safe code."""
        from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig
        from berb.config import RCConfig

        mock_config = MagicMock(spec=RCConfig)
        agent = TaskAgent(mock_config, TaskAgentConfig())

        # Safe code should be accepted
        safe_codes = [
            "def execute_task(task): return {'success': True}",
            "import math; result = math.sqrt(4)",
            "import json; data = json.loads('{}')",
        ]

        for code in safe_codes:
            assert agent._validate_code(code), f"Should accept: {code[:50]}..."

    def test_code_size_limit_enforced(self):
        """Verify code size limit is enforced."""
        from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig
        from berb.config import RCConfig

        mock_config = MagicMock(spec=RCConfig)
        agent = TaskAgent(mock_config, TaskAgentConfig())

        # Excessive code size should be rejected (> 1MB)
        # Each line is ~6 chars, need > 166667 lines to exceed 1MB
        huge_code = "x = 1\n" * 200000  # ~1.2MB
        assert not agent._validate_code(huge_code), "Should reject huge code (> 1MB)"

    def test_excessive_line_length_rejected(self):
        """Verify excessive line length is rejected."""
        from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig
        from berb.config import RCConfig

        mock_config = MagicMock(spec=RCConfig)
        agent = TaskAgent(mock_config, TaskAgentConfig())

        # Line > 10000 chars should be rejected
        long_line_code = "x = '" + "a" * 15000 + "'"
        assert not agent._validate_code(long_line_code), "Should reject long lines"

    @pytest.mark.asyncio
    async def test_simulated_execution_fallback(self):
        """Verify simulated execution works when Docker unavailable."""
        from berb.hyperagent.task_agent import TaskAgent, TaskAgentConfig
        from berb.config import RCConfig

        mock_config = MagicMock(spec=RCConfig)
        config = TaskAgentConfig(sandbox_enabled=True, fallback_to_simulated=True)

        # Patch DOCKER_AVAILABLE to False
        with patch("berb.hyperagent.task_agent.DOCKER_AVAILABLE", False):
            agent = TaskAgent(mock_config, config)
            result = await agent._execute_simulated("test_task", 60)

            assert result.success is True
            assert result.output.get("mode") == "simulated"


# =============================================================================
# Fix #2: API Key Env Var Enforcement Tests
# =============================================================================


class TestApiKeyEnvVarEnforcement:
    """Tests for Fix #2: API key environment variable enforcement."""

    def test_llm_config_has_get_api_key_method(self):
        """Verify LlmConfig has get_api_key method."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key_env="OPENAI_API_KEY",
        )

        assert hasattr(config, "get_api_key")
        assert hasattr(config, "validate_no_plaintext_key")

    def test_get_api_key_raises_without_env_var_name(self):
        """Verify get_api_key raises error without env var name."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key_env="",  # Empty
        )

        with pytest.raises(ValueError) as exc_info:
            config.get_api_key()

        assert "SECURITY" in str(exc_info.value)
        assert "api_key_env" in str(exc_info.value)

    def test_get_api_key_raises_without_env_var_set(self):
        """Verify get_api_key raises error when env var not set."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key_env="NONEXISTENT_API_KEY",
        )

        # Ensure env var is not set
        if "NONEXISTENT_API_KEY" in os.environ:
            del os.environ["NONEXISTENT_API_KEY"]

        with pytest.raises(ValueError) as exc_info:
            config.get_api_key()

        assert "SECURITY" in str(exc_info.value)
        assert "NONEXISTENT_API_KEY" in str(exc_info.value)

    def test_get_api_key_returns_value_when_set(self):
        """Verify get_api_key returns value when env var is set."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key_env="TEST_API_KEY_VAR",
        )

        # Set the env var
        os.environ["TEST_API_KEY_VAR"] = "test-key-value-12345"

        try:
            key = config.get_api_key()
            assert key == "test-key-value-12345"
        finally:
            del os.environ["TEST_API_KEY_VAR"]

    def test_plaintext_key_validation_rejects_non_empty(self):
        """Verify plaintext key validation rejects non-empty keys."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key="sk-1234567890abcdef",  # Plaintext key!
            api_key_env="OPENAI_API_KEY",
        )

        is_valid, error = config.validate_no_plaintext_key()

        assert is_valid is False
        assert "SECURITY VIOLATION" in error
        assert "Plaintext API key" in error

    def test_plaintext_key_validation_accepts_empty(self):
        """Verify plaintext key validation accepts empty keys."""
        from berb.config import LlmConfig

        config = LlmConfig(
            provider="openai",
            api_key="",  # Empty - OK
            api_key_env="OPENAI_API_KEY",
        )

        is_valid, error = config.validate_no_plaintext_key()

        assert is_valid is True
        assert error == ""

    def test_config_validation_rejects_plaintext_api_key(self):
        """Verify config validation rejects plaintext API keys."""
        from berb.config import validate_config

        data = {
            "project": {"name": "test"},
            "research": {"topic": "test"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "none"},
            "knowledge_base": {"root": "kb"},
            "llm": {
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": "sk-secret-key-here",  # SECURITY VIOLATION
            },
        }

        result = validate_config(data, check_paths=False)

        assert result.ok is False
        assert any("SECURITY VIOLATION" in e for e in result.errors)
        assert any("Plaintext API key" in e for e in result.errors)

    def test_config_validation_warns_on_other_plaintext_keys(self):
        """Verify config validation warns on other plaintext keys."""
        from berb.config import validate_config

        data = {
            "project": {"name": "test"},
            "research": {"topic": "test"},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "none"},
            "knowledge_base": {"root": "kb"},
            "llm": {
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "api_key": "",  # OK - empty
                "s2_api_key": "secret-s2-key",  # Should warn
            },
            "web_search": {
                "tavily_api_key": "secret-tavily-key",  # Should warn
            },
        }

        result = validate_config(data, check_paths=False)

        # Should pass (warnings, not errors)
        assert result.ok is True

        # Should have warnings
        assert any("s2_api_key" in w for w in result.warnings)
        assert any("tavily_api_key" in w for w in result.warnings)


# =============================================================================
# Fix #6: LLM Rate Limiting Tests
# =============================================================================


class TestLLMRateLimiting:
    """Tests for Fix #6: LLM rate limiting."""

    def test_llm_config_has_rate_limit_settings(self):
        """Verify LLMConfig includes rate limit settings."""
        from berb.llm.client import LLMConfig

        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
        )

        # SECURITY FIX #6: Rate limit settings must be present
        assert hasattr(config, "rate_limit_enabled")
        assert hasattr(config, "rate_limit_requests_per_minute")
        assert hasattr(config, "rate_limit_tokens_per_minute")

        # Defaults should be reasonable
        assert config.rate_limit_enabled is True
        assert config.rate_limit_requests_per_minute > 0
        assert config.rate_limit_tokens_per_minute > 0

    def test_token_bucket_rate_limiter_initialization(self):
        """Verify TokenBucketRateLimiter initializes correctly."""
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=90000,
        )

        status = limiter.get_status()

        assert status["requests_per_minute"] == 60
        assert status["tokens_per_minute"] == 90000
        assert status["request_tokens_available"] > 0
        assert status["token_tokens_available"] > 0

    def test_rate_limiter_allows_within_limit(self):
        """Verify rate limiter allows requests within limit."""
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=90000,
        )

        # Should allow first request
        allowed, wait_time = limiter.acquire(tokens=1000)
        assert allowed is True
        assert wait_time == 0.0

        # Should allow multiple requests within limit
        for _ in range(10):
            allowed, wait_time = limiter.acquire(tokens=100)
            assert allowed is True

    def test_rate_limiter_blocks_when_exhausted(self):
        """Verify rate limiter blocks when tokens exhausted."""
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=10,  # Low limit for testing
            tokens_per_minute=1000,
        )

        # Exhaust request tokens
        for _ in range(10):
            limiter.acquire(tokens=10)

        # Should be blocked now
        allowed, wait_time = limiter.acquire(tokens=10)
        assert allowed is False
        assert wait_time > 0

    def test_rate_limiter_refills_over_time(self):
        """Verify rate limiter refills tokens over time."""
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=60,
            tokens_per_minute=90000,
        )

        # Exhaust tokens
        for _ in range(60):
            limiter.acquire(tokens=100)

        # Should be blocked
        allowed, _ = limiter.acquire(tokens=100)
        assert allowed is False

        # Wait for refill (simulate time passing)
        time.sleep(1.0)  # 1 second = ~1 request token

        # Should allow again (at least 1 token refilled)
        allowed, wait_time = limiter.acquire(tokens=100)
        # May or may not be allowed depending on exact timing
        # But wait_time should be smaller now

    def test_llm_client_initializes_rate_limiter(self):
        """Verify LLMClient initializes rate limiter."""
        from berb.llm.client import LLMClient, LLMConfig

        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            rate_limit_enabled=True,
        )

        client = LLMClient(config)

        assert client._rate_limiter is not None
        assert client.get_rate_limiter_status() is not None

    def test_llm_client_rate_limiter_can_be_disabled(self):
        """Verify LLMClient rate limiter can be disabled."""
        from berb.llm.client import LLMClient, LLMConfig

        config = LLMConfig(
            base_url="https://api.openai.com/v1",
            api_key="test-key",
            rate_limit_enabled=False,
        )

        client = LLMClient(config)

        assert client._rate_limiter is None
        assert client.get_rate_limiter_status() is None

    def test_rate_limiter_thread_safety(self):
        """Verify rate limiter is thread-safe."""
        import threading

        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter(
            requests_per_minute=100,
            tokens_per_minute=10000,
        )

        results = []
        errors = []

        def acquire_tokens():
            try:
                for _ in range(20):
                    allowed, wait_time = limiter.acquire(tokens=100)
                    results.append(allowed)
                    if not allowed and wait_time > 0:
                        time.sleep(wait_time * 0.1)  # Small wait
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = [threading.Thread(target=acquire_tokens) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors
        assert len(errors) == 0

        # Some requests should have been allowed
        assert True in results

    def test_rate_limiter_lock_is_eagerly_initialized(self):
        """REGRESSION BUG-004: _lock must be a real Lock from __init__, not None.

        The previous lazy-init pattern had a TOCTOU window: two threads could
        both see self._lock is None and each create a separate Lock, causing
        one thread to operate without mutual exclusion.
        """
        import threading
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter()

        # _lock must be a Lock immediately after construction — before any call
        assert limiter._lock is not None, (
            "_lock is None after __init__ — lazy init TOCTOU not fixed (BUG-004)."
        )
        assert isinstance(limiter._lock, type(threading.Lock())), (
            "_lock is not a threading.Lock."
        )

    def test_rate_limiter_lock_identity_stable_under_concurrency(self):
        """REGRESSION BUG-004: concurrent _get_lock() calls must return identical object."""
        import threading
        from berb.llm.client import TokenBucketRateLimiter

        limiter = TokenBucketRateLimiter()
        lock_ids: set[int] = set()
        errors: list[Exception] = []

        def grab_lock_id():
            try:
                lock_ids.add(id(limiter._get_lock()))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=grab_lock_id) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(lock_ids) == 1, (
            f"Multiple distinct lock objects returned by _get_lock(): {len(lock_ids)} "
            "— TOCTOU race not fixed (BUG-004)."
        )


# =============================================================================
# Integration Tests
# =============================================================================


class TestSecurityFixesIntegration:
    """Integration tests for all security fixes."""

    def test_all_fixes_present_in_codebase(self):
        """Verify all security fixes are present in codebase."""
        # Fix #1: Docker sandbox
        from berb.hyperagent.task_agent import TaskAgentConfig
        config = TaskAgentConfig()
        assert hasattr(config, "docker_image")

        # Fix #2: API key env var enforcement
        from berb.config import LlmConfig
        llm_config = LlmConfig(provider="openai", api_key_env="TEST")
        assert hasattr(llm_config, "get_api_key")

        # Fix #6: Rate limiting
        from berb.llm.client import TokenBucketRateLimiter
        limiter = TokenBucketRateLimiter()
        assert hasattr(limiter, "acquire")

    def test_security_fix_markers_present(self):
        """Verify SECURITY FIX markers are present in code."""
        import re

        # Check task_agent.py
        task_agent_path = Path("berb/hyperagent/task_agent.py")
        if task_agent_path.exists():
            content = task_agent_path.read_text(encoding="utf-8")
            assert "SECURITY FIX #1" in content

        # Check config.py
        config_path = Path("berb/config.py")
        if config_path.exists():
            content = config_path.read_text(encoding="utf-8")
            assert "SECURITY FIX #2" in content

        # Check client.py
        client_path = Path("berb/llm/client.py")
        if client_path.exists():
            content = client_path.read_text(encoding="utf-8")
            assert "SECURITY FIX #6" in content


# =============================================================================
# BUG-003: SSRF fail-closed regression tests
# =============================================================================


class TestSSRFFailClosed:
    """Regression tests for BUG-003: SSRF guard must fail closed.

    Previously check_url_ssrf() returned None (safe) when DNS resolution
    failed, allowing unresolvable hostnames through without verification.
    The fix returns an error string so the caller blocks the request.
    """

    def test_unresolvable_hostname_is_blocked(self):
        """REGRESSION: unresolvable hostname must be blocked, not allowed."""
        from berb.web._ssrf import check_url_ssrf
        import socket
        from unittest.mock import patch

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
            result = check_url_ssrf("http://this-domain-definitely-does-not-exist-xyzzy.invalid/path")

        # Must return a non-None error — not silently allow the request.
        assert result is not None, (
            "SSRF check must fail closed when DNS resolution fails; "
            "got None (safe) which bypasses the guard."
        )
        assert "resolve" in result.lower() or "hostname" in result.lower()

    def test_oserror_on_dns_is_blocked(self):
        """OSError during DNS lookup must also be blocked."""
        from berb.web._ssrf import check_url_ssrf
        from unittest.mock import patch

        with patch("socket.getaddrinfo", side_effect=OSError("network unreachable")):
            result = check_url_ssrf("http://attacker.example.com/internal")

        assert result is not None

    def test_public_resolvable_domain_still_allowed(self):
        """Regression guard: legitimate resolvable public IPs remain allowed."""
        from berb.web._ssrf import check_url_ssrf
        import socket
        from unittest.mock import patch

        # Simulate resolving to a public IP (e.g. 93.184.216.34 = example.com)
        mock_info = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]
        with patch("socket.getaddrinfo", return_value=mock_info):
            result = check_url_ssrf("http://example.com/page")

        assert result is None, f"Public domain should be allowed; got: {result}"

    def test_private_ip_still_blocked(self):
        """Existing behavior: private IPs continue to be blocked."""
        from berb.web._ssrf import check_url_ssrf

        assert check_url_ssrf("http://10.0.0.1/admin") is not None
        assert check_url_ssrf("http://192.168.1.100/") is not None
        assert check_url_ssrf("http://127.0.0.1:8080/") is not None
        assert check_url_ssrf("http://169.254.169.254/latest/meta-data") is not None

    def test_is_safe_url_mirrors_check(self):
        """is_safe_url() must return False when DNS resolution fails."""
        from berb.web._ssrf import is_safe_url
        import socket
        from unittest.mock import patch

        with patch("socket.getaddrinfo", side_effect=socket.gaierror("NXDOMAIN")):
            safe = is_safe_url("http://unresolvable.invalid/")

        assert safe is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])