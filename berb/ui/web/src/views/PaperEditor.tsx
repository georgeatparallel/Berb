import React, { useState } from 'react';
import { 
  FileText,
  Eye,
  Edit,
  CheckCircle2,
  AlertCircle,
  ChevronLeft,
  Download,
  Share2,
  Settings
} from 'lucide-react';
import { designTokens } from '@design-system';

const paperSections = [
  { id: 'abstract', title: 'Abstract', content: 'Neural architecture search (NAS) has emerged as a promising approach to automate the design of efficient neural networks. This paper presents a comprehensive survey of recent advances in NAS, focusing on efficient search strategies, hardware-aware optimization, and theoretical guarantees. We identify four key challenges in current NAS methods: search space design, search efficiency, hardware constraints, and theoretical understanding. We then review 87 papers published between 2020 and 2026, categorizing them into four thematic clusters: weight sharing approaches (12 papers), search space design (8 papers), training efficiency (9 papers), and hardware-aware NAS (5 papers). Our analysis reveals that weight sharing reduces search cost by 40% without quality loss, hardware-aware constraints improve real-world latency by 25%, and one-shot NAS matches multi-trial performance within 1% accuracy on ImageNet. We conclude with open challenges and future directions for NAS research.' },
  { id: 'introduction', title: '1. Introduction', content: 'Neural architecture search (NAS) has emerged as a promising approach to automate the design of efficient neural networks. Unlike manual architecture design, NAS can systematically explore the architecture space and discover high-performing models with minimal human intervention. This paper presents a comprehensive survey of recent advances in NAS, focusing on efficient search strategies, hardware-aware optimization, and theoretical guarantees.' },
  { id: 'related-work', title: '2. Related Work', content: 'Our work builds on several key contributions in the NAS literature. Zoph and Le (2017) pioneered the use of reinforcement learning for NAS, demonstrating that neural architectures can be automatically discovered. Building on this, Baker et al. (2018) proposed evolutionary algorithms for NAS, showing competitive results with reduced computational cost. More recently, Cai et al. (2020) introduced weight sharing, dramatically reducing the search cost while maintaining competitive accuracy.' },
  { id: 'methodology', title: '3. Methodology', content: 'We conduct a systematic literature review following PRISMA guidelines. Our search strategy combines semantic search with citation traversal, starting from 10 seminal papers and expanding to include all papers cited by or citing these seeds. We use OpenAlex and Semantic Scholar as our primary sources, filtering for papers published between 2020 and 2026. After screening 52 papers, we include 34 papers that meet our inclusion criteria.' },
  { id: 'results', title: '4. Results', content: 'Our analysis reveals four key findings: (1) Weight sharing approaches achieve 40% cost reduction without quality loss, (2) Hardware-aware constraints improve real-world latency by 25%, (3) One-shot NAS matches multi-trial performance within 1% accuracy, and (4) Search space design significantly impacts final performance. We present detailed results in Section 4.1, including ablation studies and statistical significance tests.' },
  { id: 'discussion', title: '5. Discussion', content: 'Our findings have important implications for NAS research and practice. First, weight sharing has become the de facto standard for efficient NAS, with nearly all recent methods incorporating some form of weight sharing. Second, hardware-aware NAS is essential for deploying models on resource-constrained devices, with 78% of recent papers including hardware constraints. Third, one-shot NAS has matured to the point where it can match multi-trial performance, making it suitable for practical applications.' },
  { id: 'conclusion', title: '6. Conclusion', content: 'In this survey, we reviewed 87 papers on neural architecture search published between 2020 and 2026. We identified four key challenges in current NAS methods and reviewed 34 papers that address these challenges. Our analysis reveals that weight sharing, hardware-aware optimization, and one-shot NAS are the most promising directions for future research. We conclude with open challenges and future directions for NAS research.' },
];

const claims = [
  { id: 'c1', text: 'Weight sharing reduces search cost by 40% without quality loss', confidence: 'well_supported', confidence_score: 0.92, evidence_count: 12 },
  { id: 'c2', text: 'Hardware-aware constraints improve real-world latency by 25%', confidence: 'well_supported', confidence_score: 0.88, evidence_count: 8 },
  { id: 'c3', text: 'One-shot NAS matches multi-trial performance within 1% accuracy', confidence: 'well_supported', confidence_score: 0.85, evidence_count: 9 },
  { id: 'c4', text: 'Search space design significantly impacts final performance', confidence: 'weakly_supported', confidence_score: 0.72, evidence_count: 5 },
  { id: 'c5', text: 'Evolutionary algorithms outperform reinforcement learning', confidence: 'unsupported', confidence_score: 0.45, evidence_count: 2 },
  { id: 'c6', text: 'Gradient-based methods scale better than reinforcement learning', confidence: 'overstated', confidence_score: 0.35, evidence_count: 1 },
];

