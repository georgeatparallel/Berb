/** TypeScript types for Berb Web UI.
 *
 * Shared types between React components and API.
 */

// ============================================================================
// WORKFLOW TYPES
// ============================================================================

/** Types of research workflows */
export type WorkflowType =
  | 'full-research'
  | 'literature-only'
  | 'paper-from-results'
  | 'experiment-only'
  | 'review-only'
  | 'rebuttal'
  | 'literature-review'
  | 'math-paper'
  | 'computational-paper';

/** Workflow configuration */
export interface WorkflowConfig {
  workflow: WorkflowType;
  enabled_stages?: number[];
  
  // User-provided inputs
  uploaded_pdfs?: string[];
  uploaded_data?: string[];
  uploaded_manuscript?: string;
  uploaded_reviews?: string;
  
  // Component toggles
  include_math?: boolean;
  include_experiments?: boolean;
  include_code_appendix?: boolean;
  include_supplementary?: boolean;
  
  // Operation mode
  operation_mode: OperationMode;
}

/** Operation modes */
export type OperationMode = 'autonomous' | 'collaborative';

/** Collaborative mode configuration */
export interface CollaborativeConfig {
  pause_after_stages: number[];
  approval_timeout_minutes: number;
  feedback_format: 'cli' | 'json' | 'api';
  allow_stage_skip: boolean;
  allow_hypothesis_edit: boolean;
  allow_experiment_override: boolean;
}

// ============================================================================
// STAGE TYPES
// ============================================================================

/** Stage status */
export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused';

/** Pipeline stage */
export interface Stage {
  stage_number: number;
  stage_name: string;
  status: StageStatus;
  progress: number; // 0-100
  message: string;
  started_at?: string;
  completed_at?: string;
  cost_usd: number;
  duration_seconds?: number;
}

/** Phase group */
export interface Phase {
  phase_id: string;
  phase_name: string;
  stages: number[];
  status: StageStatus;
  total_cost_usd: number;
  duration_seconds?: number;
}

// ============================================================================
// LITERATURE TYPES
// ============================================================================

/** Citation intent */
export type CitationIntent = 'supporting' | 'contrasting' | 'mentioning';

/** Citation classification */
export interface CitationClassification {
  citing_paper_id: string;
  cited_paper_id: string;
  intent: CitationIntent;
  confidence: number;
  context_snippet: string;
  section: string;
}

/** Paper citation profile */
export interface PaperCitationProfile {
  paper_id: string;
  total_citations: number;
  supporting: number;
  contrasting: number;
  mentioning: number;
  berb_confidence_score: number;
}

/** Literature paper */
export interface Paper {
  id: string;
  title: string;
  authors: string[];
  year: number;
  venue: string;
  doi?: string;
  abstract: string;
  citations: number;
  cited_by: number;
  berb_confidence: number;
  citation_profile?: PaperCitationProfile;
  classification?: CitationClassification[];
  reading_notes?: string;
  figures?: PaperFigure[];
  tables?: PaperTable[];
}

/** Paper figure */
export interface PaperFigure {
  id: string;
  caption: string;
  type: 'image' | 'chart' | 'diagram' | 'table';
  path?: string;
}

/** Paper table */
export interface PaperTable {
  id: string;
  title: string;
  data: string;
}

// ============================================================================
// PAPER TYPES
// ============================================================================

/** Paper section */
export interface PaperSection {
  title: string;
  content: string;
  latex?: string;
  figures: string[];
  citations: string[];
}

/** Generated paper */
export interface GeneratedPaper {
  id: string;
  title: string;
  abstract: string;
  sections: PaperSection[];
  latex_source: string;
  pdf_path?: string;
  figures: GeneratedFigure[];
  references: PaperReference[];
  cost_usd: number;
  duration_seconds: number;
  quality_score?: number;
  novelty_score?: number;
}

/** Generated figure */
export interface GeneratedFigure {
  id: string;
  type: string;
  caption: string;
  path: string;
  latex_include: string;
}

