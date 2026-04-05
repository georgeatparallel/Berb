# Test Research Submission

Αυτό το script ελέγχει αν το UI μπορεί να submitάρει research jobs.

## Βήματα:

1. **Άνοιξε το browser** στο http://localhost:3000
2. **Πήγαινε στο wizard** (αν δεν είσαι ήδη)
3. **Συμπλήρωσε**:
   - Topic: "Augustine's Theory of Divine Foreknowledge"
   - Workflow: Full Research
   - Preset: humanities
   - Mode: Autonomous
4. **Πάτησε "Launch Research"**

## Τι πρέπει να δεις:

### ✅ Επιτυχία:
- Loading spinner με "Starting Research..."
- Μετά: "Research Launched!" με Job ID
- Progress bar (αν το backend τρέχει το pipeline)
- Status: running/queued/completed

### ❌ Σφάλμα:
- "Error Starting Research" με message
- Πιθανά messages:
  - "Failed to fetch" → Backend δεν τρέχει
  - "Not Found" → Wrong API endpoint
  - "Config error" → Missing config file

## Debug:

Αν δεις σφάλμα, άνοιξε το **Browser Console** (F12) και δες τα logs.

### Backend Logs:
```bash
# Αν τρέχεις με berb serve
# Θα δεις logs στο terminal

# Check health
curl http://localhost:8000/api/health
```

### Frontend Logs:
```javascript
// Στο browser console (F12)
// Θα δεις:
// - "Research job created: rc-..."
// - Ή error messages
```

## Εναλλακτική: CLI Test

Αν το UI δεν λειτουργεί, δοκίμασε από CLI:

```bash
cd E:\Documents\Vibe-Coding\Berb

# Δημιουργία config
berb init

# Τρέξε research
berb run --topic "Test research" --preset humanities --auto-approve
```
