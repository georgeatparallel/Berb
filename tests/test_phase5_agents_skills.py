"""Tests for Phase 5: Agents & Skills.

Author: Georgios-Chrysovalantis Chatzivantsidis
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from berb.agents.specialized import (
    AgentConfig,
    AgentResult,
    BaseAgent,
    LiteratureReviewerAgent,
    LiteratureReviewResult,
    ExperimentAnalystAgent,
    ExperimentAnalysisResult,
    PaperWritingAgent,
    PaperWritingResult,
    RebuttalWriterAgent,
    RebuttalResult,
    create_agent,
)
from berb.skills.registry import (
    Skill,
    SkillRegistry,
    apply_skills,
)


# ============== Agent Tests ==============

class TestAgentConfig:
    """Test AgentConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AgentConfig()
        assert config.max_tokens == 4096
        assert config.temperature == 0.7
        assert config.verbose is False

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            max_tokens=8192,
            temperature=0.5,
            verbose=True,
        )
        assert config.max_tokens == 8192
        assert config.temperature == 0.5
        assert config.verbose is True


class TestAgentResult:
    """Test AgentResult."""

    def test_default_result(self):
        """Test default result."""
        result = AgentResult()
        assert result.success is True
        assert result.confidence == 1.0
        assert result.output == {}

    def test_to_dict(self):
        """Test result to_dict method."""
        result = AgentResult(
            success=True,
            output={"key": "value"},
            confidence=0.85,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["output"]["key"] == "value"
        assert d["confidence"] == 0.85


class TestLiteratureReviewerAgent:
    """Test LiteratureReviewerAgent."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        config = AgentConfig()
        agent = LiteratureReviewerAgent(config)
        assert agent.config == config

    def test_format_papers(self):
        """Test paper formatting."""
        agent = LiteratureReviewerAgent()
        papers = [
            {"title": "Paper 1", "authors": ["Author A"], "year": 2020, "venue": "NeurIPS"},
            {"title": "Paper 2", "authors": ["Author B"], "year": 2021, "venue": "ICML"},
        ]
        formatted = agent._format_papers(papers)
        assert "Paper 1" in formatted
        assert "Author A" in formatted
        assert "NeurIPS" in formatted

    @pytest.mark.asyncio
    async def test_review_without_llm(self):
        """Test review without LLM (fallback)."""
        agent = LiteratureReviewerAgent()
        papers = [{"title": "Test Paper"}]
        result = await agent.review("Test Topic", papers)
        
        assert isinstance(result, LiteratureReviewResult)
        assert result.success is True
        assert len(result.key_findings) > 0

    @pytest.mark.asyncio
    async def test_review_with_mock_llm(self):
        """Test review with mock LLM."""
        mock_llm = Mock()
        mock_llm.chat = Mock(return_value=Mock(
            content='{"summary": "Test", "key_findings": ["Finding 1"], "gaps": ["Gap 1"], "trends": ["Trend 1"], "relevant_papers": []}'
        ))
        
        agent = LiteratureReviewerAgent(AgentConfig(llm_client=mock_llm))
        papers = [{"title": "Test Paper"}]
        result = await agent.review("Test Topic", papers)
        
        assert isinstance(result, LiteratureReviewResult)
        assert result.success is True


class TestExperimentAnalystAgent:
    """Test ExperimentAnalystAgent."""

    def test_format_results(self):
        """Test results formatting."""
        agent = ExperimentAnalystAgent()
        results = {"accuracy": [0.95, 0.93]}
        metrics = {"accuracy": 0.95, "f1": 0.93}
        formatted = agent._format_results(results, metrics, None)
        
        assert "## Metrics" in formatted
        assert "accuracy: 0.9500" in formatted

    @pytest.mark.asyncio
    async def test_analyze_without_llm(self):
        """Test analysis without LLM (fallback)."""
        agent = ExperimentAnalystAgent()
        results = {}
        metrics = {"accuracy": 0.95, "f1": 0.93}
        result = await agent.analyze(results, metrics)
        
        assert isinstance(result, ExperimentAnalysisResult)
        assert result.success is True
        assert len(result.key_results) > 0


class TestPaperWritingAgent:
    """Test PaperWritingAgent."""

    def test_format_outline(self):
        """Test outline formatting."""
        agent = PaperWritingAgent()
        outline = {
            "Introduction": ["Problem statement", "Contributions"],
            "Method": "Technical description",
        }
        formatted = agent._format_outline(outline)
        
        assert "## Introduction" in formatted
        assert "Problem statement" in formatted

    def test_format_citations(self):
        """Test citation formatting."""
        agent = PaperWritingAgent()
        citations = [
            {"title": "Paper 1", "authors": ["Author A"], "year": 2020},
            {"title": "Paper 2", "authors": ["Author B"], "year": 2021},
        ]
        formatted = agent._format_citations(citations)
        
        assert "Paper 1" in formatted
        assert "Author A" in formatted

    @pytest.mark.asyncio
    async def test_write_without_llm(self):
        """Test writing without LLM (fallback)."""
        agent = PaperWritingAgent()
        outline = {"Introduction": "Test"}
        result = await agent.write(outline, [])
        
        assert isinstance(result, PaperWritingResult)
        assert result.success is True
        assert "abstract" in result.sections


class TestRebuttalWriterAgent:
    """Test RebuttalWriterAgent."""

    def test_format_reviews(self):
        """Test review formatting."""
        agent = RebuttalWriterAgent()
        reviews = [
            {
                "reviewer": "R1",
                "rating": "7",
                "comments": ["Good paper", "Needs more experiments"],
            }
        ]
        formatted = agent._format_reviews(reviews)
        
        assert "Reviewer R1" in formatted
        assert "Rating: 7" in formatted
        assert "Good paper" in formatted

    @pytest.mark.asyncio
    async def test_respond_without_llm(self):
        """Test rebuttal without LLM (fallback)."""
        agent = RebuttalWriterAgent()
        reviews = [{"reviewer": "R1", "comments": ["Comment 1"]}]
        result = await agent.respond(reviews, "Paper text")
        
        assert isinstance(result, RebuttalResult)
        assert result.success is True
        assert len(result.point_by_point) > 0


class TestCreateAgent:
    """Test agent factory function."""

    def test_create_literature_agent(self):
        """Test creating literature agent."""
        agent = create_agent("literature", llm_client=Mock())
        assert isinstance(agent, LiteratureReviewerAgent)

    def test_create_experiment_agent(self):
        """Test creating experiment agent."""
        agent = create_agent("experiment", llm_client=Mock())
        assert isinstance(agent, ExperimentAnalystAgent)

    def test_create_paper_agent(self):
        """Test creating paper agent."""
        agent = create_agent("paper", llm_client=Mock())
        assert isinstance(agent, PaperWritingAgent)

    def test_create_rebuttal_agent(self):
        """Test creating rebuttal agent."""
        agent = create_agent("rebuttal", llm_client=Mock())
        assert isinstance(agent, RebuttalWriterAgent)

    def test_create_invalid_agent(self):
        """Test creating invalid agent type."""
        with pytest.raises(ValueError, match="Unknown agent type"):
            create_agent("invalid", llm_client=Mock())


# ============== Skill Tests ==============

class TestSkill:
    """Test Skill dataclass."""

    def test_default_skill(self):
        """Test default skill."""
        skill = Skill()
        assert skill.id == ""
        assert skill.triggers == []
        assert skill.instructions == []

    def test_skill_to_dict(self):
        """Test skill to_dict method."""
        skill = Skill(
            id="test-skill",
            name="Test Skill",
            description="A test skill",
            category="research",
        )
        d = skill.to_dict()
        assert d["id"] == "test-skill"
        assert d["name"] == "Test Skill"

    def test_skill_apply(self):
        """Test skill application."""
        skill = Skill(id="test-skill", name="Test")
        context = {"key": "value"}
        result = skill.apply(context)
        
        assert "applied_skills" in result
        assert "test-skill" in result["applied_skills"]


class TestSkillRegistry:
    """Test SkillRegistry."""

    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = SkillRegistry()
        assert len(registry._skills) == 4  # 4 built-in skills

    def test_get_skill(self):
        """Test getting skill by ID."""
        registry = SkillRegistry()
        skill = registry.get("literature-review")
        
        assert skill is not None
        assert skill.name == "Literature Review"

    def test_get_nonexistent_skill(self):
        """Test getting nonexistent skill."""
        registry = SkillRegistry()
        skill = registry.get("nonexistent")
        
        assert skill is None

    def test_get_by_category(self):
        """Test getting skills by category."""
        registry = SkillRegistry()
        skills = registry.get_by_category("research")
        
        assert len(skills) >= 1
        assert all(s.category == "research" for s in skills)

    def test_get_applicable_skills(self):
        """Test getting applicable skills for stage."""
        registry = SkillRegistry()
        skills = registry.get_applicable("LITERATURE_SCREEN")
        
        assert len(skills) >= 1
        assert "LITERATURE_SCREEN" in skills[0].triggers

    def test_list_skills(self):
        """Test listing all skills."""
        registry = SkillRegistry()
        skill_ids = registry.list_skills()
        
        assert len(skill_ids) == 4
        assert "literature-review" in skill_ids
        assert "experiment-analysis" in skill_ids

    def test_list_categories(self):
        """Test listing all categories."""
        registry = SkillRegistry()
        categories = registry.list_categories()
        
        assert len(categories) == 4  # research, analysis, writing, verification
        assert "research" in categories
        assert "writing" in categories

    def test_register_skill(self):
        """Test registering new skill."""
        registry = SkillRegistry()
        new_skill = Skill(
            id="custom-skill",
            name="Custom Skill",
            category="custom",
        )
        registry.register(new_skill)
        
        assert registry.get("custom-skill") is not None
        assert len(registry.list_skills()) == 5

    def test_registry_to_dict(self):
        """Test registry to_dict method."""
        registry = SkillRegistry()
        d = registry.to_dict()
        
        assert len(d) == 4
        assert "literature-review" in d
        assert d["literature-review"]["name"] == "Literature Review"


class TestApplySkills:
    """Test apply_skills helper function."""

    def test_apply_skills(self):
        """Test applying skills to context."""
        context = {"stage": "test"}
        result = apply_skills(context, "LITERATURE_SCREEN")
        
        assert "applied_skills" in result
        assert len(result["applied_skills"]) >= 1


# ============== Integration Tests ==============

class TestAgentsIntegration:
    """Test agent integration."""

    def test_import_agents(self):
        """Test agents can be imported."""
        from berb.agents.specialized import (
            LiteratureReviewerAgent,
            ExperimentAnalystAgent,
            PaperWritingAgent,
            RebuttalWriterAgent,
        )
        assert LiteratureReviewerAgent is not None

    def test_create_all_agents(self):
        """Test creating all agent types."""
        for agent_type in ["literature", "experiment", "paper", "rebuttal"]:
            agent = create_agent(agent_type, llm_client=Mock())
            assert agent is not None


class TestSkillsIntegration:
    """Test skill integration."""

    def test_import_skills(self):
        """Test skills can be imported."""
        from berb.skills import SkillRegistry, Skill
        assert SkillRegistry is not None
        assert Skill is not None

    def test_builtin_skills_complete(self):
        """Test built-in skills have all required fields."""
        registry = SkillRegistry()
        
        for skill in registry._skills.values():
            assert skill.id
            assert skill.name
            assert skill.description
            assert skill.category
            assert skill.triggers
            assert skill.instructions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
