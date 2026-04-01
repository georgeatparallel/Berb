import React, { useState } from 'react';
import { 
  Settings,
  Key,
  Globe,
  Palette,
  Bell,
  Shield,
  Zap,
  FileText,
  Database,
  Cloud,
  CheckCircle2
} from 'lucide-react';
import { designTokens } from '@design-system';

export function SettingsView() {
  const [activeTab, setActiveTab] = useState<'general' | 'api' | 'appearance' | 'notifications' | 'privacy' | 'advanced'>('general');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [language, setLanguage] = useState('en');

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold text-textPrimary mb-6">Settings</h1>

      <div className="grid grid-cols-12 gap-6">
        {/* Sidebar */}
        <div className="col-span-3">
          <div className="space-y-1">
            <button
              onClick={() => setActiveTab('general')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'general'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Settings className="w-5 h-5" />
              <span className="font-medium">General</span>
            </button>
            <button
              onClick={() => setActiveTab('api')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'api'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Key className="w-5 h-5" />
              <span className="font-medium">API Keys</span>
            </button>
            <button
              onClick={() => setActiveTab('appearance')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'appearance'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Palette className="w-5 h-5" />
              <span className="font-medium">Appearance</span>
            </button>
            <button
              onClick={() => setActiveTab('notifications')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'notifications'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Bell className="w-5 h-5" />
              <span className="font-medium">Notifications</span>
            </button>
            <button
              onClick={() => setActiveTab('privacy')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'privacy'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Shield className="w-5 h-5" />
              <span className="font-medium">Privacy</span>
            </button>
            <button
              onClick={() => setActiveTab('advanced')}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                activeTab === 'advanced'
                  ? 'bg-accentLight text-accent'
                  : 'text-textSecondary hover:bg-surfaceHover'
              }`}
            >
              <Zap className="w-5 h-5" />
              <span className="font-medium">Advanced</span>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="col-span-9">
          {activeTab === 'general' && (
            <div className="space-y-6 animate-fade-in-up">
              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Globe className="w-5 h-5 text-accent" />
                  Language & Region
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Interface Language
                    </label>
                    <select
                      value={language}
                      onChange={(e) => setLanguage(e.target.value)}
                      className="input w-full max-w-xs"
                    >
                      <option value="en">English</option>
                      <option value="el">Greek (Ελληνικά)</option>
                      <option value="es">Spanish (Español)</option>
                      <option value="fr">French (Français)</option>
                      <option value="de">German (Deutsch)</option>
                      <option value="zh">Chinese (中文)</option>
                      <option value="ja">Japanese (日本語)</option>
                      <option value="ko">Korean (한국어)</option>
                      <option value="pt">Portuguese (Português)</option>
                      <option value="ru">Russian (Русский)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Time Zone
                    </label>
                    <select className="input w-full max-w-xs">
                      <option value="UTC">UTC (Coordinated Universal Time)</option>
                      <option value="America/New_York">America/New_York</option>
                      <option value="Europe/Athens">Europe/Athens</option>
                      <option value="Asia/Tokyo">Asia/Tokyo</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-accent" />
                  Default Preset
                </h3>
                <div>
                  <label className="block text-sm font-medium text-textSecondary mb-2">
                    Default Research Preset
                  </label>
                  <select className="input w-full max-w-xs">
                    <option value="ml-conference">ML Conference (NeurIPS, ICML, ICLR)</option>
                    <option value="biomedical">Biomedical Research</option>
                    <option value="nlp">Natural Language Processing</option>
                    <option value="computer-vision">Computer Vision</option>
                    <option value="physics">Physics / Computational Science</option>
                  </select>
                  <p className="text-xs text-textTertiary mt-2">
                    This preset will be used when you start a new research without specifying one
                  </p>
                </div>
              </div>

              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Database className="w-5 h-5 text-accent" />
                  Knowledge Base
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Obsidian Vault Path
                    </label>
                    <input
                      type="text"
                      placeholder="/path/to/obsidian/vault"
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Zotero Collection
                    </label>
                    <input
                      type="text"
                      placeholder="My Research"
                      className="input w-full"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'api' && (
            <div className="space-y-6 animate-fade-in-up">
              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Key className="w-5 h-5 text-accent" />
                  LLM API Keys
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      OpenAI API Key
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value="sk-..."
                        readOnly
                        className="input flex-1"
                      />
                      <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors">
                        Edit
                      </button>
                    </div>
                    <p className="text-xs text-textTertiary mt-2">
                      Required for GPT-4o, o1 models
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Anthropic API Key
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value="sk-ant-..."
                        readOnly
                        className="input flex-1"
                      />
                      <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors">
                        Edit
                      </button>
                    </div>
                    <p className="text-xs text-textTertiary mt-2">
                      Required for Claude Sonnet, Opus
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Google Gemini API Key
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value="AI..."
                        readOnly
                        className="input flex-1"
                      />
                      <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors">
                        Edit
                      </button>
                    </div>
                    <p className="text-xs text-textTertiary mt-2">
                      Required for Gemini 2.5 Flash, Pro
                    </p>
                  </div>
                </div>
              </div>

              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Cloud className="w-5 h-5 text-accent" />
                  Search & Scraping
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      SearXNG Endpoint
                    </label>
                    <input
                      type="text"
                      value="http://localhost:8080"
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-textSecondary mb-2">
                      Firecrawl Endpoint
                    </label>
                    <input
                      type="text"
                      value="http://localhost:3002"
                      className="input w-full"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'appearance' && (
            <div className="space-y-6 animate-fade-in-up">
              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Palette className="w-5 h-5 text-accent" />
                  Theme
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <button
                    onClick={() => setTheme('light')}
                    className={`p-4 rounded-lg border-2 transition-colors ${
                      theme === 'light'
                        ? 'border-accent bg-accentLight/50'
                        : 'border-border hover:border-accent'
                    }`}
                  >
                    <div className="w-full h-32 bg-white rounded mb-3 border border-border" />
                    <span className="font-medium text-textPrimary">Light</span>
                    <div className={`w-4 h-4 rounded-full mt-2 ${theme === 'light' ? 'bg-accent' : 'bg-surfaceHover'}`} />
                  </button>
                  <button
                    onClick={() => setTheme('dark')}
                    className={`p-4 rounded-lg border-2 transition-colors ${
                      theme === 'dark'
                        ? 'border-accent bg-accentLight/50'
                        : 'border-border hover:border-accent'
                    }`}
                  >
                    <div className="w-full h-32 bg-gray-900 rounded mb-3 border border-gray-700" />
                    <span className="font-medium text-textPrimary">Dark</span>
                    <div className={`w-4 h-4 rounded-full mt-2 ${theme === 'dark' ? 'bg-accent' : 'bg-surfaceHover'}`} />
                  </button>
                </div>
              </div>

              <div className="card">
                <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                  <Zap className="w-5 h-5 text-accent" />
                  UI Preferences
                </h3>
                <div className="space-y-3">
                  {[
                    { label: 'Show progress bars', default: true },
                    { label: 'Show cost estimates', default: true },
                    { label: 'Show model usage breakdown', default: true },
                    { label: 'Show ETA estimates', default: true },
                    { label: 'Show claim confidence indicators', default: true },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <span className="text-sm text-textPrimary">{item.label}</span>
                      <div className="w-10 h-5 bg-accent rounded-full relative">
                        <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'notifications' && (
            <div className="card animate-fade-in-up">
              <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                <Bell className="w-5 h-5 text-accent" />
                Notifications
              </h3>
              <div className="space-y-3">
                {[
                  { label: 'Pipeline completion', description: 'Receive notification when research completes', default: true },
                  { label: 'Cost threshold exceeded', description: 'Alert when approaching budget limit', default: true },
                  { label: 'Stage approval required', description: 'Notify when collaborative mode pauses', default: true },
                  { label: 'Quality issues detected', description: 'Alert for low-quality outputs', default: true },
                  { label: 'Weekly summary', description: 'Weekly digest of research activity', default: false },
                ].map((item, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-surface rounded-lg">
                    <div>
                      <span className="text-sm font-medium text-textPrimary block">{item.label}</span>
                      <span className="text-xs text-textTertiary">{item.description}</span>
                    </div>
                    <div className="w-10 h-5 bg-accent rounded-full relative">
                      <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === 'privacy' && (
            <div className="card animate-fade-in-up">
              <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                <Shield className="w-5 h-5 text-accent" />
                Privacy & Data
              </h3>
              <div className="space-y-4">
                <div className="p-4 bg-surface rounded-lg">
                  <h4 className="text-sm font-semibold text-textPrimary mb-2">Data Retention</h4>
                  <p className="text-sm text-textSecondary mb-3">
                    Research data is stored for 90 days by default. After this period, raw outputs are deleted while metadata is retained for analytics.
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-textSecondary">Retention period:</span>
                    <select className="input py-1 text-sm">
                      <option value="30">30 days</option>
                      <option value="90">90 days</option>
                      <option value="180">180 days</option>
                      <option value="365">365 days</option>
                      <option value="forever">Forever</option>
                    </select>
                  </div>
                </div>

                <div className="p-4 bg-surface rounded-lg">
                  <h4 className="text-sm font-semibold text-textPrimary mb-2">Data Sharing</h4>
                  <div className="space-y-2">
                    {[
                      { label: 'Share anonymized research data', description: 'Help improve Berb for everyone', default: false },
                      { label: 'Share error reports', description: 'Include stack traces and error messages', default: true },
                      { label: 'Share performance data', description: 'Include timing and cost metrics', default: false },
                    ].map((item, i) => (
                      <div key={i} className="flex items-center justify-between">
                        <div>
                          <span className="text-sm text-textPrimary block">{item.label}</span>
                          <span className="text-xs text-textTertiary">{item.description}</span>
                        </div>
                        <div className="w-10 h-5 bg-accent rounded-full relative">
                          <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full" />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'advanced' && (
            <div className="card animate-fade-in-up">
              <h3 className="text-lg font-semibold text-textPrimary mb-4 flex items-center gap-2">
                <Zap className="w-5 h-5 text-accent" />
                Advanced Configuration
              </h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-textSecondary mb-2">
                    Default Operation Mode
                  </label>
                  <select className="input w-full max-w-xs">
                    <option value="autonomous">Autonomous (Zero human intervention)</option>
                    <option value="collaborative">Collaborative (Human-in-the-loop)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-textSecondary mb-2">
                    Max Parallel Tasks
                  </label>
                  <input
                    type="number"
                    defaultValue={3}
                    className="input w-full max-w-xs"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-textSecondary mb-2">
                    Retry Policy
                  </label>
                  <select className="input w-full max-w-xs">
                    <option value="2">2 retries</option>
                    <option value="3">3 retries</option>
                    <option value="5">5 retries</option>
                    <option value="0">No retries</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-textSecondary mb-2">
                    Timeout (minutes)
                  </label>
                  <input
                    type="number"
                    defaultValue={60}
                    className="input w-full max-w-xs"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 flex justify-end gap-3">
        <button className="px-4 py-2 bg-surface hover:bg-surfaceHover rounded-lg text-textPrimary transition-colors">
          Reset to Defaults
        </button>
        <button className="px-4 py-2 bg-accent hover:bg-accentHover rounded-lg text-textInverse transition-colors flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          Save Changes
        </button>
      </div>
    </div>
  );
}
