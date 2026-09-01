---
name: repo-tasks
description: Map of tasks/ — working planning docs: todo.md, implementation/hardening plans, and architecture audits. Use when planning work, tracking progress, or reviewing past audits per the CLAUDE.md task-management workflow.
---

# tasks/

Working directory for the task-management workflow mandated by CLAUDE.md: plans are written to `tasks/todo.md` before implementation, progress is checked off, and review sections are appended after completion. Also holds larger one-off plans and dated architecture audits. (CLAUDE.md also references a `tasks/lessons.md` for capturing corrections — create it here if missing.)

## Contents

| File/Dir | Purpose |
|------|---------|
| `todo.md` | Active plan / checklist for current work (the CLAUDE.md-mandated plan-first file) |
| `implementation_plan.md` | General implementation plan for a feature wave |
| `file_upload_plan.md` | Plan for the file-upload capability |
| `pat_scholarpeer_plan.md` | Plan for the ScholarPeer/PAT integration |
| `arch_audit_2026-08-10.md` | Dated architecture audit findings |
| `arch_hardening_plan.md` | Architecture hardening plan derived from audits |
| `hardening_plan_2026-08-13.md` | Dated hardening plan (follow-up wave) |

## Notes

- Workflow: write plan to `todo.md` → verify with user → check items off as completed → append a review section → capture lessons after corrections.
- Dated files (`*_2026-*.md`) are point-in-time snapshots — treat as historical record, do not rewrite.
- These are internal working docs, distinct from `docs/` (published documentation) — plans graduate to `docs/` when finalized.
