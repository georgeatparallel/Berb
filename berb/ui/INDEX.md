# Berb UI Documentation Index

This directory contains the complete UI implementation for Berb, an AI-powered autonomous research system.

## Quick Links

- **[QUICK_START.md](QUICK_START.md)** - Get started in 5 minutes
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - What was implemented
- **[UI_IMPLEMENTATION_GUIDE.md](UI_IMPLEMENTATION_GUIDE.md)** - Detailed implementation guide
- **[web/README.md](web/README.md)** - Web UI documentation

## Directory Structure

```
berb/ui/
├── QUICK_START.md              # Get started in 5 minutes
├── IMPLEMENTATION_SUMMARY.md   # What was implemented
├── UI_IMPLEMENTATION_GUIDE.md  # Detailed implementation guide
├── INDEX.md                    # This file
├── design-system/              # Design tokens
│   └── tokens.ts
├── web/                        # React application
│   ├── src/
│   │   ├── components/         # Reusable components
│   │   │   └── layout.tsx      # Main layout
│   │   ├── views/              # Page views
│   │   │   ├── Wizard.tsx              # New research wizard
│   │   │   ├── PipelineMonitor.tsx     # Live pipeline tracking
│   │   │   ├── LiteratureBrowser.tsx   # Paper browser
│   │   │   ├── PaperEditor.tsx         # LaTeX editor
│   │   │   ├── ResultsAnalytics.tsx    # Metrics dashboard
│   │   │   └── Settings.tsx            # Configuration
│   │   ├── types/              # TypeScript types
│   │   │   └── index.ts        # Type definitions
│   │   ├── hooks/              # Custom React hooks
│   │   ├── utils/              # Utility functions
│   │   ├── design-system/      # Design tokens import
│   │   ├── app.tsx             # Main app with routing
│   │   ├── main.tsx            # Entry point
│   │   └── index.css           # Global styles
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── index.html
│   └── README.md
└── api/                        # FastAPI backend
    ├── __init__.py
    └── server.py
```

## Documentation Guide

### For Users

1. **Start Here**: [QUICK_START.md](QUICK_START.md)
   - Installation
   - Running the UI
   - Basic usage

2. **After Setup**: [web/README.md](web/README.md)
   - Feature overview
   - Tech stack
   - Development

### For Developers

1. **Implementation Summary**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
   - What was implemented
   - Architecture overview
   - Files created/modified

2. **Implementation Guide**: [UI_IMPLEMENTATION_GUIDE.md](UI_IMPLEMENTATION_GUIDE.md)
   - Detailed architecture
   - Component breakdown
   - API endpoints
   - Integration points

### For Maintainers

1. **Design System**: `design-system/tokens.ts`
   - Color palette
   - Typography
   - Spacing
   - Animation tokens

2. **Type Definitions**: `web/src/types/index.ts`
   - Workflow types
   - API models
   - Domain models

3. **Source Code**:
   - `web/src/views/` - All views
   - `api/server.py` - Backend API
   - `modes/workflow.py` - Workflow system

## What's Included

### React Application

- **6 Views**:
  1. Wizard - Step-by-step research setup
  2. Pipeline Monitor - Real-time progress tracking
  3. Literature Browser - Paper browsing with citations
  4. Paper Editor - LaTeX editor with preview
  5. Results Analytics - Metrics and charts
  6. Settings - Configuration

- **Features**:
  - Apple-inspired design
  - Responsive layout
  - Real-time updates
  - Dark mode ready
  - Type-safe with TypeScript

### FastAPI Backend

- **REST API**:
  - Research job management
  - Preset management
  - Stage approval
  - Artifact downloads

- **WebSocket**:
  - Real-time progress updates
  - Collaborative mode support

- **SSE**:
  - Server-sent events for streaming

### Python Workflow System

- **9 Workflow Types**:
  1. Full Research (all 23 stages)
  2. Literature Only (stages 1-8)
  3. Paper from Results (stages 14-23)
  4. Experiment Only (stages 9-15)
  5. Review Only (stage 18)
  6. Rebuttal (custom)
  7. Literature Review (stages 1-8, 16-23)
  8. Math Paper (all + math engine)
  9. Computational Paper (all + code appendix)

- **Operation Modes**:
  - Autonomous (zero human intervention)
  - Collaborative (human-in-the-loop)

### CLI Commands

- `literature` - Literature-only workflow
- `write` - Paper from results
- `experiment` - Experiments only
- `review` - Review manuscript
- `rebuttal` - Generate rebuttal
- `survey` - Literature review

## Design System

### Colors

- **Background**: `#FFFFFF`
- **Surface**: `#F5F5F7`
- **Border**: `#D2D2D7`
- **Text Primary**: `#1D1D1F`
- **Text Secondary**: `#6E6E73`
- **Berb Blue (Accent)**: `#0071E3`
- **Success**: `#34C759`
- **Warning**: `#FF9F0A`
- **Error**: `#FF3B30`

### Typography

- **Font Family**: `-apple-system, "SF Pro Display", sans-serif`
- **Body**: 15px, 1.65 line-height
- **Heading**: 22px, 600 weight
- **Code**: Monospace

### Spacing

- **8px Grid**: xs=4, sm=8, md=16, lg=24, xl=32, xxl=48

## API Endpoints

### Research Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/research` | Create job |
| GET | `/api/v1/research/{id}` | Get status |
| GET | `/api/v1/research/{id}/stream` | SSE stream |
| POST | `/api/v1/research/{id}/approve` | Approve stage |
| POST | `/api/v1/research/{id}/feedback` | Submit feedback |
| GET | `/api/v1/research/{id}/artifacts` | Download artifacts |
| DELETE | `/api/v1/research/{id}` | Cancel job |

### Presets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/presets` | List presets |
| GET | `/api/v1/presets/{name}` | Get preset |

### WebSocket

| Event | Endpoint | Description |
|-------|----------|-------------|
| Connection | `WS /api/v1/research/{id}/ws` | Real-time updates |

## Running the UI

### Development

```bash
# Terminal 1 - Backend
cd berb/api
python -m berb.api.server

# Terminal 2 - Frontend
cd berb/ui/web
npm run dev
```

### Production

```bash
# Build frontend
cd berb/ui/web
npm run build

# Deploy dist/ directory to Vercel, Netlify, etc.
```

## Next Steps

1. **Read QUICK_START.md** for installation and basic usage
2. **Explore the UI** at http://localhost:3000
3. **Configure API keys** in Settings
4. **Start your first research** using the Wizard

## Support

- **Issues**: GitHub Issues
- **Documentation**: See individual files
- **Examples**: See QUICK_START.md

## License

MIT License - See LICENSE file.
