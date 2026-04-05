# Berb Web UI

Apple-inspired web interface for Berb research automation system.

## Features

- **New Research Wizard** - Step-by-step guided setup for research projects
- **Pipeline Monitor** - Real-time progress tracking with stage indicators
- **Literature Browser** - Browse and analyze research papers with citation intelligence
- **Paper Editor** - LaTeX source editor with live preview
- **Results Analytics** - Quality metrics, cost breakdown, and evidence consensus
- **Settings** - Configure API keys, presets, and preferences

## Tech Stack

- **React 19** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Styling with Apple-inspired design tokens
- **Framer Motion** - Animations
- **Recharts** - Data visualization
- **TanStack Query** - Data fetching
- **Lucide React** - Icons

## Development

### Prerequisites

- Node.js >= 18.0.0
- npm >= 9.0.0
- Python 3.11+ (for FastAPI backend)

### Installation

```bash
cd berb/ui/web
npm install
```

### Development Server

```bash
npm run dev
```

The UI will be available at `http://localhost:3000`.

### Build

```bash
npm run build
```

### Lint

```bash
npm run lint
```

## Design System

The UI follows Apple Human Interface Guidelines:

- **Light theme** as primary
- **Berb Blue** (#0071E3) as primary accent
- **8px grid system** for spacing
- **Subtle shadows** and rounded corners
- **Smooth animations** with physics-based springs

See `src/design-system/tokens.ts` for all design tokens.

## API Integration

The UI connects to the FastAPI backend at `http://localhost:8000`:

- `POST /api/v1/research` - Create research job
- `GET /api/v1/research/{id}` - Get job status
- `GET /api/v1/research/{id}/stream` - SSE progress stream
- `POST /api/v1/research/{id}/approve` - Approve stage
- `GET /api/v1/presets` - List presets
- `WS /api/v1/research/{id}/ws` - WebSocket for real-time updates

## Project Structure

```
berb/ui/web/
├── src/
│   ├── components/     # Reusable UI components
│   ├── views/          # Page views (Wizard, PipelineMonitor, etc.)
│   ├── types/          # TypeScript type definitions
│   ├── hooks/          # Custom React hooks
│   ├── utils/          # Utility functions
│   ├── design-system/  # Design tokens and styles
│   ├── app.tsx         # Main app with routing
│   └── main.tsx        # Entry point
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── postcss.config.js
```

## Running with Backend

1. Start the FastAPI backend:
   ```bash
   cd berb/api
   python -m berb.api.server
   ```

2. Start the React dev server:
   ```bash
   cd berb/ui/web
   npm run dev
   ```

## Deployment

The UI can be deployed to any static hosting service:

```bash
npm run build
# Deploy the dist/ directory to Vercel, Netlify, etc.
```

## License

MIT License - See LICENSE file for details.
