---
name: fast-cr-fix
description: |
  Review uncommitted local code changes, scan for bugs/security/quality/performance/logic issues,
  generate a review report, then auto-fix findings with awareness of OpenSpec specs and
  superpowers planning documents to ensure alignment with project requirements and design.
  Triggers: "/fast-cr-fix", "fast cr fix", "fast code review fix", "快速评审修复",
  "review and fix uncommitted changes", "scan and fix my changes".
license: MIT
metadata:
  author: frank
  version: "1.0"
---

# Fast CR Fix — 快速代码评审与自动修复

A two-phase pipeline: **comprehensive review** → **intelligent auto-fix**. Reviews all uncommitted local changes across the full stack (Python backend, Electron/Node.js frontend, configuration, documentation), then fixes findings guided by the project's requirements artifacts.

---

## Phase 1: Comprehensive Review

### Step 1.1: Gather Change Context

```bash
git status --short
git diff --stat
git diff
```

If nothing to commit, inform the user and stop.

### Step 1.2: Gather Requirements Context

**Always gather requirements context before reviewing or fixing.** This grounds the review in what the project actually requires, not generic best practices.

1. **Load OpenSpec specs (current, not archive):**
   ```bash
   ls openspec/specs/*/spec.md
   ```
   Read each spec file to understand the current capability requirements, API contracts, data models, and expected behaviors. These define the system's designed behavior.

2. **Load Active OpenSpec changes (if any):**
   ```bash
   ls openspec/changes/*/proposal.md
   ```
   - Read proposals and design docs from active changes (NOT archive/)
   - These contain the work-in-progress requirements that may affect the current changeset

3. **Load superpowers planning docs:**
   Check `docs/superpowers/specs/` and `docs/superpowers/plans/` for the latest design and plan documents relevant to the changed files. These contain business requirements and architectural decisions.

4. **Synthesize a requirements summary** (~10-15 bullet points) covering:
   - Relevant API contracts and data models
   - Expected component behaviors
   - Design constraints and architectural decisions
   - Business rules and role/permission logic
   Use this summary to cross-reference findings.

### Step 1.3: Multi-Dimension Review

Review the diff across all dimensions. For each finding, record:
- **File**: path, line range
- **Severity**: `CRITICAL` (blocks functionality/security) | `HIGH` (likely bug) | `MEDIUM` (anti-pattern, fragility) | `LOW` (style, nit, cleanup)
- **Category**: `bug` | `security` | `performance` | `logic` | `quality` | `consistency` | `requirements-gap` | `accessibility` | `error-handling`
- **Description**: what's wrong and why
- **Fix suggestion**: concrete approach

#### Review Dimensions

| # | Dimension | What to check |
|---|-----------|---------------|
| 1 | **Logic & Correctness** | Wrong conditions, inverted booleans, off-by-one, null/undefined access, race conditions, missing awaits, incorrect IPC channel names |
| 2 | **Security** | XSS (innerHTML, document.write), injection in SQL/command/JSON, exposed secrets, missing input validation, broken auth/role checks, insecure IPC |
| 3 | **Error Handling** | Missing try-catch, unhandled promise rejections, swallowed errors, missing error propagation callbacks, inadequate logging |
| 4 | **Data Flow & State** | Broken IPC contracts (mismatched channel names), stale state reads, missing state updates, inconsistent event payloads, serialization issues (e.g. BLOB columns in JSON) |
| 5 | **Performance** | N+1 queries, unnecessary re-renders, missing memoization, sync blocking in main thread, large diffs suggesting architecture problems |
| 6 | **Code Quality** | Duplicated code, overly complex functions, inconsistent patterns vs codebase conventions, dead code, magic numbers, vague naming |
| 7 | **Requirements Alignment** | Code contradicts OpenSpec specs, misses required behaviors, breaks existing capabilities, introduces unplanned side effects, violates documented design decisions |
| 8 | **Consistency** | Mismatched function signatures across files, inconsistent error message formats, style drift from surrounding code, breaking naming conventions |
| 9 | **Typo & Resource** | Misspelled variable/function names, missing imports, broken imports, CSS class name mismatches, incorrect element ID references |

### Step 1.4: Generate Review Report

Write findings to a temporary review file with this structure:

