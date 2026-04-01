import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  ChevronLeft,
  Play,
  Pause,
  RefreshCw,
  CheckCircle2,
  Clock,
  DollarSign,
  FileText,
  FlaskConical,
  BookOpen,
  BarChart3,
  AlertCircle,
  Loader2
} from 'lucide-react';
import { designTokens } from '@design-system';
import type { Stage, Phase, StageStatus } from '@types';

const phases: Phase[] = [
  { phase_id: 'A', phase_name: 'Scoping', stages: [1, 2], status: 'completed', total_cost_usd: 0.02 },
  { phase_id: 'B', phase_name: 'Literature', stages: [3, 4, 5, 6], status: 'completed', total_cost_usd: 0.15 },
  { phase_id: 'C', phase_name: 'Synthesis', stages: [7, 8], status: 'running', total_cost_usd: 0.10 },
  { phase_id: 'D', phase_name: 'Design', stages: [9, 10, 11], status: 'pending', total_cost_usd: 0 },
  { phase_id: 'E', phase_name: 'Execution', stages: [12, 13], status: 'pending', total_cost_usd: 0 },
  { phase_id: 'F', phase_name: 'Analysis', stages: [14, 15], status: 'pending', total_cost_usd: 0 },
  { phase_id: 'G', phase_name: 'Writing', stages: [16, 17, 18, 19], status: 'pending', total_cost_usd: 0 },
  { phase_id: 'H', phase_name: 'Finalization', stages: [20, 21, 22, 23], status: 'pending', total_cost_usd: 0 },
];

