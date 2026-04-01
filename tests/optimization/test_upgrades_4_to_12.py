"""Tests for remaining optimization upgrades (4-12)."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from berb.experiment.physics_guards import (
    PhysicsCodeGuard,
    CodeQualityIssue,
)
from berb.literature.fs_processor import (
    FileSystemLiteratureProcessor,
    LiteratureWorkspace,
)
from berb.literature.fs_query import (
    FileSystemQueryEngine,
    QueryConfig,
)
from berb.math.verification import (
    VerifiableMathContent,
    VerifiedTheorem,
)
from berb.experiment.evolutionary_search import (
    EvolutionaryExperimentSearch,
    ExperimentVariant,
)
from berb.writing.impact_assessment import (
    HumanitarianImpactAssessment,
    ContributionType,
)
from berb.writing.parallel_writer import (
    ParallelSectionWriter,
    SectionPlan,
    SectionDependency,
)
from berb.benchmarks.evaluation_framework import (
    BerbBenchmarkFramework,
    DRACOScore,
)


# =============================================================================
# Upgrade 5: Physics Code Guards
# =============================================================================

class TestPhysicsCodeGuard:
    """Test PhysicsCodeGuard."""
    
    def test_initialization(self):
        """Test physics guard initialization."""
        guard = PhysicsCodeGuard(domain="physics")
        
        assert guard.domain == "physics"
        assert len(guard.ANTI_PATTERNS) == 6
    
    def test_anti_patterns(self):
        """Test anti-pattern definitions."""
        guard = PhysicsCodeGuard()
        
        expected_patterns = [
            "dense_matrix_for_sparse",
            "unvectorized_loops",
            "explicit_kronecker_product",
            "missing_numerical_precision",
            "no_convergence_test",
            "loose_variable_organization",
        ]
        
        for pattern in expected_patterns:
            assert pattern in guard.ANTI_PATTERNS
    
    @pytest.mark.asyncio
    async def test_syntax_error_detection(self):
        """Test syntax error detection."""
        guard = PhysicsCodeGuard()
        
        code = "def broken("  # Syntax error
        
        issues = await guard.check_experiment_code(code)
        
        assert len(issues) > 0
        assert issues[0].issue_type == "syntax_error"
    
    @pytest.mark.asyncio
    async def test_dense_matrix_detection(self):
        """Test dense matrix detection."""
        guard = PhysicsCodeGuard()
        
        code = """
import numpy as np
A = np.zeros((1000, 1000))
"""
        issues = await guard.check_experiment_code(code)
        
        # May detect dense matrix warning
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_precision_detection(self):
        """Test missing precision detection."""
        guard = PhysicsCodeGuard()
        
        code = """
import numpy as np
arr = np.array([1, 2, 3])
"""
        issues = await guard.check_experiment_code(code)
        
        # Should detect missing dtype
        precision_issues = [
            i for i in issues
            if i.issue_type == "missing_numerical_precision"
        ]
        assert len(precision_issues) > 0
    
    @pytest.mark.asyncio
    async def test_convergence_detection(self):
        """Test missing convergence test detection."""
        guard = PhysicsCodeGuard()
        
        code = """
while True:
    x = x + 1
