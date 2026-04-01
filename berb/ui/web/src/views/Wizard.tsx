import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Brain,
  BookOpen,
  FileText,
  FlaskConical,
  Search,
  CheckCircle2,
  ChevronRight,
  ChevronLeft,
  Upload,
  File,
  Settings,
  DollarSign,
  Users,
  Calculator,
  BookOpenCheck,
  Loader2,
  ExternalLink,
} from 'lucide-react';
import { designTokens } from '@design-system';
import type { WorkflowType } from '@types';
import { useResearch } from '@hooks/useResearch';

interface WorkflowOption {
  id: WorkflowType;
  title: string;
  description: string;
  icon: React.ReactNode;
  color: string;
}

const workflowOptions: WorkflowOption[] = [
  {
    id: 'full-research',
    title: 'Full Research',
    description: 'Topic → Literature → Hypothesis → Experiments → Paper',
    icon: <FlaskConical className="w-8 h-8" />,
    color: 'border-accent bg-accentLight',
  },
  {
    id: 'literature-only',
    title: 'Literature Only',
    description: 'Literature search + synthesis only. No experiments.',
    icon: <BookOpen className="w-8 h-8" />,
    color: 'border-blue-100 bg-blue-50',
  },
  {
    id: 'paper-from-results',
    title: 'Paper from Results',
    description: 'You have results. Berb writes the paper.',
    icon: <FileText className="w-8 h-8" />,
    color: 'border-green-100 bg-green-50',
  },
  {
    id: 'experiment-only',
    title: 'Experiments Only',
    description: 'Design and run experiments. No paper writing.',
    icon: <FlaskConical className="w-8 h-8" />,
    color: 'border-orange-100 bg-orange-50',
  },
  {
    id: 'literature-review',
    title: 'Literature Review',
    description: 'Standalone literature review / survey paper.',
    icon: <BookOpenCheck className="w-8 h-8" />,
    color: 'border-purple-100 bg-purple-50',
  },
  {
    id: 'math-paper',
    title: 'Math Paper',
    description: 'Significant mathematical content and proofs.',
    icon: <Calculator className="w-8 h-8" />,
    color: 'border-red-100 bg-red-50',
  },
];

