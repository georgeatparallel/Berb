"""Pipeline stage definitions per research field."""


def get_stages_for_field(pipeline_type: str, topic: str) -> list:
    """Get pipeline stages based on field type."""
    
    if pipeline_type == "humanities":
        return _get_humanities_stages(topic)
    elif pipeline_type == "social-sciences":
        return _get_social_sciences_stages(topic)
    elif pipeline_type in ["natural-sciences", "physics", "chemistry", "biology"]:
        return _get_natural_sciences_stages(topic)
    elif pipeline_type in ["ml-cs", "ai", "cs"]:
        return _get_ml_cs_stages(topic)
    elif pipeline_type == "biomedical":
        return _get_biomedical_stages(topic)
    elif pipeline_type == "engineering":
        return _get_engineering_stages(topic)
    else:
        return _get_general_stages(topic)


def _get_humanities_stages(topic: str) -> list:
    """Humanities: 18 stages, qualitative, NO experiments."""
    return [
        ("TOPIC_INIT", {"prompt": f"SOCRATIC: What is X? Why matter? Assumptions?: {topic}", "reasoning_method": "socratic"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"MULTI-PERSPECTIVE (historical, philosophical, theological): {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"Search: key texts, primary sources: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Collect: papers, primary sources, interpretations: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "Screen: BAYESIAN confidence update.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Extract: multiple interpretive frameworks.", "reasoning_method": "multi_perspective"}),
        ("SYNTHESIS", {"prompt": "DIALECTICAL: thesis → antithesis → aufhebung.", "reasoning_method": "dialectical"}),
        ("HYPOTHESIS_GEN", {"prompt": "Thesis statement (not hypothesis). Nuanced position.", "reasoning_method": "dialectical"}),
        ("RESULT_ANALYSIS", {"prompt": "Hermeneutic/textual analysis.", "reasoning_method": "multi_perspective"}),
        ("RESEARCH_DECISION", {"prompt": "JURY: weigh competing interpretations.", "reasoning_method": "jury"}),
        ("PAPER_OUTLINE", {"prompt": "Intro → Arguments → Counter → Response → Conclusion", "reasoning_method": "dialectical"}),
        ("PAPER_DRAFT", {"prompt": "Rhetorical argumentation.", "reasoning_method": "debate"}),
        ("PEER_REVIEW", {"prompt": "Multiple scholarly traditions.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address critiques, maintain core.", "reasoning_method": "dialectical"}),
        ("QUALITY_GATE", {"prompt": "Originality, Rigor, Clarity, Contribution.", "reasoning_method": "jury"}),
        ("KNOWLEDGE_ARCHIVE", {"prompt": "Document sources, arguments.", "reasoning_method": "research"}),
        ("EXPORT_PUBLISH", {"prompt": "Chicago/Turabian style.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Chicago: DOI, pages, quotes.", "reasoning_method": "bayesian"}),
    ]