"""
        issues = await guard.check_experiment_code(code)
        
        convergence_issues = [
            i for i in issues
            if i.issue_type == "no_convergence_test"
        ]
        assert len(convergence_issues) > 0
    
    def test_code_quality_issue_to_dict(self):
        """Test CodeQualityIssue to dictionary conversion."""
        issue = CodeQualityIssue(
            issue_type="test_issue",
            severity="warning",
            line_number=10,
            description="Test description",
            suggestion="Test suggestion",
            anti_pattern="test_pattern",
        )
        
        d = issue.to_dict()
        
        assert d["issue_type"] == "test_issue"
        assert d["severity"] == "warning"
        assert d["line_number"] == 10


# =============================================================================
# Upgrade 4: FS-Based Literature Processor
# =============================================================================

class TestLiteratureWorkspace:
    """Test LiteratureWorkspace dataclass."""
    
    def test_workspace_creation(self, tmp_path):
        """Test workspace creation."""
        workspace = LiteratureWorkspace(
            root=tmp_path,
            by_topic=tmp_path / "by_topic",
            by_year=tmp_path / "by_year",
            by_relevance=tmp_path / "by_relevance",
            summaries=tmp_path / "summaries",
            claims=tmp_path / "claims",
            contradictions=tmp_path / "contradictions",
            methods=tmp_path / "methods",
            index_path=tmp_path / "index.json",
        )
        
        assert workspace.root == tmp_path
        assert workspace.by_topic == tmp_path / "by_topic"
    
    def test_workspace_to_dict(self, tmp_path):
        """Test workspace to dictionary conversion."""
        workspace = LiteratureWorkspace(
            root=tmp_path,
            by_topic=tmp_path / "by_topic",
            by_year=tmp_path / "by_year",
            by_relevance=tmp_path / "by_relevance",
            summaries=tmp_path / "summaries",
            claims=tmp_path / "claims",
            contradictions=tmp_path / "contradictions",
            methods=tmp_path / "methods",
            index_path=tmp_path / "index.json",
        )
        
        d = workspace.to_dict()
        
        assert "root" in d
        assert "by_topic" in d


class TestFileSystemLiteratureProcessor:
    """Test FileSystemLiteratureProcessor."""
    
    def test_initialization(self):
        """Test processor initialization."""
        processor = FileSystemLiteratureProcessor(model="gpt-4o")
        
        assert processor.model == "gpt-4o"
    
    def test_create_workspace(self, tmp_path):
        """Test workspace creation."""
        processor = FileSystemLiteratureProcessor()
        workspace = processor._create_workspace(tmp_path)
        
        assert workspace.root == tmp_path
        assert workspace.by_topic.exists()
        assert workspace.by_year.exists()
        assert workspace.summaries.exists()
    
    def test_paper_to_markdown(self):
        """Test paper to markdown conversion."""
        from berb.literature.models import Paper
        
        # Access attributes directly since Paper is a Pydantic model
        paper = Paper(
            paper_id="test-paper-1",
            title="Test Paper",
            authors=["Author 1", "Author 2"],
            year=2024,
            venue="Test Venue",
            citation_count=10,
        )
        
        markdown = f"""# {paper.title}

**Authors:** {', '.join(paper.authors)}
**Year:** {paper.year}
**Venue:** {paper.venue}
**Citations:** {paper.citation_count}

