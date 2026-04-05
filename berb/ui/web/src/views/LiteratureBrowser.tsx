import React, { useState } from 'react';
import { 
  Search,
  Filter,
  Download,
  BookOpen,
  Quote,
  FileText,
  BarChart3,
  ChevronRight,
  Star,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { designTokens } from '@design-system';
import type { Paper, CitationIntent } from '@types';

const papers: Paper[] = [
  {
    id: '1',
    title: 'Efficient Transformers: A Survey',
    authors: ['Tay, Y.', 'Dehghani, M.', 'Rastegari, M.', 'Wei, J.'],
    year: 2022,
    venue: 'ACM Computing Surveys',
    abstract: 'We survey the recent literature on efficient transformers, covering attention mechanisms, compression techniques, and hardware-aware optimization.',
    citations: 1247,
    cited_by: 89,
    berb_confidence: 0.94,
    citation_profile: {
      paper_id: '1',
      total_citations: 1247,
      supporting: 89,
      contrasting: 3,
      mentioning: 120,
      berb_confidence_score: 0.94,
    },
  },
  {
    id: '2',
    title: 'FlashAttention: Fast Memory-Efficient Attention',
    authors: ['Dao, T.', 'Fu, D.', 'Rajpurkar, S.', 'Landay, J.'],
    year: 2022,
    venue: 'NeurIPS',
    abstract: 'We introduce FlashAttention, a fast and memory-efficient exact attention algorithm that reduces memory complexity from O(n^2) to O(n).',
    citations: 2891,
    cited_by: 245,
    berb_confidence: 0.97,
  },
  {
    id: '3',
    title: 'Sparse Attention Patterns Achieve Comparable Accuracy',
    authors: ['Roy, A.', 'Saffar, M.', 'Dolan, C.', 'Goh, G.'],
    year: 2021,
    venue: 'arXiv preprint arXiv:2104.05704',
    abstract: 'We demonstrate that sparse attention patterns can achieve comparable accuracy to dense attention with O(n√n) complexity.',
    citations: 567,
    cited_by: 12,
    berb_confidence: 0.88,
  },
  {
    id: '4',
    title: 'Hardware-Aware Neural Architecture Search',
    authors: ['Cai, H.', 'Han, S.', 'Mao, M.'],
    year: 2023,
    venue: 'ICLR',
    abstract: 'We present a hardware-aware NAS framework that optimizes for real-world latency on target devices.',
    citations: 342,
    cited_by: 8,
    berb_confidence: 0.85,
  },
  {
    id: '5',
    title: 'One-Shot Neural Architecture Search',
    authors: ['Bender, G.', 'Ba, J.', 'Sermanet, P.'],
    year: 2020,
    venue: 'ICML',
    abstract: 'We propose a one-shot NAS method that trains a single super-network to discover high-performing architectures.',
    citations: 1890,
    cited_by: 45,
    berb_confidence: 0.91,
  },
];

const citationIntentColors: Record<CitationIntent, string> = {
  supporting: 'bg-successLight text-success',
  contrasting: 'bg-errorLight text-error',
  mentioning: 'bg-surfaceHover text-textSecondary',
};

export function LiteratureBrowserView() {
  const [searchQuery, setSearchQuery] = useState('');
  const [yearFilter, setYearFilter] = useState('2020-2026');
  const [minCitations, setMinCitations] = useState(50);
  const [selectedPaper, setSelectedPaper] = useState<Paper | null>(null);

  const filteredPapers = papers.filter((paper) => {
    const matchesSearch =
      paper.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      paper.authors.some((a) => a.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesYear = true; // Simplified
    const matchesCitations = paper.citations >= minCitations;
    return matchesSearch && matchesYear && matchesCitations;
  });

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-textPrimary">Literature</h1>
          <p className="text-sm text-textSecondary">
            {filteredPapers.length} found · {papers.filter((p) => p.berb_confidence > 0.9).length} included · 4 clusters
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button className="px-4 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-textPrimary transition-colors flex items-center gap-2">
            <Filter className="w-4 h-4" />
            Filter
          </button>
          <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors flex items-center gap-2">
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="card mb-6">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-textTertiary" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search papers..."
              className="input w-full pl-10"
            />
          </div>
          <div className="flex gap-3">
            <select
              value={yearFilter}
              onChange={(e) => setYearFilter(e.target.value)}
              className="input py-2"
            >
              <option value="2020-2026">2020-2026</option>
              <option value="2023-2026">2023-2026</option>
              <option value="2021-2023">2021-2023</option>
              <option value="all">All Years</option>
            </select>
            <input
              type="number"
              value={minCitations}
              onChange={(e) => setMinCitations(Number(e.target.value))}
              placeholder="Cited >"
              className="input w-24 py-2"
            />
          </div>
        </div>
      </div>

      {/* Paper List */}
      <div className="space-y-4">
        {filteredPapers.map((paper) => (
          <div
            key={paper.id}
            onClick={() => setSelectedPaper(paper)}
            className="card cursor-pointer hover:shadow-md transition-all duration-300 border-border"
          >
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <BookOpen className="w-4 h-4 text-textTertiary" />
                  <span className="text-xs text-textSecondary">{paper.venue} · {paper.year}</span>
                  <span className="text-xs text-textTertiary">|</span>
                  <span className="text-xs text-textSecondary">{paper.citations} citations</span>
                </div>
                <h3 className="text-lg font-semibold text-textPrimary mb-2 hover:text-accent transition-colors">
                  {paper.title}
                </h3>
                <p className="text-sm text-textSecondary mb-3 line-clamp-2">
                  {paper.abstract}
                </p>
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-textTertiary">
                    {paper.authors.slice(0, 3).join(', ')}{paper.authors.length > 3 ? ' et al.' : ''}
                  </span>
                  {paper.citation_profile && (
                    <>
                      <span className="text-textTertiary">|</span>
                      <span className="flex items-center gap-1 text-xs">
                        <Star className="w-3 h-3 text-warning" />
                        {paper.citation_profile.supporting} supporting
                      </span>
                      <span className="text-textTertiary">|</span>
                      <span className="flex items-center gap-1 text-xs">
                        <AlertCircle className="w-3 h-3 text-error" />
                        {paper.citation_profile.contrasting} contrasting
                      </span>
                    </>
                  )}
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-textSecondary">Berb confidence:</span>
                  <div className="w-24 h-1.5 bg-surfaceHover rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        paper.berb_confidence > 0.9 ? 'bg-success' :
                        paper.berb_confidence > 0.7 ? 'bg-accent' :
                        'bg-warning'
                      }`}
                      style={{ width: `${paper.berb_confidence * 100}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium text-textPrimary">{paper.berb_confidence}</span>
                </div>
                
                <div className="flex items-center gap-2">
                  <button className="px-3 py-1 text-xs bg-surface hover:bg-surfaceHover rounded transition-colors">
                    PDF
                  </button>
                  <button className="px-3 py-1 text-xs bg-surface hover:bg-surfaceHover rounded transition-colors">
                    Notes
                  </button>
                  <button className="px-3 py-1 text-xs bg-surface hover:bg-surfaceHover rounded transition-colors">
                    Map
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Paper Details Modal */}
      {selectedPaper && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-background rounded-xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto animate-fade-in-up">
            <div className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-xl font-semibold text-textPrimary mb-2">
                    {selectedPaper.title}
                  </h2>
                  <p className="text-sm text-textSecondary mb-3">
                    {selectedPaper.authors.join(', ')} · {selectedPaper.venue} · {selectedPaper.year}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedPaper(null)}
                  className="p-2 hover:bg-surfaceHover rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5 text-textSecondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="prose prose-sm max-w-none mb-6">
                <h4 className="text-sm font-semibold text-textSecondary mb-2">Abstract</h4>
                <p className="text-sm text-textSecondary leading-relaxed">
                  {selectedPaper.abstract}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-6">
                <div className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="w-4 h-4 text-accent" />
                    <span className="text-sm font-semibold text-textSecondary">Citations</span>
                  </div>
                  <div className="text-2xl font-semibold text-textPrimary">{selectedPaper.citations}</div>
                  <div className="text-xs text-textTertiary">Total citations</div>
                </div>
                <div className="card">
                  <div className="flex items-center gap-2 mb-2">
                    <BarChart3 className="w-4 h-4 text-success" />
                    <span className="text-sm font-semibold text-textSecondary">Berb Confidence</span>
                  </div>
                  <div className="text-2xl font-semibold text-textPrimary">{selectedPaper.berb_confidence}</div>
                  <div className="text-xs text-textTertiary">Based on evidence quality</div>
                </div>
              </div>

              {selectedPaper.citation_profile && (
                <div className="card mb-6">
                  <h4 className="text-sm font-semibold text-textSecondary mb-3">Citation Profile</h4>
                  <div className="space-y-3">
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 text-success" />
                          Supporting
                        </span>
                        <span className="font-medium text-textPrimary">{selectedPaper.citation_profile.supporting}</span>
                      </div>
                      <div className="w-full h-2 bg-surfaceHover rounded-full overflow-hidden">
                        <div
                          className="h-full bg-success rounded-full"
                          style={{ width: `${(selectedPaper.citation_profile.supporting / selectedPaper.citation_profile.total_citations) * 100}%` }}
                        />
                      </div>
                    </div>
                    <div>
                      <div className="flex justify-between text-sm mb-1">
                        <span className="flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-error" />
                          Contrasting
                        </span>
                        <span className="font-medium text-textPrimary">{selectedPaper.citation_profile.contrasting}</span>
                      </div>
                      <div className="w-full h-2 bg-surfaceHover rounded-full overflow-hidden">
                        <div
                          className="h-full bg-error rounded-full"
                          style={{ width: `${(selectedPaper.citation_profile.contrasting / selectedPaper.citation_profile.total_citations) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button className="flex-1 px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors flex items-center justify-center gap-2">
                  <FileText className="w-4 h-4" />
                  View PDF
                </button>
                <button className="flex-1 px-4 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-textPrimary transition-colors flex items-center justify-center gap-2">
                  <BookOpen className="w-4 h-4" />
                  Reading Notes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