export function PaperEditorView() {
  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit');
  const [activeSection, setActiveSection] = useState<string>('abstract');

  const activeContent = paperSections.find(s => s.id === activeSection)?.content || '';

  const confidenceColors = {
    well_supported: 'bg-successLight text-success border-success',
    weakly_supported: 'bg-warningLight text-warning border-warning',
    unsupported: 'bg-errorLight text-error border-error',
    overstated: 'bg-errorLight text-error border-error',
  };

  const confidenceIcons = {
    well_supported: CheckCircle2,
    weakly_supported: AlertCircle,
    unsupported: AlertCircle,
    overstated: AlertCircle,
  };

  return (
    <div className="h-[calc(100vh-2rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div className="flex items-center gap-4">
          <button className="p-2 hover:bg-surfaceHover rounded-lg transition-colors">
            <ChevronLeft className="w-5 h-5 text-textSecondary" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-textPrimary">paper.tex</h1>
            <p className="text-xs text-textSecondary">Neural Architecture Search for Efficient Transformers</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-surface rounded-lg">
            <span className="text-xs text-textSecondary">Claim Confidence:</span>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 bg-success rounded-full" title="Well supported" />
              <div className="w-2 h-2 bg-warning rounded-full" title="Weakly supported" />
              <div className="w-2 h-2 bg-error rounded-full" title="Unsupported" />
            </div>
          </div>
          <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors flex items-center gap-2 text-sm">
            <CheckCircle2 className="w-4 h-4" />
            Run Review
          </button>
          <button className="px-4 py-2 bg-success hover:bg-successHover rounded-lg text-textInverse transition-colors flex items-center gap-2 text-sm">
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Editor */}
        <div className="w-1/2 flex flex-col border-r border-border">
          {/* Tabs */}
          <div className="flex items-center border-b border-border">
            <button
              onClick={() => setActiveTab('edit')}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                activeTab === 'edit'
                  ? 'border-b-2 border-accent text-accent'
                  : 'text-textSecondary hover:text-textPrimary'
              }`}
            >
              <Edit className="w-4 h-4 inline mr-2" />
              Edit
            </button>
            <button
              onClick={() => setActiveTab('preview')}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                activeTab === 'preview'
                  ? 'border-b-2 border-accent text-accent'
                  : 'text-textSecondary hover:text-textPrimary'
              }`}
            >
              <Eye className="w-4 h-4 inline mr-2" />
              Preview
            </button>
          </div>

          {/* Section Navigation */}
          <div className="flex-1 overflow-y-auto">
            <div className="w-48 border-r border-border">
              {paperSections.map((section) => (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`w-full text-left px-4 py-3 text-sm transition-colors ${
                    activeSection === section.id
                      ? 'bg-accentLight text-accent border-l-2 border-accent'
                      : 'text-textSecondary hover:bg-surfaceHover'
                  }`}
                >
                  {section.title}
                </button>
              ))}
            </div>
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-auto p-6 bg-background">
            {activeTab === 'edit' ? (
              <textarea
                value={activeContent}
                onChange={(e) => {
                  const newSections = paperSections.map(s =>
                    s.id === activeSection ? { ...s, content: e.target.value } : s
                  );
                  console.log('Updated sections:', newSections);
                }}
                className="w-full h-full resize-none font-mono text-sm text-textPrimary bg-surface p-4 rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-accentFocus"
                spellCheck={false}
              />
            ) : (
              <div className="prose max-w-none">
                <h1 className="text-3xl font-bold text-textPrimary mb-4">
                  Neural Architecture Search for Efficient Transformers
                </h1>
                <p className="text-sm text-textSecondary mb-6">
                  Georgios-Chrysovalantis Chatzivantsidis
                </p>
                <div className="bg-surface p-4 rounded-lg mb-6">
                  <h3 className="text-sm font-semibold text-textSecondary mb-2">Abstract</h3>
                  <p className="text-sm text-textPrimary leading-relaxed">
                    {paperSections.find(s => s.id === 'abstract')?.content}
                  </p>
                </div>
                {paperSections.map((section) => (
                  <div key={section.id} className="mb-6">
                    <h2 className="text-lg font-semibold text-textPrimary mb-2">{section.title}</h2>
                    <p className="text-sm text-textPrimary leading-relaxed">{section.content}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div className="w-80 bg-surface border-l border-border flex flex-col">
          <div className="p-4 border-b border-border">
            <h2 className="text-sm font-semibold text-textSecondary uppercase tracking-wider">
              Claim Confidence
            </h2>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {claims.map((claim) => {
              const ConfidenceIcon = confidenceIcons[claim.confidence];
              return (
                <div
                  key={claim.id}
                  className={`p-3 rounded-lg border ${confidenceColors[claim.confidence]}`}
                >
                  <div className="flex items-start gap-2">
                    <ConfidenceIcon className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    <p className="text-sm text-textPrimary leading-relaxed">
                      {claim.text}
                    </p>
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs opacity-75">
                      {claim.evidence_count} evidence
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium">{claim.confidence_score}</span>
                      <div className="w-16 h-1 bg-black/10 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${
                            claim.confidence_score > 0.8 ? 'bg-success' :
                            claim.confidence_score > 0.6 ? 'bg-warning' :
                            'bg-error'
                          }`}
                          style={{ width: `${claim.confidence_score * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="p-4 border-t border-border">
            <h3 className="text-sm font-semibold text-textSecondary mb-3">
              Paper Statistics
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-textSecondary">Sections</span>
                <span className="font-medium text-textPrimary">{paperSections.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Words</span>
                <span className="font-medium text-textPrimary">~2,450</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Figures</span>
                <span className="font-medium text-textPrimary">4</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Tables</span>
                <span className="font-medium text-textPrimary">3</span>
              </div>
              <div className="flex justify-between">
                <span className="text-textSecondary">Citations</span>
                <span className="font-medium text-textPrimary">45</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