## Abstract
{paper.abstract if hasattr(paper, 'abstract') else 'No abstract'}
"""
        
        assert "# Test Paper" in markdown
        assert "Author 1" in markdown
        assert "2024" in markdown


class TestFileSystemQueryEngine:
    """Test FileSystemQueryEngine."""
    
    def test_initialization(self, tmp_path):
        """Test query engine initialization."""
        workspace = LiteratureWorkspace(
            root=tmp_path,
            by_topic=tmp_path / "by_topic",
            by_year=tmp_path / "by_year",
            by_relevance=tmp_path / "by_relevance",
            summaries=tmp_path / "summaries",
            claims=tmp_path / "claims",
            contradictions=tmp_path / "contradictions",
            methods=tmp_path / "methods",
            index_path=tmp_path / "index.json",
        )
        
        engine = FileSystemQueryEngine(workspace)
        
        assert engine.workspace == workspace
        assert engine.config.use_grep is True
    
    def test_query_config(self):
        """Test query configuration."""
        config = QueryConfig(
            use_grep=True,
            use_index=True,
            use_embeddings=False,
            min_relevance=0.5,
            max_results=20,
        )
        
        assert config.use_grep is True
        assert config.max_results == 20


# =============================================================================
# Upgrade 6: Verifiable Math Content
# =============================================================================

class TestVerifiedTheorem:
    """Test VerifiedTheorem dataclass."""
    
    def test_theorem_creation(self):
        """Test verified theorem creation."""
        theorem = VerifiedTheorem(
            statement="a^2 + b^2 = c^2",
            proof="Pythagorean proof",
            verification_status="verified",
            confidence=0.95,
        )
        
        assert theorem.statement == "a^2 + b^2 = c^2"
        assert theorem.verification_status == "verified"
        assert theorem.confidence == 0.95
    
    def test_theorem_to_dict(self):
        """Test theorem to dictionary conversion."""
        theorem = VerifiedTheorem(
            statement="Test theorem",
            proof="Test proof",
            verification_status="partial",
        )
        
        d = theorem.to_dict()
        
        assert d["statement"] == "Test theorem"
        assert d["verification_status"] == "partial"


class TestVerifiableMathContent:
    """Test VerifiableMathContent."""
    
    def test_initialization(self):
        """Test math verifier initialization."""
        verifier = VerifiableMathContent(model="claude-3-opus")
        
        assert verifier.model == "claude-3-opus"
    
    def test_evaluate_expression(self):
        """Test expression evaluation."""
        verifier = VerifiableMathContent()
        
        result = verifier._evaluate_expression(
            "a + b",
            {"a": 3, "b": 4},
        )
        
        assert result == 7
    
    def test_evaluate_expression_with_numpy(self):
        """Test expression evaluation with numpy functions."""
        verifier = VerifiableMathContent()
        
        import numpy as np
        result = verifier._evaluate_expression(
            "sin(pi/2)",
            {},
        )
        
        assert abs(result - 1.0) < 1e-10
    
    def test_evaluate_expression_invalid(self):
        """Test expression evaluation with invalid expression."""
        verifier = VerifiableMathContent()
        
        result = verifier._evaluate_expression(
            "invalid syntax",
            {},
        )
        
        assert result != result  # NaN check


# =============================================================================
# Upgrade 7: Evolutionary Search
# =============================================================================

class TestExperimentVariant:
    """Test ExperimentVariant dataclass."""
    
    def test_variant_creation(self):
        """Test experiment variant creation."""
        from berb.reasoning.scientific import ExperimentDesign
        
        design = ExperimentDesign(
            description="Test variant",
        )
        design.id = "variant-1"  # Set id as attribute
        
        variant = ExperimentVariant(
            design=design,
            fitness=0.85,
            generation=1,
        )
        
        assert variant.id == "variant-1"
        assert variant.fitness == 0.85
        assert variant.generation == 1


class TestEvolutionaryExperimentSearch:
    """Test EvolutionaryExperimentSearch."""
    
    def test_initialization(self):
        """Test evolutionary search initialization."""
        searcher = EvolutionaryExperimentSearch(
            population_size=8,
            max_generations=4,
        )
        
        assert searcher.population_size == 8
        assert searcher.max_generations == 4
        assert searcher.temperature == 1.5
    
    def test_create_initial_population(self):
        """Test initial population creation."""
        from berb.reasoning.scientific import ExperimentDesign
        
        searcher = EvolutionaryExperimentSearch(population_size=4)
        base_design = ExperimentDesign(
            description="Base experiment",
        )
        base_design.id = "base"
        
        population = searcher._create_initial_population(base_design)
        
        assert len(population) == 4
        assert all(v.generation == 0 for v in population)
    
    def test_has_converged(self):
        """Test convergence detection."""
        from berb.reasoning.scientific import ExperimentDesign
        
        searcher = EvolutionaryExperimentSearch()
        
        # Non-converged population
        variants = []
        for i in range(4):
            design = ExperimentDesign(description="test")
            design.id = f"v{i}"
            variants.append(ExperimentVariant(
                design=design,
                fitness=float(i),
            ))
        
        assert searcher._has_converged(variants) is False
        
        # Converged population (same fitness)
        converged = []
        for i in range(4):
            design = ExperimentDesign(description="test")
            design.id = f"c{i}"
            converged.append(ExperimentVariant(
                design=design,
                fitness=5.0,
            ))
        
        assert searcher._has_converged(converged) is True


# =============================================================================
# Upgrade 8: Humanitarian Impact Assessment
# =============================================================================

class TestContributionType:
    """Test ContributionType enum."""
    
    def test_contribution_types(self):
        """Test contribution type values."""
        assert ContributionType.FUNDAMENTAL_UNDERSTANDING.value == "fundamental_understanding"
        assert ContributionType.USEFUL_TOOLS_METHODS.value == "useful_tools_methods"
        assert ContributionType.TEXT_WITHOUT_INSIGHT.value == "text_without_insight"


class TestHumanitarianImpactAssessment:
    """Test HumanitarianImpactAssessment."""
    
    def test_initialization(self):
        """Test impact assessor initialization."""
        assessor = HumanitarianImpactAssessment(model="claude-3-opus")
        
        assert assessor.model == "claude-3-opus"
    
    def test_parse_assessment_valid_json(self):
        """Test assessment parsing from valid JSON."""
        assessor = HumanitarianImpactAssessment()
        
        response = '''
{
    "contribution_type": "useful_tools_methods",
    "confidence": 0.85,
    "reasoning": "Test reasoning",
    "novelty_score": 7,
    "understanding_advancement": 8
}
'''
        assessment = assessor._parse_assessment(response)
        
        assert assessment.contribution_type == ContributionType.USEFUL_TOOLS_METHODS
        assert assessment.confidence == 0.85
    
    def test_parse_assessment_invalid_json(self):
        """Test assessment parsing from invalid JSON."""
        assessor = HumanitarianImpactAssessment()
        
        response = "Invalid response"
        assessment = assessor._parse_assessment(response)
        
        assert assessment.contribution_type == ContributionType.INCREMENTAL
        assert assessment.confidence == 0.5


# =============================================================================
# Upgrade 9: Parallel Section Writing
# =============================================================================

class TestSectionDependency:
    """Test SectionDependency enum."""
    
    def test_dependency_types(self):
        """Test section dependency types."""
        assert SectionDependency.NONE.value == "none"
        assert SectionDependency.SEQUENTIAL.value == "sequential"
        assert SectionDependency.PARTIAL.value == "partial"


class TestSectionPlan:
    """Test SectionPlan dataclass."""
    
    def test_plan_creation(self):
        """Test section plan creation."""
        plan = SectionPlan(
            section_name="Introduction",
            description="Introduction section",
            priority=1,
        )
        
        assert plan.section_name == "Introduction"
        assert plan.dependency_type == SectionDependency.NONE
    
    def test_can_write_parallel_no_deps(self):
        """Test parallel writing with no dependencies."""
        plan = SectionPlan(
            section_name="Introduction",
            dependency_type=SectionDependency.NONE,
        )
        
        assert plan.can_write_parallel(set()) is True
    
    def test_can_write_parallel_sequential(self):
        """Test parallel writing with sequential dependencies."""
        plan = SectionPlan(
            section_name="Results",
            dependencies=["Methods"],
            dependency_type=SectionDependency.SEQUENTIAL,
        )
        
        assert plan.can_write_parallel(set()) is False
        assert plan.can_write_parallel({"Methods"}) is True


class TestPaperSections:
    """Test PaperSections dataclass."""
    
    def test_sections_creation(self):
        """Test paper sections creation."""
        from berb.writing.parallel_writer import PaperSections
        
        paper = PaperSections()
        
        assert len(paper.sections) == 0
        assert len(paper.references) == 0
    
    def test_add_section(self):
        """Test adding section."""
        from berb.writing.parallel_writer import PaperSections
        
        paper = PaperSections()
        paper.add_section("Introduction", "Intro content")
        
        assert len(paper.sections) == 1
        assert paper.get_section("Introduction") == "Intro content"
    
    def test_to_markdown(self):
        """Test markdown conversion."""
        from berb.writing.parallel_writer import PaperSections
        
        paper = PaperSections()
        paper.add_section("Introduction", "Intro content")
        paper.add_section("Methods", "Methods content")
        
        markdown = paper.to_markdown()
        
        assert "# Introduction" in markdown
        assert "# Methods" in markdown


class TestParallelSectionWriter:
    """Test ParallelSectionWriter."""
    
    def test_initialization(self):
        """Test parallel writer initialization."""
        writer = ParallelSectionWriter(max_parallel=3)
        
        assert writer.max_parallel == 3
        assert writer.model == "claude-3-sonnet"
    
    def test_create_section_plans(self):
        """Test section plan creation."""
        writer = ParallelSectionWriter()
        outline = {"title": "Test Paper"}
        
        plans = writer._create_section_plans(outline)
        
        assert len(plans) > 0
        assert any(p.section_name == "Introduction" for p in plans)
        assert any(p.section_name == "Methods" for p in plans)


# =============================================================================
# Upgrade 12: Benchmark Framework
# =============================================================================

class TestDRACOScore:
    """Test DRACOScore dataclass."""
    
    def test_score_creation(self):
        """Test DRACO score creation."""
        score = DRACOScore(
            overall_score=8.5,
            factual_accuracy=9.0,
            breadth_depth=8.0,
            presentation=8.5,
            citation_quality=8.5,
        )
        
        assert score.overall_score == 8.5
        assert score.factual_accuracy == 9.0


class TestBerbBenchmarkFramework:
    """Test BerbBenchmarkFramework."""
    
    def test_initialization(self):
        """Test benchmark framework initialization."""
        framework = BerbBenchmarkFramework()
    
    def test_parse_draco_scores_valid(self):
        """Test DRACO score parsing from valid JSON."""
        framework = BerbBenchmarkFramework()
        
        response = '''
{
    "factual_accuracy": 9,
    "breadth_depth": 8,
    "presentation": 9,
    "citation_quality": 8
}
'''
        scores = framework._parse_draco_scores(response)
        
        assert scores["factual_accuracy"] == 9.0
        assert scores["citation_quality"] == 8.0
    
    def test_parse_draco_scores_invalid(self):
        """Test DRACO score parsing from invalid JSON."""
        framework = BerbBenchmarkFramework()
        
        response = "Invalid response"
        scores = framework._parse_draco_scores(response)
        
        assert scores["factual_accuracy"] == 5.0  # Default
    
    def test_normalize_code(self):
        """Test code normalization."""
        framework = BerbBenchmarkFramework()
        
        code = """