/** Paper reference */
export interface PaperReference {
  citation_key: string;
  full_citation: string;
  paper_id?: string;
}

// ============================================================================
// CLAIM & EVIDENCE TYPES
// ============================================================================

/** Claim confidence level */
export type ClaimConfidence = 'well_supported' | 'weakly_supported' | 'unsupported' | 'overstated';

/** Research claim */
export interface ResearchClaim {
  id: string;
  text: string;
  section: string;
  confidence: ClaimConfidence;
  evidence: ClaimEvidence[];
  confidence_score: number;
}

/** Claim evidence */
export interface ClaimEvidence {
  paper_id: string;
  paper_title: string;
  support_level: 'strong' | 'moderate' | 'weak';
  context: string;
}

// ============================================================================
// COST & METRICS TYPES
// ============================================================================

/** Cost breakdown */
export interface CostBreakdown {
  total_usd: number;
  by_model: Record<string, number>;
  by_phase: Record<string, number>;
  by_stage: Record<number, number>;
}

/** Model usage */
export interface ModelUsage {
  model: string;
  tokens: number;
  cost_usd: number;
  percentage: number;
}

/** Quality metrics */
export interface QualityMetrics {
  literature_quality: number;
  hypothesis_quality: number;
  experiment_quality: number;
  paper_quality: number;
  overall_score: number;
}

// ============================================================================
// API TYPES
// ============================================================================

/** Research job status */
export interface ResearchJob {
  id: string;
  topic: string;
  workflow: WorkflowType;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  stages: Stage[];
  phases: Phase[];
  cost_usd: number;
  duration_seconds: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  artifacts?: ResearchArtifacts;
}

/** Research artifacts */
export interface ResearchArtifacts {
  paper_pdf?: string;
  paper_tex?: string;
  figures: string[];
  data: string[];
  reproducibility_package?: string;
  audit_trail?: string;
}

/** Feedback submission */
export interface FeedbackSubmission {
  action: 'approve' | 'edit' | 'reject' | 'skip';
  feedback_text?: string;
  confidence_scores?: Record<string, number>;
  metadata?: Record<string, unknown>;
}

// ============================================================================
// PRESET TYPES
// ============================================================================

/** Pipeline preset */
export interface PipelinePreset {
  name: string;
  description: string;
  tags: string[];
  
  // Search
  primary_sources: string[];
  search_engines: string[];
  grey_sources: string[];
  full_text_access: string[];
  
  // Models
  primary_model: string;
  fallback_models: string[];
  reasoning_model: string;
  budget_model: string;
  
  // Pipeline
  enabled_stages: number[];
  stage_overrides: Record<number, Record<string, unknown>>;
  
  // Experiment
  experiment_mode: 'simulated' | 'sandbox' | 'docker' | 'ssh_remote' | 'colab_drive';
  experiment_frameworks: string[];
  validation_methods: string[];
  
  // Writing
  paper_format: string;
  target_venue?: string;
  max_pages: number;
  style_profile?: string;
  citation_style: 'numeric' | 'author-year' | 'footnote';
  
  // Quality
  min_literature_papers: number;
  min_quality_score: number;
  min_novelty_score: number;
  
  // Budget
  max_budget_usd: number;
  cost_optimization: 'aggressive' | 'balanced' | 'quality-first';
}

// ============================================================================
// WIZARD TYPES
// ============================================================================

/** Wizard step */
export interface WizardStep {
  id: number;
  title: string;
  description: string;
  icon: string;
}

/** Wizard state */
export interface WizardState {
  step: number;
  topic: string;
  workflow: WorkflowType;
  preset: string;
  sources: string[];
  options: WizardOptions;
  mode: OperationMode;
  budget: number;
}

/** Wizard options */
export interface WizardOptions {
  include_math: boolean;
  include_code_appendix: boolean;
  citation_style: string;
  min_year?: number;
  max_age_years?: number;
}

// ============================================================================
// UTILS
// ============================================================================

/** Pagination */
export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    total_pages: number;
  };
}

/** API response */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}
