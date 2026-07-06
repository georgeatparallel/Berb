# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""Tests for `berb survey` — literature review via sonar-deep-research."""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from berb import cli as rc_cli
from berb.llm.deep_query_client import DeepQueryResult


def _write_config(path: Path, *, perplexity_enabled: bool = True) -> None:
    (path.parent / "kb").mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
project:
  name: demo
  mode: docs-first
research:
  topic: Synthetic benchmark research
runtime:
  timezone: UTC
notifications:
  channel: test
knowledge_base:
  backend: markdown
  root: kb
openclaw_bridge: {{}}
llm:
  provider: openai-compatible
  base_url: http://localhost:1234/v1
  api_key_env: TEST_KEY
perplexity:
  enabled: {str(perplexity_enabled).lower()}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _args(config_path: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "config": str(config_path),
        "topic": "test survey topic",
        "preset": "ml-conference",
        "output": None,
        "yes": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_missing_config_returns_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _args(tmp_path / "missing.yaml")
    code = rc_cli.cmd_survey(args)
    assert code == 1
    assert "config file not found" in capsys.readouterr().err.lower()


def test_perplexity_disabled_returns_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, perplexity_enabled=False)
    args = _args(config_path)

    code = rc_cli.cmd_survey(args)

    assert code == 1
    assert "perplexity.enabled is false" in capsys.readouterr().err


def test_no_api_key_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    args = _args(config_path)

    code = rc_cli.cmd_survey(args)

    assert code == 1
    assert "PERPLEXITY_API_KEY is not set" in capsys.readouterr().err


def test_successful_survey_writes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "fake-key")
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    output_path = tmp_path / "review.md"
    args = _args(config_path, output=str(output_path))

    fake_result = DeepQueryResult(
        title="survey",
        content="## Overview\n\nComprehensive review body.",
        url="",
        source="DeepQuery",
        citations=[{"title": "Paper A", "url": "https://arxiv.org/abs/1"}],
    )

    with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_cls:
        mock_cls.return_value.literature_review.return_value = fake_result
        code = rc_cli.cmd_survey(args)

    assert code == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "Comprehensive review body." in content
    assert "Paper A" in content
    assert "https://arxiv.org/abs/1" in content
    out = capsys.readouterr().out
    assert "1 sources cited" in out


def test_literature_review_failure_returns_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "fake-key")
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    args = _args(config_path)

    with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_cls:
        mock_cls.return_value.literature_review.side_effect = RuntimeError("API down")
        code = rc_cli.cmd_survey(args)

    assert code == 1
    assert "literature review failed" in capsys.readouterr().err


def test_declining_confirmation_aborts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PERPLEXITY_API_KEY", "fake-key")
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    args = _args(config_path, yes=False)

    monkeypatch.setattr("builtins.input", lambda _: "n")

    with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_cls:
        code = rc_cli.cmd_survey(args)
        mock_cls.return_value.literature_review.assert_not_called()

    assert code == 1
    assert "Aborted" in capsys.readouterr().out


def test_default_output_path_uses_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No --output given → falls back to artifacts/survey-<run_id>.md."""
    monkeypatch.setenv("PERPLEXITY_API_KEY", "fake-key")
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    args = _args(config_path, output=None)

    fake_result = DeepQueryResult(title="survey", content="Body.", url="", source="DeepQuery")

    with patch("berb.llm.deep_query_client.DeepQueryClient") as mock_cls:
        mock_cls.return_value.literature_review.return_value = fake_result
        code = rc_cli.cmd_survey(args)

    assert code == 0
    matches = list((tmp_path / "artifacts").glob("survey-rc-*.md"))
    assert len(matches) == 1
