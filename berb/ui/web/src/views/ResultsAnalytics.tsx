import React from 'react';
import { 
  TrendingUp,
  DollarSign,
  BarChart3,
  Activity,
  Target,
  Clock,
  CheckCircle2,
  AlertCircle,
  ChevronRight
} from 'lucide-react';
import { designTokens } from '@design-system';

export function ResultsAnalyticsView() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-textPrimary">Results & Analytics</h1>
          <p className="text-sm text-textSecondary">Performance metrics and quality assessment</p>
        </div>
        <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors flex items-center gap-2">
          <Target className="w-4 h-4" />
          Set Goals
        </button>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-4 gap-4">
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-accent" />
            <span className="text-sm font-semibold text-textSecondary">Quality Score</span>
          </div>
          <div className="text-3xl font-semibold text-textPrimary">8.7/10</div>
          <div className="flex items-center gap-1 mt-1">
            <TrendingUp className="w-3 h-3 text-success" />
            <span className="text-xs text-success">+0.4 from baseline</span>
          </div>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-success" />
            <span className="text-sm font-semibold text-textSecondary">Total Cost</span>
          </div>
          <div className="text-3xl font-semibold text-textPrimary">$0.85</div>
          <div className="flex items-center gap-1 mt-1">
            <span className="text-xs text-textSecondary">/ $2.00 budget</span>
          </div>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-warning" />
            <span className="text-sm font-semibold text-textSecondary">Time</span>
          </div>
          <div className="text-3xl font-semibold text-textPrimary">1h 23m</div>
          <div className="flex items-center gap-1 mt-1">
            <span className="text-xs text-textSecondary">~87% efficiency</span>
          </div>
        </div>
        
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-purple-500" />
            <span className="text-sm font-semibold text-textSecondary">Papers</span>
          </div>
          <div className="text-3xl font-semibold text-textPrimary">34</div>
          <div className="flex items-center gap-1 mt-1">
            <span className="text-xs text-textSecondary">from 87 found</span>
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-sm font-semibold text-textSecondary mb-4">Quality Score Progression</h3>
          <div className="h-48 flex items-end justify-between gap-2">
            {[6.2, 6.8, 7.1, 7.5, 7.9, 8.2, 8.5, 8.7].map((score, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-2">
                <div
                  className="w-full bg-accent rounded-t-lg transition-all duration-500"
                  style={{ height: `${(score / 10) * 100}%` }}
                />
                <span className="text-xs text-textSecondary">{i + 1}</span>
              </div>
            ))}
          </div>
        </div>
        
        <div className="card">
          <h3 className="text-sm font-semibold text-textSecondary mb-4">Cost Breakdown</h3>
          <div className="h-48 flex items-center justify-center">
            <div className="relative w-32 h-32 rounded-full border-8 border-surfaceHover flex items-center justify-center">
              <div className="absolute inset-0 rounded-full border-8 border-success" style={{ clipPath: 'inset(0 0 50% 0)' }} />
              <div className="absolute inset-0 rounded-full border-8 border-warning" style={{ clipPath: 'inset(50% 0 0 0)' }} />
              <div className="absolute inset-0 rounded-full border-8 border-accent" style={{ clipPath: 'inset(0 50% 0 0)' }} />
              <div className="absolute inset-0 rounded-full border-8 border-error" style={{ clipPath: 'inset(0 0 0 50%)' }} />
              <div className="text-center">
                <div className="text-2xl font-semibold text-textPrimary">$0.85</div>
                <div className="text-xs text-textSecondary">Total</div>
              </div>
            </div>
          </div>
          <div className="space-y-2 mt-4">
            {[
              { label: 'Literature Search', cost: 0.25, color: 'bg-success' },
              { label: 'Synthesis', cost: 0.15, color: 'bg-warning' },
              { label: 'Hypothesis Gen', cost: 0.20, color: 'bg-accent' },
              { label: 'Writing', cost: 0.25, color: 'bg-error' },
            ].map((item, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${item.color}`} />
                  <span className="text-textSecondary">{item.label}</span>
                </div>
                <span className="font-medium text-textPrimary">${item.cost.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Claim Integrity Report */}
      <div className="card">
        <h3 className="text-lg font-semibold text-textPrimary mb-4">Claim Integrity Report</h3>
        <div className="space-y-3">
          {[
            { id: 1, claim: 'Weight sharing reduces search cost by 40%', confidence: 'well_supported', evidence: 12, papers: ['Roy et al., 2021', 'Cai et al., 2020'] },
            { id: 2, claim: 'Hardware-aware constraints improve latency by 25%', confidence: 'well_supported', evidence: 8, papers: ['Cai et al., 2023', 'Bender et al., 2020'] },
            { id: 3, claim: 'One-shot NAS matches multi-trial within 1%', confidence: 'well_supported', evidence: 9, papers: ['Bender et al., 2020', 'Cai et al., 2023'] },
            { id: 4, claim: 'Search space design impacts performance', confidence: 'weakly_supported', evidence: 5, papers: ['Roy et al., 2021'] },
            { id: 5, claim: 'Evolutionary algorithms outperform RL', confidence: 'unsupported', evidence: 2, papers: ['Baker et al., 2018'] },
          ].map((item) => (
            <div key={item.id} className="flex items-start gap-3 p-3 bg-surface rounded-lg">
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                item.confidence === 'well_supported' ? 'bg-successLight text-success' :
                item.confidence === 'weakly_supported' ? 'bg-warningLight text-warning' :
                'bg-errorLight text-error'
              }`}>
                {item.confidence === 'well_supported' ? (
                  <CheckCircle2 className="w-5 h-5" />
                ) : (
                  <AlertCircle className="w-5 h-5" />
                )}
              </div>
              <div className="flex-1">
                <p className="text-sm text-textPrimary mb-1">{item.claim}</p>
                <div className="flex items-center gap-3 text-xs">
                  <span className={`font-medium ${
                    item.confidence === 'well_supported' ? 'text-success' :
                    item.confidence === 'weakly_supported' ? 'text-warning' :
                    'text-error'
                  }`}>
                    {item.confidence.replace('_', ' ')}
                  </span>
                  <span className="text-textTertiary">|</span>
                  <span className="text-textSecondary">{item.evidence} evidence</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {item.papers.map((paper, i) => (
                    <span key={i} className="px-2 py-0.5 bg-surfaceHover rounded text-xs text-textTertiary">
                      {paper}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Evidence Consensus Map */}
      <div className="card">
        <h3 className="text-lg font-semibold text-textPrimary mb-4">Evidence Consensus Map</h3>
        <div className="h-64 flex items-center justify-center bg-surface rounded-lg">
          <div className="text-center">
            <div className="w-48 h-48 mx-auto mb-4 relative">
              <div className="absolute inset-0 rounded-full border-2 border-accent opacity-30" />
              <div className="absolute inset-4 rounded-full border-2 border-success opacity-30" />
              <div className="absolute inset-8 rounded-full border-2 border-warning opacity-30" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-4 h-4 bg-accent rounded-full" />
              </div>
              <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-4">
                <div className="w-3 h-3 bg-success rounded-full" />
              </div>
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-4">
                <div className="w-3 h-3 bg-warning rounded-full" />
              </div>
              <div className="absolute left-0 top-1/2 -translate-x-4 -translate-y-1/2">
                <div className="w-3 h-3 bg-error rounded-full" />
              </div>
              <div className="absolute right-0 top-1/2 translate-x-4 -translate-y-1/2">
                <div className="w-3 h-3 bg-purple-500 rounded-full" />
              </div>
            </div>
            <p className="text-sm text-textSecondary">
              Central claim supported by 12 papers, with 8 supporting and 3 contrasting evidence
            </p>
          </div>
        </div>
      </div>

      {/* Experiment Results */}
      <div className="card">
        <h3 className="text-lg font-semibold text-textPrimary mb-4">Experiment Results</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="py-3 px-4 font-semibold text-textSecondary">Metric</th>
                <th className="py-3 px-4 font-semibold text-textSecondary">Baseline</th>
                <th className="py-3 px-4 font-semibold text-textSecondary">Ours</th>
                <th className="py-3 px-4 font-semibold text-textSecondary">Improvement</th>
                <th className="py-3 px-4 font-semibold text-textSecondary">Significance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {[
                { metric: 'Search Cost', baseline: '100%', ours: '60%', improvement: '-40%', sig: '***' },
                { metric: 'Latency', baseline: '100ms', ours: '75ms', improvement: '-25%', sig: '***' },
                { metric: 'Accuracy', baseline: '78.2%', ours: '79.1%', improvement: '+0.9%', sig: '*' },
                { metric: 'Parameters', baseline: '12.5M', ours: '10.2M', improvement: '-18%', sig: '***' },
                { metric: 'Training Time', baseline: '24h', ours: '18h', improvement: '-25%', sig: '**' },
              ].map((row, i) => (
                <tr key={i} className="hover:bg-surfaceHover/50">
                  <td className="py-3 px-4 text-textPrimary">{row.metric}</td>
                  <td className="py-3 px-4 text-textSecondary">{row.baseline}</td>
                  <td className="py-3 px-4 text-accent font-medium">{row.ours}</td>
                  <td className={`py-3 px-4 font-medium ${row.improvement.startsWith('+') ? 'text-success' : 'text-error'}`}>
                    {row.improvement}
                  </td>
                  <td className="py-3 px-4">
                    <span className={`font-bold ${
                      row.sig === '***' ? 'text-error' :
                      row.sig === '**' ? 'text-warning' :
                      'text-textSecondary'
                    }`}>{row.sig}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
