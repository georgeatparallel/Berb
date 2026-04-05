# Berb UI Quick Start

Get the Berb UI up and running in 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+

## Installation

### 1. Install Python Dependencies

```bash
cd E:\Documents\Vibe-Coding\Berb
pip install -e ".[all]"
```

### 2. Install Frontend Dependencies

```bash
cd berb/ui/web
npm install
```

## Running the UI

### Option 1: Start Backend and Frontend Separately

**Terminal 1 - Backend:**
```bash
cd berb/api
python -m berb.api.server
```

**Terminal 2 - Frontend:**
```bash
cd berb/ui/web
npm run dev
```

### Option 2: Start Both Together

**Terminal 1 - Backend:**
```bash
cd berb/api && python -m berb.api.server
```

**Terminal 2 - Frontend:**
```bash
cd berb/ui/web && npm run dev
```

## Accessing the UI

Open your browser and navigate to:

```
http://localhost:3000
```

## Using the UI

### 1. Start New Research

1. Click "New Research" or go to `/new`
2. Enter your research topic
3. Select workflow type:
   - Full Research (default)
   - Literature Only
   - Paper from Results
   - Experiments Only
   - Review
   - Rebuttal
   - Literature Review
   - Math Paper
   - Computational Paper
4. Choose preset (e.g., ml-conference, biomedical)
5. Select mode:
   - Autonomous (zero human intervention)
   - Collaborative (human-in-the-loop)
6. Review and launch

### 2. Monitor Pipeline

- View real-time progress
- Track cost and time
- See stage outputs
- Approve stages (collaborative mode)

### 3. Browse Literature

- Search papers
- Filter by year, citations
- View citation profiles
- Check Berb confidence scores

### 4. Edit Paper

- Edit LaTeX source
- Preview rendered output
- Check claim confidence
- Export paper

### 5. View Results

- Quality metrics
- Cost breakdown
- Evidence consensus
- Experiment results

### 6. Configure Settings

- API keys
- Theme (light/dark)
- Language
- Default preset
- Notifications

## CLI Commands

```bash
# Full research
berb run --topic "Neural architecture search" --preset ml-conference

# Literature-only
berb literature --topic "transformer efficiency" --preset ml-conference

# Paper from results
berb write --topic "..." --data results/ --figures figures/

# Experiments only
berb experiment --hypothesis "X improves Y" --context background.md

# Review manuscript
berb review --manuscript paper.pdf --venue neurips

# Generate rebuttal
berb rebuttal --manuscript paper.pdf --reviews comments.txt

# Literature review
berb survey --topic "..." --preset ml-conference
```

## Development

### Frontend Development

```bash
cd berb/ui/web
npm run dev        # Start dev server
npm run build      # Build for production
npm run lint       # Run linter
npm run type-check # Type check
```

### Backend Development

```bash
cd berb/api
python -m berb.api.server  # Start server
```

## Troubleshooting

### Port Already in Use

```bash
# Change Vite port
npm run dev -- --port 3001

# Change FastAPI port
uvicorn berb.api.server:app --host 127.0.0.1 --port 8001
```

### CORS Errors

Ensure backend allows origins in `berb/api/server.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    ...
)
```

### Dependencies Not Found

```bash
# Reinstall frontend
cd berb/ui/web
rm -rf node_modules
npm install

# Reinstall Python
cd E:\Documents\Vibe-Coding\Berb
pip install -e ".[all]"
```

## Next Steps

1. **Configure API Keys** - Add your OpenAI, Anthropic, and Google API keys in Settings
2. **Select Preset** - Choose a preset for your research domain
3. **Start Research** - Enter your topic and launch
4. **Monitor Progress** - Watch the pipeline in real-time
5. **Review Results** - Check quality metrics and evidence

## Support

- Documentation: `berb/ui/UI_IMPLEMENTATION_GUIDE.md`
- Implementation Summary: `berb/ui/IMPLEMENTATION_SUMMARY.md`
- Web UI README: `berb/ui/web/README.md`

## License

MIT License - See LICENSE file.