```
## Fast CR Fix — Review Report
**Date:** <date>
**Branch:** <branch>
**Files Changed:** N
**OpenSpec Specs Reviewed:** <list>
**Superpowers Docs Reviewed:** <list>

### Summary
| Severity | Count |
|----------|-------|
| CRITICAL | N |
| HIGH     | N |
| MEDIUM   | N |
| LOW      | N |

### Findings

#### F-001: <title>
- **Severity:** CRITICAL
- **Category:** bug
- **File:** path/file.ext:123-125
- **Description:** <what's wrong and why>
- **Fix:** <concrete fix approach>

... (repeat for each finding)
```

Present the report to the user with a summary. The user may choose to:
1. Proceed with all auto-fixable findings
2. Select specific findings to fix
3. Skip fixing (review only)

---

## Phase 2: Intelligent Auto-Fix

### Step 2.1: Prioritize Fix Order

Fix in dependency order to avoid cascading conflicts:
1. **CRITICAL** (security, data integrity first)
2. **HIGH** (bugs)
3. **MEDIUM** (anti-patterns)
4. **LOW** (style/cleanup only if trivial)

Within the same severity, group by file to minimize file-open operations.

### Step 2.2: Apply Fixes

For each finding being fixed:

1. **Read the target file** (if not already read)
2. **Verify the finding still applies** (code may have been changed by a prior fix)
3. **Apply the fix** minimally — change only what's needed
4. **Cross-check against requirements context:**
   - Does the fix align with OpenSpec specs?
   - Does the fix respect superpowers design decisions?
   - Does the fix maintain backward compatibility with existing APIs?
   - Does the fix follow the project's established patterns?
5. **If a fix would conflict with requirements**: flag it, don't blindly apply. Report the conflict and ask the user.

### Step 2.3: Post-Fix Verification

After all fixes are applied:

1. **Re-check the diff:**
   ```bash
   git diff --stat
   ```

2. **Quick sanity scan**: re-read changed files and verify:
   - No new syntax errors introduced
   - Imports still resolve
   - Function signatures still match callers
   - No leftover debug code or temporary comments

3. **Run existing tests if available:**
   ```bash
   # Python tests
   python -m pytest src/python/ --co 2>/dev/null || echo "No test runner available"
   # Node tests
   npm test --if-present 2>/dev/null || echo "No test runner available"
   ```

### Step 2.4: Summary Output

```
## Fast CR Fix — Complete

**Reviewed:** N files, M findings
**Fixed:** X/Y findings resolved
**Skipped:** Z findings (reasons: ...)

### Fixes Applied
- [F-001] <title> — <file>
- [F-003] <title> — <file>
...

### Skipped (Unfixable / Needs Decision)
- [F-002] <title> — requires architectural decision
...

### Files Modified After Fix
<git diff --stat output>
```

---

## Requirements-Aware Fixing Rules

When fixing, ALWAYS cross-reference these project-specific rules derived from OpenSpec specs:

### From identity-fusion spec
- Identity events (`onIdentityConfirmed`, `onIdentityUnknown`) must include complete payloads with `person_id`, `display_name`, `role`, `face_thumbnail`, `voiceprint_spectrum`
- Database queries via `_row_to_json_dict` must filter BLOB columns before JSON serialization
- `auto_discovery` return structure must include `person_id` and `is_new` fields
- UNKNOWN events must broadcast on both state transition AND new discovery

### From role-permission spec
- 5-tier role system: owner → admin → member → child → guest
- Role validation must happen before write operations
- Permission matrix drives all access control checks

### From ui-shell spec
- PanelManager.open must set `isOpen` before loading data (timing: open first, then load)
- Event delegation over inline `onclick` (XSS prevention)
- Single-frame rendering for personList (merge `member.list` + `member.pending` before render)

### General project conventions
- Commit message format: Chinese 概要/内容/影响/测试/备注/作者 structure
- IPC channel names validated against preload.js exposed APIs
- CSS uses oklch color space with design token system
- Python backend uses FastAPI + SQLite with custom JSON serialization

---

## Guardrails

- **CRITICAL findings are always presented first**, with clear explanation of impact
- **Never auto-fix without showing the review report first** — user always sees findings before fixes
- **If a fix contradicts an OpenSpec spec**, flag it and ask the user instead of blindly fixing
- **Don't fix things that aren't broken** — if code diverges from spec but the spec might be outdated, ask
- **Minimal fixes** — change only the problematic lines, don't refactor adjacent code
- **If the diff is very large (>20 files)**, ask the user whether to do a full review or focus on a subset
- **Never commit fixes automatically** — the user reviews and commits via `fast-git-push` when ready
- **Preserve existing code style** — match indentation, quoting style, comment density of surrounding code
- **Language awareness**: Python ↔ JavaScript ↔ HTML/CSS — different idioms per language
