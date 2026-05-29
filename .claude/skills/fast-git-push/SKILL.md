---
name: fast-git-push
description: Stage all changes, generate a conventional commit message, and push to origin. Use when the user wants to quickly commit and push their current work.
license: MIT
metadata:
  author: frank
  version: "1.0"
---

Quickly stage, commit, and push all changes with a conventional commit message.

**Input**: The user may optionally provide a commit summary, optionally prefixed with a type. If no input is given at all, auto-analyze the diff and generate all commit message fields automatically. If only a summary is given without a type prefix, auto-detect the type based on the diff content.

**Language**: All generated commit message content MUST be in Chinese (Simplified Chinese / 简体中文). The type prefix (feat, fix, refactor, etc.) remains in English as per conventional commit standards.

**Commit Convention**

Format: 

```
概要：<type> <summary>
内容：<description>
影响：<affected-areas>
测试：<test-cases>
备注：<notes>
作者：<author>

```

Valid types:
| Type | Use when |
|------|----------|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `refactor` | Code restructuring without feature change |
| `docs` | Documentation only changes |
| `test` | Adding or updating tests |
| `build` | Build system, dependencies, tooling |
| `pref` | Performance improvement |
| `revert` | Reverting a previous commit |
| `chore` | Maintenance, cleanup, miscellaneous |

**Steps**

1. **Check working tree status**
   ```bash
   git status --short
   ```
   If nothing to commit, inform the user and stop.

2. **Determine the commit type and generate message fields**
   
   **If the user provided input:**
   - If the user explicitly said "feat: xxx" or "fix: xxx", use that type and summary.
   - If the user just gave a summary without a type prefix, inspect the diff to auto-detect:
     - New files/functions/features → `feat`
     - Bug fixes, error handling → `fix`
     - Renames, restructuring, cleanup → `refactor`
     - Markdown/docs only → `docs`
     - Test files only → `test`
     - Config/build files → `build`
     - Performance-related → `pref`
     - Otherwise → `chore`
   - Confirm the chosen type with the user if ambiguous.
   - Auto-generate the remaining fields (内容, 影响, 测试, 备注, 作者) from the diff.
   
   **If no input is provided (auto-generate all fields):**
   - Run `git diff --stat` and `git diff` to understand the full change set.
   - Auto-detect the type based on the same rules above.
   - Auto-generate a concise **概要** (summary) from the changed files and diff content:
     - Summarize the main change in one line (under 72 chars, lowercase, no period).
     - Focus on WHAT changed and WHY, not just listing files.
     - **Must be in Chinese.**
   - Auto-generate **内容** (description) — a bullet list of specific changes:
     - List each logical change with its file paths.
     - Be specific: what was added/modified/deleted.
     - **Must be in Chinese.**
   - Auto-generate **影响** (affected areas) — which modules/components are touched:
     - Deduce from file paths and diff context.
     - **Must be in Chinese.**
   - Auto-generate **测试** (test cases) — if applicable:
     - If test files are part of the diff, list them.
     - Otherwise note "无" or suggest testing approach.
     - **Must be in Chinese.**
   - Auto-generate **备注** (notes) — anything noteworthy:
     - Breaking changes, dependencies, follow-up items.
     - If nothing special, note "无".
     - **Must be in Chinese.**
   - Auto-generate **作者** (author) — from `git config user.name`.
   - Present the complete generated commit message to the user for confirmation before proceeding.

3. **Construct the commit message**
   ```
   概要：<type>: <summary>
   内容：
   - <change 1>
   - <change 2>
   影响：<affected-areas>
   测试：<test-cases>
   备注：<notes>
   作者：<author>
   ```
   - Keep the summary line under 72 characters.
   - Use lowercase.
   - No period at the end.

4. **Stage and commit**
   ```bash
   git add .
   git commit -m "概要：<type>: <summary>
   内容：
   - <change 1>
   - <change 2>
   影响：<affected-areas>
   测试：<test-cases>
   备注：<notes>
   作者：<author>"
   ```

5. **Push**
   ```bash
   git push origin <current-branch>
   ```
   - Detect the current branch with `git branch --show-current`.
   - If the branch has no upstream, use `git push -u origin <branch>`.

**Output**

```
## Fast Git Push

**Branch:** <branch>
**Commit:**
```
概要：<type>: <summary>
内容：
- <change 1>
- <change 2>
影响：<affected-areas>
测试：<test-cases>
备注：<notes>
作者：<author>
```
**Files changed:** N

Pushing to origin/<branch>...
✓ Done
```

**Guardrails**
- Always show the user the complete generated commit message before staging.
- When auto-generating, present all fields for user confirmation; allow the user to edit any field before committing.
- If there are sensitive-looking files (`.env`, secrets, large binaries), warn before adding.
- If the auto-generated message seems too vague or inaccurate, ask the user to clarify.
- If push fails (e.g. no network, rejected), report the error and stop — do not force push.
