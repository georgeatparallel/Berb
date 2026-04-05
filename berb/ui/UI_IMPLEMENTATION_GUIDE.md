# Berb UI Implementation Guide

This document describes the UI implementation for Berb, following the specifications in `BERB_IMPLEMENTATION_PROMPT_v8_FINAL.md`.

## Overview

The Berb UI consists of:

1. **React Web Application** (`berb/ui/web/`) - Apple-inspired web interface
2. **FastAPI Backend** (`berb/api/server.py`) - REST API and WebSocket support
3. **Python Workflow System** (`berb/modes/workflow.py`) - Workflow configuration
4. **CLI Commands** - New commands for different workflow types

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Berb Web UI                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│  │  React App   │  │  FastAPI Backend │  │  Python Core    │   │
│  │  (Vite)      │  │  (Port 8000)     │  │  (Pipeline)     │   │
│  │              │  │                  │  │                 │   │
│  │ - Wizard     │  │ - REST API       │  │ - 23 stages     │   │
│  │ - Monitor    │  │ - WebSocket      │  │ - Workflows     │   │
│  │ - Literature │  │ - Presets        │  │ - Presets       │   │
│  │ - Paper      │  │ - Auth           │  │ - Operation     │   │
│  │ - Results    │  │                  │  │                 │   │
│  │ - Settings   │  │                  │  │                 │   │
│  └──────────────┘  └──────────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
berb/
├── ui/
│   ├── design-system/          # Design tokens (tokens.ts)
│   └── web/                    # React application
│       ├── src/
│       │   ├── components/     # Reusable components
│       │   │   └── layout.tsx  # Main layout with sidebar
│       │   ├── views/          # Page views
│       │   │   ├── Wizard.tsx              # New research wizard
│       │   │   ├── PipelineMonitor.tsx     # Live pipeline tracking
│       │   │   ├── LiteratureBrowser.tsx   # Paper browser
│       │   │   ├── PaperEditor.tsx         # LaTeX editor
│       │   │   ├── ResultsAnalytics.tsx    # Metrics & charts
│       │   │   └── Settings.tsx            # Configuration
│       │   ├── types/          # TypeScript types
│       │   │   └── index.ts    # Shared type definitions
│       │   ├── hooks/          # Custom React hooks
│       │   ├── utils/          # Utility functions
│       │   ├── design-system/  # Design tokens import
│       │   ├── app.tsx         # Main app with routing
│       │   ├── main.tsx        # Entry point
│       │   └── index.css       # Global styles
│       ├── package.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       ├── tsconfig.json
│       └── README.md
├── api/
│   ├── __init__.py
│   └── server.py               # FastAPI server
└── modes/
    ├── __init__.py
    ├── operation_mode.py       # Autonomous/collaborative modes
    └── workflow.py             # Workflow types (NEW)
```

## Design System

### Color Palette

Based on Apple Human Interface Guidelines with Berb Blue accent:

```typescript
{
  // Base
  background: '#FFFFFF',
  surface: '#F5F5F7',
  border: '#D2D2D7',
  
  // Text
  textPrimary: '#1D1D1F',
  textSecondary: '#6E6E73',
  
  // Accent - Berb Blue
  accent: '#0071E3',
  accentHover: '#0077ED',
  
  // Semantic
  success: '#34C759',
  warning: '#FF9F0A',
  error: '#FF3B30',
}
```

### Typography

```typescript
{
  fontFamily: '-apple-system, "SF Pro Display", sans-serif',
  body: { fontSize: '15px', lineHeight: 1.65 },
  heading: { fontSize: '22px', fontWeight: 600 },
}
```

### Spacing (8px grid)

```typescript
{
  xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48
}
```

## Workflow Types

### Implemented Workflows

| Workflow | Stages | Description |
|----------|--------|-------------|
| `full-research` | 1-23 | End-to-end research (default) |
| `literature-only` | 1-8 | Literature search + synthesis |
| `paper-from-results` | 14-23 | Write paper from existing results |
| `experiment-only` | 9-15 | Run experiments only |
| `review-only` | 18 | Review manuscript |
| `rebuttal` | Custom | Generate rebuttal letter |
| `literature-review` | 1-8, 16-23 | Standalone review paper |
| `math-paper` | 1-23 + O2 | Math-heavy paper |
| `computational-paper` | 1-23 + O3 | Computational paper |

### CLI Commands

```bash
# Full research (default)
berb run --topic "..." --preset ml-conference

# Literature-only
berb literature --topic "neural architecture search" --preset ml-conference

# Paper from results
berb write --topic "..." --data results/ --figures figures/

# Experiments only
berb experiment --hypothesis "X improves Y" --context background.md

