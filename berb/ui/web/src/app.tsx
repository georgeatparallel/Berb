import React from 'react';
import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout';
import { WizardView } from './views/Wizard';
import { PipelineMonitorView } from './views/PipelineMonitor';
import { LiteratureBrowserView } from './views/LiteratureBrowser';
import { PaperEditorView } from './views/PaperEditor';
import { ResultsAnalyticsView } from './views/ResultsAnalytics';
import { SettingsView } from './views/Settings';

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<WizardView />} />
        <Route path="/new" element={<WizardView />} />
        <Route path="/research/:id" element={<PipelineMonitorView />} />
        <Route path="/research/:id/literature" element={<LiteratureBrowserView />} />
        <Route path="/research/:id/paper" element={<PaperEditorView />} />
        <Route path="/research/:id/results" element={<ResultsAnalyticsView />} />
        <Route path="/settings" element={<SettingsView />} />
      </Routes>
    </Layout>
  );
}