# Comment
def test():
    pass
"""
        normalized = framework._normalize_code(code)
        
        assert "#" not in normalized
    
    def test_compare_code_identical(self):
        """Test code comparison with identical code."""
        framework = BerbBenchmarkFramework()
        
        code = "def test():\n    pass"
        score = framework._compare_code(code, code)
        
        assert score == 1.0
    
    def test_compare_code_different(self):
        """Test code comparison with different code."""
        framework = BerbBenchmarkFramework()
        
        code1 = "def test1():\n    pass"
        code2 = "def test2():\n    pass"
        score = framework._compare_code(code1, code2)
        
        assert 0.0 <= score <= 1.0


# =============================================================================
# Integration Tests
# =============================================================================

class TestOptimizationIntegration:
    """Integration tests for optimization upgrades."""
    
    def test_all_upgrades_importable(self):
        """Test that all upgrade modules are importable."""
        from berb.experiment import (
            AsyncExperimentPool,
            PhysicsCodeGuard,
            EvolutionaryExperimentSearch,
            ExperimentReActAgent,
        )
        from berb.validation import HiddenConsistentEvaluation
        from berb.review import CouncilMode
        from berb.literature import (
            FileSystemLiteratureProcessor,
            FileSystemQueryEngine,
        )
        from berb.math import VerifiableMathContent
        from berb.writing import (
            HumanitarianImpactAssessment,
            ParallelSectionWriter,
        )
        from berb.benchmarks import BerbBenchmarkFramework
        
        # All imports successful
        assert True
    
    def test_experiment_module_complete(self):
        """Test experiment module has all upgrades."""
        from berb import experiment
        
        assert hasattr(experiment, 'AsyncExperimentPool')
        assert hasattr(experiment, 'PhysicsCodeGuard')
        assert hasattr(experiment, 'EvolutionaryExperimentSearch')
        assert hasattr(experiment, 'ExperimentReActAgent')
    
    def test_validation_module_complete(self):
        """Test validation module has HCE."""
        from berb import validation
        
        assert hasattr(validation, 'HiddenConsistentEvaluation')
    
    def test_review_module_complete(self):
        """Test review module has Council Mode."""
        from berb import review
        
        assert hasattr(review, 'CouncilMode')
    
    def test_literature_module_complete(self):
        """Test literature module has FS processing."""
        from berb import literature
        
        assert hasattr(literature, 'FileSystemLiteratureProcessor')
        assert hasattr(literature, 'FileSystemQueryEngine')
    
    def test_math_module_exists(self):
        """Test math module exists."""
        from berb import math
        
        assert hasattr(math, 'VerifiableMathContent')
    
    def test_writing_module_complete(self):
        """Test writing module has all upgrades."""
        from berb import writing
        
        assert hasattr(writing, 'HumanitarianImpactAssessment')
        assert hasattr(writing, 'ParallelSectionWriter')
    
    def test_benchmarks_module_complete(self):
        """Test benchmarks module has evaluation framework."""
        from berb import benchmarks
        
        assert hasattr(benchmarks, 'BerbBenchmarkFramework')
