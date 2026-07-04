"""MetaClaw bridge: post-pipeline hook.

Converts high-severity lessons into MetaClaw skills and records skill
effectiveness feedback.

Extracted from pipeline/runner.py as part of the Phase 2 runner split.

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from berb.config import RCConfig
from berb.pipeline.executor import StageResult

logger = logging.getLogger(__name__)


def metaclaw_post_pipeline(
    config: RCConfig,
    results: list[StageResult],
    lessons: list[object],
    run_id: str,
    run_dir: Path,
) -> None:
    """MetaClaw bridge: post-pipeline hook.

    1. Convert high-severity lessons into MetaClaw skills.
    2. Record skill effectiveness feedback.
    3. Signal session end to MetaClaw proxy.
    """
    bridge = getattr(config, "metaclaw_bridge", None)
    if not bridge or not getattr(bridge, "enabled", False):
        return

    from berb.llm.client import LLMClient

    # 1. Lesson-to-skill conversion
    l2s = getattr(bridge, "lesson_to_skill", None)
    if l2s and getattr(l2s, "enabled", False) and lessons:
        try:
            from berb.metaclaw_bridge.lesson_to_skill import (
                convert_lessons_to_skills,
            )

            min_sev = getattr(l2s, "min_severity", "warning")
            llm = LLMClient.from_rc_config(config)
            new_skills = convert_lessons_to_skills(
                lessons,
                llm,
                getattr(bridge, "skills_dir", "~/.metaclaw/skills"),
                min_severity=min_sev,
                max_skills=getattr(l2s, "max_skills_per_run", 3),
            )
            if new_skills:
                logger.info(
                    "MetaClaw: generated %d new skills from lessons: %s",
                    len(new_skills),
                    new_skills,
                )
        except Exception:
            logger.warning("MetaClaw lesson-to-skill conversion failed", exc_info=True)

    # 2. Skill effectiveness feedback
    try:
        from berb.metaclaw_bridge.skill_feedback import (
            SkillFeedbackStore,
            record_stage_skills,
        )
        from berb.metaclaw_bridge.stage_skill_map import get_stage_config

        feedback_store = SkillFeedbackStore(run_dir / "evolution" / "skill_effectiveness.jsonl")
        for result in results:
            stage_num = int(getattr(result, "stage", 0))
            stage_name = {
                1: "topic_init",
                2: "problem_decompose",
                3: "search_strategy",
                4: "literature_collect",
                5: "literature_screen",
                6: "knowledge_extract",
                7: "synthesis",
                8: "hypothesis_gen",
                9: "experiment_design",
                10: "code_generation",
                11: "resource_planning",
                12: "experiment_run",
                13: "iterative_refine",
                14: "result_analysis",
                15: "research_decision",
                16: "paper_outline",
                17: "paper_draft",
                18: "peer_review",
                19: "paper_revision",
                20: "quality_gate",
                21: "knowledge_archive",
                22: "export_publish",
                23: "citation_verify",
            }.get(stage_num, "")
            if not stage_name:
                continue
            stage_config = get_stage_config(stage_name)
            active_skills = stage_config.get("skills", [])
            status = str(getattr(result, "status", ""))
            success = "done" in status.lower()
            if active_skills:
                record_stage_skills(feedback_store, stage_name, run_id, success, active_skills)
    except Exception as exc:
        logger.warning("MetaClaw skill feedback recording failed (%s: %s)", type(exc).__name__, exc)

    # 3. Signal session end (fire-and-forget)
    try:
        import urllib.request as _urllib_req

        from berb.metaclaw_bridge.session import MetaClawSession

        session = MetaClawSession(run_id)
        end_headers = session.end()
        proxy_url = getattr(bridge, "proxy_url", "http://localhost:30000")
        url = f"{proxy_url.rstrip('/')}/v1/chat/completions"
        body = json.dumps(
            {
                "model": "session-end",
                "messages": [{"role": "user", "content": "session complete"}],
                "max_tokens": 1,
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        headers.update(end_headers)
        req = _urllib_req.Request(url, data=body, headers=headers)
        try:
            _urllib_req.urlopen(req, timeout=5)
        except Exception:
            pass
    except Exception:
        pass