def _get_social_sciences_stages(topic: str) -> list:
    """Social Sciences: 20 stages, mixed methods."""
    return [
        ("TOPIC_INIT", {"prompt": f"SOCRATIC: What phenomenon? Theories?: {topic}", "reasoning_method": "socratic"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Sociological, psychological, economic, cultural: {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"Mixed methods sources: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Papers, datasets, case studies: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "BAYESIAN screening.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Qualitative + quantitative findings.", "reasoning_method": "multi_perspective"}),
        ("SYNTHESIS", {"prompt": "Weigh qualitative vs quantitative.", "reasoning_method": "bayesian"}),
        ("HYPOTHESIS_GEN", {"prompt": "Testable social science hypotheses.", "reasoning_method": "scientific"}),
        ("SURVEY_DESIGN", {"prompt": "Survey/interview protocols.", "reasoning_method": "scientific"}),
        ("DATA_COLLECTION", {"prompt": "Sampling, ethics, validity.", "reasoning_method": "pre_mortem"}),
        ("DATA_ANALYSIS", {"prompt": "Statistical or thematic.", "reasoning_method": "scientific"}),
        ("RESULT_ANALYSIS", {"prompt": "Theoretical context.", "reasoning_method": "multi_perspective"}),
        ("RESEARCH_DECISION", {"prompt": "Support/refine/reject.", "reasoning_method": "bayesian"}),
        ("PAPER_OUTLINE", {"prompt": "APA structure.", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "APA style.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Multi-disciplinary.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address feedback.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "Validity, Reliability, Generalizability, Ethics.", "reasoning_method": "jury"}),
        ("EXPORT_PUBLISH", {"prompt": "APA format.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "APA verification.", "reasoning_method": "bayesian"}),
    ]


def _get_natural_sciences_stages(topic: str) -> list:
    """Natural Sciences: 23 stages, scientific method."""
    return [
        ("TOPIC_INIT", {"prompt": f"Scientific: What phenomenon? Laws?: {topic}", "reasoning_method": "scientific"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Testable sub-problems: {topic}", "reasoning_method": "scientific"}),
        ("SEARCH_STRATEGY", {"prompt": f"Primary literature: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Papers, data, methods: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "BAYESIAN screening.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Methods, results, uncertainties.", "reasoning_method": "scientific"}),
        ("SYNTHESIS", {"prompt": "Current understanding.", "reasoning_method": "multi_perspective"}),
        ("HYPOTHESIS_GEN", {"prompt": "Falsifiable hypotheses.", "reasoning_method": "scientific"}),
        ("EXPERIMENT_DESIGN", {"prompt": "Controls, variables.", "reasoning_method": "scientific"}),
        ("PRE_MORTEM", {"prompt": "What could fail?", "reasoning_method": "pre_mortem"}),
        ("CODE_GENERATION", {"prompt": "Analysis code.", "reasoning_method": "scientific"}),
        ("RESOURCE_PLANNING", {"prompt": "Equipment, safety.", "reasoning_method": "pre_mortem"}),
        ("EXPERIMENT_RUN", {"prompt": "Execute, record.", "reasoning_method": "scientific"}),
        ("ITERATIVE_REFINE", {"prompt": "Refine.", "reasoning_method": "scientific"}),
        ("RESULT_ANALYSIS", {"prompt": "Statistics, significance.", "reasoning_method": "bayesian"}),
        ("RESEARCH_DECISION", {"prompt": "Accept/reject.", "reasoning_method": "scientific"}),
        ("PAPER_OUTLINE", {"prompt": "Scientific structure.", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "Scientific style.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Scientific rigor.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address concerns.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "Reproducibility, Validity, Novelty.", "reasoning_method": "jury"}),
        ("EXPORT_PUBLISH", {"prompt": "Journal format.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Journal style.", "reasoning_method": "bayesian"}),
    ]


def _get_ml_cs_stages(topic: str) -> list:
    """ML/CS: 23 stages, computational experiments."""
    return [
        ("TOPIC_INIT", {"prompt": f"Technical: What problem? SOTA?: {topic}", "reasoning_method": "scientific"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Technical sub-problems: {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"arXiv, conferences, code: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Papers, code, benchmarks: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "Venue, citations, code.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Architectures, methods, metrics.", "reasoning_method": "scientific"}),
        ("SYNTHESIS", {"prompt": "SOTA, gaps.", "reasoning_method": "multi_perspective"}),
        ("HYPOTHESIS_GEN", {"prompt": "'Method X improves Y by Z%'.", "reasoning_method": "scientific"}),
        ("EXPERIMENT_DESIGN", {"prompt": "Baselines, ablations, metrics.", "reasoning_method": "scientific"}),
        ("PRE_MORTEM", {"prompt": "GPU issues, bugs?", "reasoning_method": "pre_mortem"}),
        ("CODE_GENERATION", {"prompt": "Training/eval code.", "reasoning_method": "scientific"}),
        ("RESOURCE_PLANNING", {"prompt": "GPU hours, data.", "reasoning_method": "pre_mortem"}),
        ("EXPERIMENT_RUN", {"prompt": "Train, log.", "reasoning_method": "scientific"}),
        ("ITERATIVE_REFINE", {"prompt": "Hyperparams, debug.", "reasoning_method": "scientific"}),
        ("RESULT_ANALYSIS", {"prompt": "Accuracy, ablations.", "reasoning_method": "bayesian"}),
        ("RESEARCH_DECISION", {"prompt": "Validated? Next?", "reasoning_method": "multi_perspective"}),
        ("PAPER_OUTLINE", {"prompt": "NeurIPS/ICML structure.", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "Conference style.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Novelty, reproducibility.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address reviews.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "SOTA, reproducibility, code.", "reasoning_method": "jury"}),
        ("EXPORT_PUBLISH", {"prompt": "Conference format.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Verify.", "reasoning_method": "bayesian"}),
    ]


def _get_biomedical_stages(topic: str) -> list:
    """Biomedical: 23 stages, clinical rigor."""
    return [
        ("TOPIC_INIT", {"prompt": f"Clinical: Condition? Mechanisms?: {topic}", "reasoning_method": "scientific"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Molecular, cellular, clinical: {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"PUBMED, trials, guidelines: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"RCTs, meta-analyses: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "Quality, bias.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "PICO, outcomes, effects.", "reasoning_method": "scientific"}),
        ("SYNTHESIS", {"prompt": "GRADE evidence.", "reasoning_method": "bayesian"}),
        ("HYPOTHESIS_GEN", {"prompt": "Clinical hypothesis.", "reasoning_method": "scientific"}),
        ("EXPERIMENT_DESIGN", {"prompt": "RCT/cohort. Ethics.", "reasoning_method": "scientific"}),
        ("PRE_MORTEM", {"prompt": "Safety, recruitment.", "reasoning_method": "pre_mortem"}),
        ("CODE_GENERATION", {"prompt": "Stats plan.", "reasoning_method": "scientific"}),
        ("RESOURCE_PLANNING", {"prompt": "Patients, IRB.", "reasoning_method": "pre_mortem"}),
        ("EXPERIMENT_RUN", {"prompt": "Execute, monitor.", "reasoning_method": "scientific"}),
        ("ITERATIVE_REFINE", {"prompt": "Interim, safety.", "reasoning_method": "bayesian"}),
        ("RESULT_ANALYSIS", {"prompt": "ITT, subgroup.", "reasoning_method": "bayesian"}),
        ("RESEARCH_DECISION", {"prompt": "Clinical significance?", "reasoning_method": "jury"}),
        ("PAPER_OUTLINE", {"prompt": "CONSORT/STROBE.", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "Medical style.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Validity, ethics.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "Relevance, rigor, ethics.", "reasoning_method": "jury"}),
        ("EXPORT_PUBLISH", {"prompt": "Journal format.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Vancouver/AMA.", "reasoning_method": "bayesian"}),
    ]


def _get_engineering_stages(topic: str) -> list:
    """Engineering: 23 stages, design-build-test."""
    return [
        ("TOPIC_INIT", {"prompt": f"Need? Constraints?: {topic}", "reasoning_method": "scientific"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Requirements, subsystems: {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"Patents, standards: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Specs, datasheets: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "Applicability.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Design patterns.", "reasoning_method": "scientific"}),
        ("SYNTHESIS", {"prompt": "Requirements.", "reasoning_method": "multi_perspective"}),
        ("HYPOTHESIS_GEN", {"prompt": "'System X achieves Y under Z'.", "reasoning_method": "scientific"}),
        ("EXPERIMENT_DESIGN", {"prompt": "Prototype, test.", "reasoning_method": "scientific"}),
        ("PRE_MORTEM", {"prompt": "Failures, safety.", "reasoning_method": "pre_mortem"}),
        ("CODE_GENERATION", {"prompt": "Control code.", "reasoning_method": "scientific"}),
        ("RESOURCE_PLANNING", {"prompt": "Materials, budget.", "reasoning_method": "pre_mortem"}),
        ("EXPERIMENT_RUN", {"prompt": "Build, test.", "reasoning_method": "scientific"}),
        ("ITERATIVE_REFINE", {"prompt": "Iterations.", "reasoning_method": "scientific"}),
        ("RESULT_ANALYSIS", {"prompt": "Performance, reliability.", "reasoning_method": "bayesian"}),
        ("RESEARCH_DECISION", {"prompt": "Production-ready?", "reasoning_method": "debate"}),
        ("PAPER_OUTLINE", {"prompt": "Design → Implementation → Eval", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "Engineering style.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Soundness, practicality.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Address.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "Functionality, Safety, Cost.", "reasoning_method": "jury"}),
        ("EXPORT_PUBLISH", {"prompt": "Format.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Verify.", "reasoning_method": "bayesian"}),
    ]


def _get_general_stages(topic: str) -> list:
    """General: 23 stages, balanced."""
    return [
        ("TOPIC_INIT", {"prompt": f"What? Why? How?: {topic}", "reasoning_method": "socratic"}),
        ("PROBLEM_DECOMPOSE", {"prompt": f"Sub-problems: {topic}", "reasoning_method": "multi_perspective"}),
        ("SEARCH_STRATEGY", {"prompt": f"Strategy: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_COLLECT", {"prompt": f"Collect: {topic}", "reasoning_method": "research"}),
        ("LITERATURE_SCREEN", {"prompt": "Relevance.", "reasoning_method": "bayesian"}),
        ("KNOWLEDGE_EXTRACT", {"prompt": "Insights.", "reasoning_method": "multi_perspective"}),
        ("SYNTHESIS", {"prompt": "Synthesize.", "reasoning_method": "research"}),
        ("HYPOTHESIS_GEN", {"prompt": "Hypotheses.", "reasoning_method": "scientific"}),
        ("EXPERIMENT_DESIGN", {"prompt": "Design.", "reasoning_method": "scientific"}),
        ("PRE_MORTEM", {"prompt": "What fails?", "reasoning_method": "pre_mortem"}),
        ("CODE_GENERATION", {"prompt": "Code.", "reasoning_method": "scientific"}),
        ("RESOURCE_PLANNING", {"prompt": "Plan.", "reasoning_method": "pre_mortem"}),
        ("EXPERIMENT_RUN", {"prompt": "Run.", "reasoning_method": "scientific"}),
        ("ITERATIVE_REFINE", {"prompt": "Refine.", "reasoning_method": "scientific"}),
        ("RESULT_ANALYSIS", {"prompt": "Analyze.", "reasoning_method": "bayesian"}),
        ("RESEARCH_DECISION", {"prompt": "Decide.", "reasoning_method": "multi_perspective"}),
        ("PAPER_OUTLINE", {"prompt": "Outline.", "reasoning_method": "research"}),
        ("PAPER_DRAFT", {"prompt": "Draft.", "reasoning_method": "research"}),
        ("PEER_REVIEW", {"prompt": "Review.", "reasoning_method": "multi_perspective"}),
        ("PAPER_REVISION", {"prompt": "Revise.", "reasoning_method": "debate"}),
        ("QUALITY_GATE", {"prompt": "Quality.", "reasoning_method": "jury"}),
        ("KNOWLEDGE_ARCHIVE", {"prompt": "Archive.", "reasoning_method": "research"}),
        ("EXPORT_PUBLISH", {"prompt": "Export.", "reasoning_method": "research"}),
        ("CITATION_VERIFY", {"prompt": "Verify.", "reasoning_method": "bayesian"}),
    ]