const stages: Stage[] = [
  { stage_number: 1, stage_name: 'TOPIC_INIT', status: 'completed', progress: 100, message: 'Topic initialized', cost_usd: 0.01 },
  { stage_number: 2, stage_name: 'PROBLEM_DECOMPOSE', status: 'completed', progress: 100, message: 'Problem decomposed', cost_usd: 0.01 },
  { stage_number: 3, stage_name: 'SEARCH_STRATEGY', status: 'completed', progress: 100, message: 'Search strategy created', cost_usd: 0.02 },
  { stage_number: 4, stage_name: 'LITERATURE_COLLECT', status: 'completed', progress: 100, message: '87 papers found', cost_usd: 0.05 },
  { stage_number: 5, stage_name: 'LITERATURE_SCREEN', status: 'completed', progress: 100, message: '52 papers screened', cost_usd: 0.03 },
  { stage_number: 6, stage_name: 'KNOWLEDGE_EXTRACT', status: 'completed', progress: 100, message: 'Knowledge extracted', cost_usd: 0.04 },
  { stage_number: 7, stage_name: 'SYNTHESIS', status: 'running', progress: 78, message: 'Identifying thematic clusters', cost_usd: 0.06 },
  { stage_number: 8, stage_name: 'HYPOTHESIS_GEN', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 9, stage_name: 'EXPERIMENT_DESIGN', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 10, stage_name: 'CODE_GENERATION', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 11, stage_name: 'RESOURCE_PLANNING', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 12, stage_name: 'EXPERIMENT_RUN', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 13, stage_name: 'ITERATIVE_REFINE', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 14, stage_name: 'RESULT_ANALYSIS', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 15, stage_name: 'RESEARCH_DECISION', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 16, stage_name: 'PAPER_OUTLINE', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 17, stage_name: 'PAPER_DRAFT', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 18, stage_name: 'PEER_REVIEW', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 19, stage_name: 'PAPER_REVISION', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 20, stage_name: 'QUALITY_GATE', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 21, stage_name: 'KNOWLEDGE_ARCHIVE', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 22, stage_name: 'EXPORT_PUBLISH', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
  { stage_number: 23, stage_name: 'CITATION_VERIFY', status: 'pending', progress: 0, message: 'Waiting...', cost_usd: 0 },
];

const statusColors: Record<StageStatus, string> = {
  pending: 'bg-surfaceHover text-textSecondary',
  running: 'bg-accentLight text-accent',
  completed: 'bg-successLight text-success',
  failed: 'bg-errorLight text-error',
  paused: 'bg-warningLight text-warning',
};

export function PipelineMonitorView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'overview' | 'literature' | 'paper' | 'results'>('overview');
  const [showApprovalModal, setShowApprovalModal] = useState(false);

  const totalCost = stages.reduce((sum, s) => sum + s.cost_usd, 0);
  const completedStages = stages.filter(s => s.status === 'completed').length;
  const totalStages = stages.length;
  const overallProgress = Math.round((completedStages / totalStages) * 100);

  const getStatusIcon = (status: StageStatus) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5" />;
      case 'running':
        return <Loader2 className="w-5 h-5 animate-spin" />;
      case 'paused':
        return <Pause className="w-5 h-5" />;
      case 'failed':
        return <AlertCircle className="w-5 h-5" />;
      default:
        return <div className="w-5 h-5 rounded-full bg-surfaceHover" />;
    }
  };

  const getStatusBadge = (status: StageStatus) => {
    return (
      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[status]}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="p-2 hover:bg-surfaceHover rounded-lg transition-colors"
          >
            <ChevronLeft className="w-5 h-5 text-textSecondary" />
          </button>
          <div>
            <h1 className="text-2xl font-semibold text-textPrimary">
              Neural Architecture Search for Efficient Transformers
            </h1>
            <p className="text-sm text-textSecondary">
              ID: {id || 'rc-20260331-abc123'} • Started: 3m ago
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-4 py-2 bg-surface rounded-lg">
            <DollarSign className="w-4 h-4 text-textSecondary" />
            <span className="font-semibold text-textPrimary">${totalCost.toFixed(2)}</span>
            <span className="text-sm text-textTertiary">/ $2.00</span>
          </div>
          <button className="px-4 py-2 bg-accent text-textInverse rounded-lg font-medium hover:bg-accentHover transition-colors">
            Pause
          </button>
          <button className="px-4 py-2 bg-success text-textInverse rounded-lg font-medium hover:bg-successHover transition-colors">
            Export
          </button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Main Content */}
        <div className="col-span-9 space-y-6">
          {/* Pipeline Progress */}
          <div className="card">
            <h2 className="text-lg font-semibold text-textPrimary mb-4">Pipeline Progress</h2>
            
            {/* Phase Indicators */}
            <div className="space-y-4 mb-6">
              {phases.map((phase) => (
                <div key={phase.phase_id} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                        phase.status === 'completed' ? 'bg-successLight text-success' :
                        phase.status === 'running' ? 'bg-accentLight text-accent' :
                        phase.status === 'failed' ? 'bg-errorLight text-error' :
                        'bg-surfaceHover text-textSecondary'
                      }`}>
                        <span className="font-semibold text-sm">{phase.phase_id}</span>
                      </div>
                      <span className="font-medium text-textPrimary">{phase.phase_name}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-textSecondary">
                        {phase.stages.length} stages
                      </span>
                      <span className="text-sm text-textSecondary">
                        ${phase.total_cost_usd.toFixed(2)}
                      </span>
                      {phase.status === 'running' && (
                        <span className="flex items-center gap-1 text-sm text-accent">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Running...
                        </span>
                      )}
                    </div>
                  </div>
                  
                  {/* Stage Progress Bar */}
                  <div className="h-2 bg-surfaceHover rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        phase.status === 'completed' ? 'bg-success' :
                        phase.status === 'running' ? 'bg-accent' :
                        phase.status === 'failed' ? 'bg-error' :
                        'bg-surfaceHover'
                      }`}
                      style={{ width: `${(phase.stages.length / 23) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Stage Details */}
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-textSecondary uppercase tracking-wider mb-2">
                Current Stage
              </h3>
              <div className="grid grid-cols-1 gap-3">
                {stages.slice(0, 10).map((stage) => (
                  <div
                    key={stage.stage_number}
                    className={`flex items-center gap-4 p-3 rounded-lg ${
                      stage.status === 'running' ? 'bg-accentLight/50' : ''
                    }`}
                  >
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      stage.status === 'completed' ? 'bg-successLight text-success' :
                      stage.status === 'running' ? 'bg-accent text-textInverse' :
                      stage.status === 'failed' ? 'bg-errorLight text-error' :
                      'bg-surfaceHover text-textSecondary'
                    }`}>
                      {stage.stage_number}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-textPrimary">{stage.stage_name}</span>
                        {stage.status === 'paused' && (
                          <span className="text-xs text-warning">PAUSED FOR APPROVAL</span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-sm text-textSecondary">{stage.message}</span>
                        <span className="text-xs text-textTertiary">|</span>
                        <span className="text-xs text-textTertiary">${stage.cost_usd.toFixed(3)}</span>
                      </div>
                      {stage.status === 'running' && (
                        <div className="w-full h-1 bg-surfaceHover rounded-full mt-2 overflow-hidden">
                          <div
                            className="h-full bg-accent rounded-full transition-all duration-300"
                            style={{ width: `${stage.progress}%` }}
                          />
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {getStatusIcon(stage.status)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Live Metrics */}
          <div className="grid grid-cols-3 gap-4">
            <div className="card">
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="w-4 h-4 text-accent" />
                <span className="text-sm font-semibold text-textSecondary">Literature</span>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Found</span>
                  <span className="font-semibold text-textPrimary">87</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Screened</span>
                  <span className="font-semibold text-textPrimary">52</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Included</span>
                  <span className="font-semibold text-textPrimary">34</span>
                </div>
              </div>
            </div>
            
            <div className="card">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-4 h-4 text-success" />
                <span className="text-sm font-semibold text-textSecondary">Cost</span>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Current</span>
                  <span className="font-semibold text-textPrimary">${totalCost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Budget</span>
                  <span className="font-semibold text-textPrimary">$2.00</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Est. Total</span>
                  <span className="font-semibold text-textPrimary">$0.85</span>
                </div>
              </div>
            </div>
            
            <div className="card">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-4 h-4 text-warning" />
                <span className="text-sm font-semibold text-textSecondary">Time</span>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Elapsed</span>
                  <span className="font-semibold text-textPrimary">3m 12s</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">ETA</span>
                  <span className="font-semibold text-textPrimary">~8m</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Efficiency</span>
                  <span className="font-semibold text-textPrimary">92%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Stage Output */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-textPrimary">Stage Output</h2>
              <button className="text-sm text-accent hover:text-accentHover">View Details</button>
            </div>
            
            <div className="bg-surface rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 bg-accent rounded-full animate-pulse" />
                <span className="text-sm font-medium text-textPrimary">Synthesis is identifying 4 thematic clusters:</span>
              </div>
              <ul className="space-y-2">
                <li className="flex items-start gap-2 text-sm text-textSecondary">
                  <span className="w-1.5 h-1.5 bg-accent rounded-full mt-1.5 flex-shrink-0" />
                  <span><strong>Weight sharing approaches</strong> (12 papers)</span>
                </li>
                <li className="flex items-start gap-2 text-sm text-textSecondary">
                  <span className="w-1.5 h-1.5 bg-accent rounded-full mt-1.5 flex-shrink-0" />
                  <span><strong>Search space design</strong> (8 papers)</span>
                </li>
                <li className="flex items-start gap-2 text-sm text-textSecondary">
                  <span className="w-1.5 h-1.5 bg-accent rounded-full mt-1.5 flex-shrink-0" />
                  <span><strong>Training efficiency</strong> (9 papers)</span>
                </li>
                <li className="flex items-start gap-2 text-sm text-textSecondary">
                  <span className="w-1.5 h-1.5 bg-accent rounded-full mt-1.5 flex-shrink-0" />
                  <span><strong>Hardware-aware NAS</strong> (5 papers)</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="col-span-3 space-y-6">
          {/* Model Usage */}
          <div className="card">
            <h2 className="text-lg font-semibold text-textPrimary mb-4">Model Usage</h2>
            <div className="space-y-3">
              {[
                { name: 'Claude Sonnet', count: 62, color: 'bg-green-500' },
                { name: 'GPT-4o', count: 28, color: 'bg-blue-500' },
                { name: 'Gemini Flash', count: 8, color: 'bg-yellow-500' },
              ].map((model) => (
                <div key={model.name}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-textSecondary">{model.name}</span>
                    <span className="text-textPrimary font-medium">{model.count}%</span>
                  </div>
                  <div className="w-full h-2 bg-surfaceHover rounded-full overflow-hidden">
                    <div
                      className={`h-full ${model.color} rounded-full`}
                      style={{ width: `${model.count}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="card">
            <h2 className="text-lg font-semibold text-textPrimary mb-4">Quick Actions</h2>
            <div className="space-y-2">
              <button className="w-full flex items-center gap-2 px-3 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-sm text-textPrimary transition-colors">
                <FileText className="w-4 h-4" />
                View Paper
              </button>
              <button className="w-full flex items-center gap-2 px-3 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-sm text-textPrimary transition-colors">
                <BookOpen className="w-4 h-4" />
                Browse Literature
              </button>
              <button className="w-full flex items-center gap-2 px-3 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-sm text-textPrimary transition-colors">
                <BarChart3 className="w-4 h-4" />
                View Results
              </button>
              <button
                onClick={() => setShowApprovalModal(true)}
                className="w-full flex items-center gap-2 px-3 py-2 bg-accentLight hover:bg-accentLight/80 rounded-lg text-sm text-accent transition-colors"
              >
                <Play className="w-4 h-4" />
                Resume Pipeline
              </button>
            </div>
          </div>

          {/* Progress Summary */}
          <div className="card">
            <h2 className="text-lg font-semibold text-textPrimary mb-4">Progress Summary</h2>
            <div className="text-center">
              <div className="w-24 h-24 mx-auto mb-4 relative">
                <svg className="w-full h-full transform -rotate-90">
                  <circle
                    cx="48"
                    cy="48"
                    r="40"
                    fill="none"
                    stroke="#E5E5EA"
                    strokeWidth="8"
                  />
                  <circle
                    cx="48"
                    cy="48"
                    r="40"
                    fill="none"
                    stroke="#0071E3"
                    strokeWidth="8"
                    strokeDasharray={251.2}
                    strokeDashoffset={251.2 - (251.2 * overallProgress) / 100}
                    className="transition-all duration-500"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center flex-col">
                  <span className="text-2xl font-semibold text-textPrimary">{overallProgress}%</span>
                  <span className="text-xs text-textSecondary">Complete</span>
                </div>
              </div>
              <div className="flex justify-between text-sm text-textSecondary">
                <span>{completedStages} stages</span>
                <span>{23 - completedStages} remaining</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Approval Modal */}
      {showApprovalModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-background rounded-xl shadow-xl max-w-lg w-full animate-fade-in-up">
            <div className="p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-warning rounded-full flex items-center justify-center">
                  <Pause className="w-5 h-5 text-textInverse" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-textPrimary">Pipeline Paused</h3>
                  <p className="text-sm text-textSecondary">Stage 8: Hypothesis Generation</p>
                </div>
              </div>
              
              <div className="space-y-3 mb-6">
                <h4 className="text-sm font-semibold text-textSecondary">3 hypotheses generated:</h4>
                
                <div className="flex items-start gap-3 p-3 bg-surface rounded-lg">
                  <div className="w-5 h-5 rounded border border-border flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-textPrimary">
                      Weight sharing reduces search cost by 40% without quality loss
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-textSecondary">Confidence: 0.82</span>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 bg-surface rounded-lg">
                  <div className="w-5 h-5 rounded border border-border flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-textPrimary">
                      Hardware-aware constraints improve real-world latency by 25%
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-textSecondary">Confidence: 0.76</span>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-start gap-3 p-3 bg-surface rounded-lg opacity-50">
                  <div className="w-5 h-5 rounded border border-border flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm text-textPrimary">
                      One-shot NAS matches multi-trial on ImageNet within 1% accuracy
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-textSecondary">Confidence: 0.54</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={() => setShowApprovalModal(false)}
                  className="flex-1 px-4 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-textPrimary transition-colors"
                >
                  Edit Feedback
                </button>
                <button
                  onClick={() => setShowApprovalModal(false)}
                  className="flex-1 px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors"
                >
                  Approve & Continue
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
