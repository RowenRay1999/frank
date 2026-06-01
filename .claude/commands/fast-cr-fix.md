---
name: "Fast CR Fix"
description: Review uncommitted changes, generate report, and auto-fix with awareness of project requirements
category: Quality
tags: [review, fix, code-quality, security, requirements, openspec]
---

Review all uncommitted local code changes, scan for bugs/security/quality/performance/logic issues, generate a review report, then auto-fix findings guided by OpenSpec specs and superpowers planning documents.

**Usage:** `/fast-cr-fix` or `/fast-cr-fix <focus>` (e.g., `/fast-cr-fix security`, `/fast-cr-fix frontend`)

**Examples:**
- `/fast-cr-fix` — full review + fix of all uncommitted changes
- `/fast-cr-fix security` — focus on security findings only
- `/fast-cr-fix requirements` — focus on requirements alignment only
- `/fast-cr-fix review-only` — generate review report without auto-fixing

**Pipeline**

```
┌──────────────────────────────────────────────────┐
│  PHASE 1: Comprehensive Review                   │
│                                                  │
│  1.1  Gather git diff (changed files + content)  │
│  1.2  Load OpenSpec specs + superpowers docs     │
│  1.3  Multi-dimension scan (9 dimensions)        │
│  1.4  Generate REVIEW.md structured report        │
│                                                  │
│              ▼  User confirms  ▼                  │
│                                                  │
│  PHASE 2: Intelligent Auto-Fix                   │
│                                                  │
│  2.1  Prioritize fixes (CRITICAL → LOW)          │
│  2.2  Apply each fix, cross-check requirements   │
│  2.3  Post-fix sanity verification               │
│  2.4  Summary output                             │
│                                                  │
│  ✓ Done — user commits via /fast-git-push        │
└──────────────────────────────────────────────────┘
```

**Review Dimensions (9 total):**
1. Logic & Correctness
2. Security
3. Error Handling
4. Data Flow & State
5. Performance
6. Code Quality
7. Requirements Alignment (vs OpenSpec + superpowers)
8. Consistency
9. Typo & Resource

**Requirements Awareness:**
- Reads `openspec/specs/*/spec.md` for API contracts, data models, expected behaviors
- Reads `docs/superpowers/specs/` and `docs/superpowers/plans/` for business requirements
- Cross-references every fix against these documents before applying

**Guardrails:**
- Never fix without showing the review report first
- Never contradict OpenSpec specs — flag conflicts and ask
- Minimal fixes only — don't refactor adjacent code
- Never auto-commit; user commits when ready