# Review manuscript
berb review --manuscript paper.pdf --venue neurips

# Generate rebuttal
berb rebuttal --manuscript paper.pdf --reviews comments.txt

# Literature review
berb survey --topic "transformer efficiency" --preset ml-conference
```

## API Endpoints

### Research Jobs

```http
POST   /api/v1/research              # Create job
GET    /api/v1/research/{id}         # Get status
GET    /api/v1/research/{id}/stream  # SSE stream
POST   /api/v1/research/{id}/approve # Approve stage
POST   /api/v1/research/{id}/feedback # Submit feedback
GET    /api/v1/research/{id}/artifacts # Download artifacts
DELETE /api/v1/research/{id}         # Cancel job
```

### Presets

```http
GET    /api/v1/presets               # List presets
GET    /api/v1/presets/{name}        # Get preset details
```

### WebSocket

```http
WS /api/v1/research/{id}/ws          # Real-time updates
```

## React Components

### Layout

Three-zone layout with collapsible sidebar and context panel:

```typescript
<Layout>
  <Sidebar />        // 240px (collapsible)
  <MainCanvas />     // Main content area
  <ContextPanel />   // 320px (collapsible)
  <BottomBar />     // Always-visible progress
</Layout>
```

### Views

#### Wizard View

Step-by-step configuration:
1. Topic input
2. Workflow selection
3. Preset selection
4. Mode selection (autonomous/collaborative)
5. Summary

#### Pipeline Monitor

Real-time progress tracking:
- Phase indicators (A-H)
- Stage progress bars
- Cost tracker
- Model usage breakdown
- Stage output display

#### Literature Browser

Paper browsing with:
- Search and filters
- Citation profile visualization
- Berb confidence scores
- Reading notes integration

#### Paper Editor

Split-pane editor:
- LaTeX source (left)
- Rendered preview (right)
- Claim confidence sidebar
- Export functionality

#### Results Analytics

Metrics dashboard:
- Quality score progression
- Cost breakdown (pie chart)
- Claim integrity report
- Evidence consensus map
- Experiment results table

#### Settings

Configuration panel:
- API key management
- Theme toggle (light/dark)
- Language selection
- Default preset
- Notification preferences
- Privacy settings

## FastAPI Backend

### Key Features

- REST API for job management
- WebSocket for real-time updates
- Preset management
- CORS enabled for localhost:3000

### Running the Backend

```bash
cd berb/api
python -m berb.api.server
```

The server runs on `http://127.0.0.1:8000`.

## Integration Points

### CLI Integration

New workflow commands in `berb/cli.py`:
- `cmd_literature()` - Literature-only workflow
- `cmd_write()` - Paper from results
- `cmd_experiment()` - Experiments only
- `cmd_review()` - Review manuscript
- `cmd_rebuttal()` - Generate rebuttal
- `cmd_survey()` - Literature review

### Workflow Configuration

`berb/modes/workflow.py`:
- `WorkflowType` enum (9 types)
- `WorkflowConfig` model
- `WorkflowManager` class
- `WORKFLOW_STAGES` mapping

### Operation Modes

`berb/modes/operation_mode.py`:
- `OperationMode` enum (autonomous/collaborative)
- `CollaborativeConfig` model
- `OperationModeManager` class
- `AuditTrail` class for tracking decisions

## Development Workflow

### 1. Start Backend

```bash
cd berb/api
python -m berb.api.server
```

### 2. Start Frontend

```bash
cd berb/ui/web
npm install
npm run dev
```

### 3. Access UI

Open `http://localhost:3000` in your browser.

## Testing

### Frontend Tests

```bash
cd berb/ui/web
npm test
```

### Backend Tests

```bash
pytest tests/test_api_server.py
```

## Deployment

### Build Frontend

```bash
cd berb/ui/web
npm run build
```

### Deploy

The `dist/` directory can be deployed to:
- Vercel
- Netlify
- GitHub Pages
- Any static hosting

## Future Enhancements

### Phase 2 (P2)
- Dark mode support
- Advanced charting with Recharts
- Citation graph visualization
- Interactive evidence map

### Phase 3 (P3)
- Real-time collaboration
- Team workspace
- Shared research projects

## Troubleshooting

### Port Already in Use

```bash
# Change Vite port
npm run dev -- --port 3001

# Change FastAPI port
uvicorn berb.api.server:app --host 127.0.0.1 --port 8001
```

### CORS Errors

Ensure backend allows origins:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    ...
)
```

### Build Errors

```bash
# Clear cache
rm -rf node_modules/.vite
npm run build
```

## License

MIT License - See LICENSE file.