export function WizardView() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [topic, setTopic] = useState('');
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowType | null>(null);
  const [preset, setPreset] = useState('humanities');
  const [mode, setMode] = useState<'autonomous' | 'collaborative'>('autonomous');

  // Use research hook
  const { job, isLoading, error, submitResearch, cancelJob } = useResearch();

  const handleNext = async () => {
    if (step < 5) {
      setStep(step + 1);
    } else {
      // Step 5: Submit research
      if (topic && selectedWorkflow) {
        try {
          await submitResearch({
            topic,
            preset,
            mode,
            budget_usd: 2.0,
          });
          // Don't navigate - stay on this step to show progress
        } catch (err) {
          console.error('Failed to submit research:', err);
        }
      }
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep(step - 1);
    }
  };

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center gap-2 mb-8">
      {[1, 2, 3, 4, 5, 6].map((s) => (
        <div key={s} className="flex items-center">
          <div
            className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all duration-300 ${
              s <= step
                ? 'bg-accent text-textInverse'
                : 'bg-surface text-textSecondary'
            }`}
          >
            {s}
          </div>
          {s < 6 && (
            <div
              className={`w-8 h-0.5 mx-1 transition-all duration-300 ${
                s < step ? 'bg-accent' : 'bg-surfaceHover'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );

  const renderTopicStep = () => (
    <div className="animate-fade-in-up">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-semibold text-textPrimary mb-2">
          What would you like to research?
        </h2>
        <p className="text-textSecondary">
          Enter your research topic or idea
        </p>
      </div>
      
      <div className="max-w-2xl mx-auto">
        <div className="card">
          <label className="block text-sm font-medium text-textSecondary mb-2">
            Research Topic
          </label>
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g., Neural architecture search for efficient transformers"
            className="input w-full text-lg py-4"
          />
          <p className="text-xs text-textTertiary mt-2">
            Be specific and focused for better results
          </p>
        </div>
        
        <div className="mt-6 flex justify-between">
          <button
            onClick={handleBack}
            disabled={step === 1}
            className="btn btn-secondary disabled:opacity-50"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back
          </button>
          <button
            onClick={handleNext}
            disabled={!topic.trim()}
            className="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
            <ChevronRight className="w-4 h-4 ml-1" />
          </button>
        </div>
      </div>
    </div>
  );

  const renderWorkflowStep = () => (
    <div className="animate-fade-in-up">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-semibold text-textPrimary mb-2">
          What do you need?
        </h2>
        <p className="text-textSecondary">
          Select the workflow that matches your goals
        </p>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl mx-auto">
        {workflowOptions.map((option) => (
          <div
            key={option.id}
            onClick={() => setSelectedWorkflow(option.id)}
            className={`card cursor-pointer transition-all duration-300 hover:shadow-md ${
              selectedWorkflow === option.id
                ? 'border-accent ring-2 ring-accentLight'
                : 'border-border'
            }`}
          >
            <div className="flex items-start gap-4">
              <div
                className={`w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  selectedWorkflow === option.id
                    ? option.color
                    : 'bg-surface text-textSecondary'
                }`}
              >
                {option.icon}
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-textPrimary mb-1">
                  {option.title}
                </h3>
                <p className="text-sm text-textSecondary leading-relaxed">
                  {option.description}
                </p>
              </div>
              {selectedWorkflow === option.id && (
                <CheckCircle2 className="w-6 h-6 text-accent flex-shrink-0" />
              )}
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-8 flex justify-between">
        <button
          onClick={handleBack}
          className="btn btn-secondary"
        >
          <ChevronLeft className="w-4 h-4 mr-1" />
          Back
        </button>
        <button
          onClick={handleNext}
          disabled={!selectedWorkflow}
          className="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
          <ChevronRight className="w-4 h-4 ml-1" />
        </button>
      </div>
    </div>
  );

  const renderPresetStep = () => (
    <div className="animate-fade-in-up">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-semibold text-textPrimary mb-2">
          Domain & Preset
        </h2>
        <p className="text-textSecondary">
          Auto-detected based on your topic
        </p>
      </div>
      
      <div className="max-w-2xl mx-auto">
        <div className="card">
          <label className="block text-sm font-medium text-textSecondary mb-2">
            Preset
          </label>
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value)}
            className="input w-full py-3"
          >
            <option value="ml-conference">ML Conference (NeurIPS, ICML, ICLR)</option>
            <option value="biomedical">Biomedical Research</option>
            <option value="nlp">Natural Language Processing</option>
            <option value="computer-vision">Computer Vision</option>
            <option value="physics">Physics / Computational Science</option>
            <option value="social-sciences">Social Sciences</option>
            <option value="systematic-review">Systematic Review</option>
            <option value="engineering">Engineering / Applied CS</option>
            <option value="humanities">Humanities / Qualitative</option>
            <option value="rapid-draft">Rapid Draft (Quick & Cheap)</option>
            <option value="budget">Budget-Optimized</option>
            <option value="max-quality">Maximum Quality</option>
          </select>
          <p className="text-xs text-textTertiary mt-2">
            You can customize this later
          </p>
        </div>
        
        <div className="mt-6 flex justify-between">
          <button
            onClick={handleBack}
            className="btn btn-secondary"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back
          </button>
          <button
            onClick={handleNext}
            className="btn btn-primary"
          >
            Next
            <ChevronRight className="w-4 h-4 ml-1" />
          </button>
        </div>
      </div>
    </div>
  );

  const renderModeStep = () => (
    <div className="animate-fade-in-up">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-semibold text-textPrimary mb-2">
          Operation Mode
        </h2>
        <p className="text-textSecondary">
          How would you like to collaborate with Berb?
        </p>
      </div>
      
      <div className="max-w-2xl mx-auto grid grid-cols-2 gap-4">
        <div
          onClick={() => setMode('autonomous')}
          className={`card cursor-pointer transition-all duration-300 ${
            mode === 'autonomous'
              ? 'border-accent ring-2 ring-accentLight'
              : 'border-border'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <Brain className={`w-6 h-6 ${mode === 'autonomous' ? 'text-accent' : 'text-textSecondary'}`} />
            <span className="font-semibold text-textPrimary">Autonomous</span>
          </div>
          <p className="text-sm text-textSecondary">
            Zero human intervention. Full pipeline execution.
          </p>
          <div className="mt-3 text-xs text-textTertiary">
            Best for: Rapid prototyping, known domains
          </div>
        </div>
        
        <div
          onClick={() => setMode('collaborative')}
          className={`card cursor-pointer transition-all duration-300 ${
            mode === 'collaborative'
              ? 'border-accent ring-2 ring-accentLight'
              : 'border-border'
          }`}
        >
          <div className="flex items-center gap-3 mb-3">
            <Users className={`w-6 h-6 ${mode === 'collaborative' ? 'text-accent' : 'text-textSecondary'}`} />
            <span className="font-semibold text-textPrimary">Collaborative</span>
          </div>
          <p className="text-sm text-textSecondary">
            Human-in-the-loop at decision points.
          </p>
          <div className="mt-3 text-xs text-textTertiary">
            Best for: Novel research, high-stakes papers
          </div>
        </div>
      </div>
      
      <div className="mt-6 flex justify-between">
        <button
          onClick={handleBack}
          className="btn btn-secondary"
        >
          <ChevronLeft className="w-4 h-4 mr-1" />
          Back
        </button>
        <button
          onClick={handleNext}
          className="btn btn-primary"
        >
          Next
          <ChevronRight className="w-4 h-4 ml-1" />
        </button>
      </div>
    </div>
  );

  const renderSummaryStep = () => (
    <div className="animate-fade-in-up">
      <div className="text-center mb-8">
        <h2 className="text-3xl font-semibold text-textPrimary mb-2">
          Summary
        </h2>
        <p className="text-textSecondary">
          Review your configuration before launching
        </p>
      </div>
      
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="card">
          <h3 className="font-semibold text-textPrimary mb-4 flex items-center gap-2">
            <File className="w-5 h-5 text-accent" />
            Research Details
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-textSecondary">Topic</span>
              <span className="text-textPrimary font-medium">{topic || 'Not specified'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-textSecondary">Workflow</span>
              <span className="text-textPrimary font-medium">
                {workflowOptions.find(w => w.id === selectedWorkflow)?.title || 'Full Research'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-textSecondary">Preset</span>
              <span className="text-textPrimary font-medium capitalize">{preset.replace('-', ' ')}</span>
            </div>
          </div>
        </div>
        
        <div className="card">
          <h3 className="font-semibold text-textPrimary mb-4 flex items-center gap-2">
            <Settings className="w-5 h-5 text-accent" />
            Configuration
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-textSecondary">Mode</span>
              <span className={`font-medium ${mode === 'autonomous' ? 'text-success' : 'text-warning'}`}>
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-textSecondary">Estimated Cost</span>
              <span className="text-textPrimary font-medium">$0.40 - $2.00</span>
            </div>
            <div className="flex justify-between">
              <span className="text-textSecondary">Estimated Time</span>
              <span className="text-textPrimary font-medium">1-2 hours</span>
            </div>
          </div>
        </div>
        
        <div className="mt-6 flex justify-between">
          <button
            onClick={handleBack}
            className="btn btn-secondary"
          >
            <ChevronLeft className="w-4 h-4 mr-1" />
            Back
          </button>
          <button
            onClick={handleNext}
            className="btn btn-primary"
          >
            Launch Research
            <ChevronRight className="w-4 h-4 ml-1" />
          </button>
        </div>
      </div>
    </div>
  );

  const renderProgressStep = () => {
    if (isLoading) {
      return (
        <div className="animate-fade-in-up text-center">
          <div className="w-20 h-20 bg-accentLight rounded-full flex items-center justify-center mx-auto mb-6">
            <Loader2 className="w-10 h-10 text-accent animate-spin" />
          </div>
          <h2 className="text-3xl font-semibold text-textPrimary mb-4">
            Starting Research...
          </h2>
          <p className="text-textSecondary max-w-md mx-auto">
            Berb is initializing your research project.
          </p>
        </div>
      );
    }

    if (error) {
      return (
        <div className="animate-fade-in-up text-center">
          <div className="w-20 h-20 bg-errorLight rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="w-10 h-10 text-error" />
          </div>
          <h2 className="text-3xl font-semibold text-textPrimary mb-4">
            Error Starting Research
          </h2>
          <p className="text-textSecondary max-w-md mx-auto mb-6">
            {error}
          </p>
          <button
            onClick={cancelJob}
            className="btn btn-primary"
          >
            Try Again
          </button>
        </div>
      );
    }

    if (job) {
      return (
        <div className="animate-fade-in-up text-center">
          <div className="w-20 h-20 bg-successLight rounded-full flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="w-10 h-10 text-success" />
          </div>
          <h2 className="text-3xl font-semibold text-textPrimary mb-4">
            Research Launched!
          </h2>
          <p className="text-textSecondary max-w-md mx-auto mb-2">
            Job ID: <code className="text-sm bg-surface px-2 py-1 rounded">{job.id}</code>
          </p>
          
          {job.status === 'running' && (
            <div className="card mt-6 max-w-md mx-auto">
              <div className="mb-4">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-textSecondary">Progress</span>
                  <span className="text-textPrimary font-medium">
                    {job.progress?.toFixed(0) || 0}%
                  </span>
                </div>
                <div className="w-full bg-surface rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-accent h-full transition-all duration-500"
                    style={{ width: `${job.progress || 0}%` }}
                  />
                </div>
              </div>
              
              {job.current_stage && (
                <p className="text-sm text-textSecondary">
                  Current Stage: {job.current_stage}
                </p>
              )}
              
              <p className="text-xs text-textSecondary mt-4">
                Status: <span className="font-medium text-accent">{job.status}</span>
              </p>
            </div>
          )}

          <div className="mt-6 flex gap-4 justify-center">
            <button
              onClick={() => navigate('/dashboard')}
              className="btn btn-primary"
            >
              Go to Dashboard
              <ExternalLink className="w-4 h-4 ml-2" />
            </button>
            {job.status === 'running' && (
              <button
                onClick={cancelJob}
                className="btn btn-outline"
              >
                Start New Research
              </button>
            )}
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="p-8 max-w-5xl mx-auto">
      {renderStepIndicator()}

      <div className="min-h-[500px]">
        {step === 1 && renderTopicStep()}
        {step === 2 && renderWorkflowStep()}
        {step === 3 && renderPresetStep()}
        {step === 4 && renderModeStep()}
        {step === 5 && renderSummaryStep()}
        {(job || isLoading || error) && renderProgressStep()}
      </div>
    </div>
  );
}
