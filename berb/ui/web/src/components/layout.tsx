import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  BookOpen, 
  FileText, 
  BarChart3, 
  Settings, 
  Menu, 
  X, 
  ChevronLeft, 
  ChevronRight,
  Brain,
  FlaskConical,
  Search,
  PenTool,
  CheckCircle2
} from 'lucide-react';
import { designTokens } from '@design-system';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [contextPanelOpen, setContextPanelOpen] = useState(true);
  const location = useLocation();

  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/' },
    { icon: BookOpen, label: 'Literature', path: '/literature' },
    { icon: FileText, label: 'Paper', path: '/paper' },
    { icon: BarChart3, label: 'Results', path: '/results' },
    { icon: Settings, label: 'Settings', path: '/settings' },
  ];

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? 'w-60' : 'w-16'
        } flex-shrink-0 bg-surface border-r border-border transition-all duration-300 ease-in-out flex flex-col`}
      >
        <div className="h-14 flex items-center px-4 border-b border-border">
          {sidebarOpen ? (
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center">
                <FlaskConical className="w-5 h-5 text-textInverse" />
              </div>
              <span className="font-semibold text-textPrimary">Berb</span>
            </div>
          ) : (
            <div className="w-8 h-8 bg-accent rounded-lg flex items-center justify-center mx-auto">
              <FlaskConical className="w-5 h-5 text-textInverse" />
            </div>
          )}
        </div>

        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const isActive = location.pathname.includes(item.path.replace('/', ''));
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 ${
                  isActive
                    ? 'bg-accentLight text-accent'
                    : 'text-textSecondary hover:bg-surfaceHover hover:text-textPrimary'
                }`}
              >
                <item.icon className="w-5 h-5" />
                {sidebarOpen && <span className="text-sm font-medium">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="flex items-center justify-center w-full p-2 rounded-lg hover:bg-surfaceHover transition-colors"
          >
            {sidebarOpen ? (
              <ChevronLeft className="w-4 h-4 text-textSecondary" />
            ) : (
              <ChevronRight className="w-4 h-4 text-textSecondary" />
            )}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-background border-b border-border flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold text-textPrimary">
              {location.pathname === '/' ? 'New Research' : 'Pipeline Monitor'}
            </h1>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-full hover:bg-surfaceHover transition-colors relative">
              <div className="w-5 h-5 text-textSecondary">
                <Search />
              </div>
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full"></span>
            </button>
            <button className="p-2 rounded-full hover:bg-surfaceHover transition-colors">
              <div className="w-5 h-5 text-textSecondary">
                <CheckCircle2 />
              </div>
            </button>
            <div className="w-8 h-8 bg-accent rounded-full flex items-center justify-center">
              <span className="text-xs font-semibold text-textInverse">GC</span>
            </div>
          </div>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-auto bg-background">
          {children}
        </div>

        {/* Bottom Bar */}
        <div className="h-12 bg-surface border-t border-border flex items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-32 h-1.5 bg-surfaceHover rounded-full overflow-hidden">
                <div className="w-3/4 h-full bg-accent rounded-full"></div>
              </div>
              <span className="text-xs text-textSecondary">Stage 8 of 23</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-textSecondary">Cost:</span>
              <span className="text-sm font-medium text-textPrimary">$0.42</span>
              <span className="text-xs text-textTertiary">/ $2.00</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-xs text-textSecondary">Models:</span>
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 bg-accent rounded-full"></div>
                <span className="text-xs text-textSecondary">Claude</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 bg-success rounded-full"></div>
                <span className="text-xs text-textSecondary">GPT-4o</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 bg-warning rounded-full"></div>
                <span className="text-xs text-textSecondary">Flash</span>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Context Panel */}
      {contextPanelOpen && (
        <aside className="w-80 bg-surface border-l border-border flex-shrink-0 flex flex-col">
          <div className="h-14 flex items-center px-4 border-b border-border">
            <span className="text-sm font-semibold text-textPrimary">Context</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className="card">
              <h3 className="text-sm font-semibold text-textPrimary mb-2">Stage Details</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Current Stage</span>
                  <span className="text-textPrimary font-medium">Hypothesis Generation</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Progress</span>
                  <span className="text-textPrimary font-medium">78%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Cost</span>
                  <span className="text-textPrimary font-medium">$0.15</span>
                </div>
              </div>
            </div>
            <div className="card">
              <h3 className="text-sm font-semibold text-textPrimary mb-2">Cost Tracker</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Total Cost</span>
                  <span className="text-textPrimary font-medium">$0.42</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-textSecondary">Budget</span>
                  <span className="text-textPrimary font-medium">$2.00</span>
                </div>
                <div className="w-full h-1.5 bg-surfaceHover rounded-full overflow-hidden">
                  <div className="w-21 h-full bg-accent rounded-full"></div>
                </div>
              </div>
            </div>
            <div className="card">
              <h3 className="text-sm font-semibold text-textPrimary mb-2">Paper Preview</h3>
              <div className="space-y-2">
                <div className="text-sm text-textSecondary">
                  <span className="font-medium">Neural Architecture Search</span>
                </div>
                <div className="text-xs text-textTertiary">
                  12 pages · 87 citations · 4 figures
                </div>
              </div>
            </div>
          </div>
        </aside>
      )}
    </div>
  );
}
