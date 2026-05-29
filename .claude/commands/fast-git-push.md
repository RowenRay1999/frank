---
name: "Fast Git Push"
description: Stage all, conventional commit, and push to origin
category: Workflow
tags: [git, commit, push, workflow]
---

Quickly stage all changes, generate a conventional commit message with full fields in Chinese, and push to origin.

**Usage:** `/fast-git-push <type>: <summary>` or `/fast-git-push <summary>` or `/fast-git-push` (auto-generate all fields)

**Examples:**
- `/fast-git-push feat: add user login`
- `/fast-git-push fix: resolve null pointer in parser`
- `/fast-git-push refactor: simplify auth middleware`
- `/fast-git-push update dependencies` (auto-detect type + generate remaining fields)
- `/fast-git-push` (auto-generate all fields from diff)

**Steps**

1. Run `git status --short` to see what changed. If nothing to commit, stop.

2. **Determine the type, summary, and all commit fields:**

   **If the user provided a type prefix (e.g. `feat: xxx`):**
   - Use the provided type and summary directly.
   - Auto-generate the remaining fields (内容, 影响, 测试, 备注, 作者) from `git diff`.

   **If only a summary was given (no type prefix):**
   - Auto-detect type from `git diff --stat`:
     - `feat` — new features, new files, new functions
     - `fix` — bug fixes, error handling, null checks
     - `refactor` — restructuring, renaming, cleanup without feature change
     - `docs` — documentation/markdown only
     - `test` — test files only
     - `build` — config, dependencies, build scripts
     - `pref` — performance improvements
     - `revert` — reverting previous changes
     - `chore` — maintenance, formatting, miscellaneous
   - Auto-generate the remaining fields from `git diff`.
   - Ask the user to confirm if ambiguous.

   **If no input is provided (fully auto-generate):**
   - Run `git diff --stat` and `git diff` to analyze all changes.
   - Auto-detect type using the same rules above.
   - Auto-generate a concise 概要 (summary) in Chinese summarizing the main change (under 72 chars).
   - Auto-generate 内容 (description) in Chinese as a bullet list of specific changes with file paths.
   - Auto-generate 影响 (affected areas) in Chinese from file paths and diff context.
   - Auto-generate 测试 (test cases) in Chinese: list test files if present, otherwise "无".
   - Auto-generate 备注 (notes) in Chinese: breaking changes, dependencies, or "无".
   - Auto-generate 作者 (author) from `git config user.name`.
   - All generated text content (summary, description, affected areas, test cases, notes) must be in Chinese.
   - Present the complete generated message for user confirmation; allow edits.

3. **Construct message:**
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
   - Keep the summary line under 72 chars, lowercase, no trailing period.

4. **Commit:**
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

5. **Push:**
   ```bash
   git push origin $(git branch --show-current)
   ```
   Use `-u` if the branch has no upstream tracking.

**Guardrails:**
- Always show the complete generated commit message before staging.
- When auto-generating, present all fields for user confirmation; allow edits.
- Warn if sensitive files (`.env`, secrets, large binaries) are detected.
- If auto-generated message seems vague, ask the user to clarify.
- Never force push.
- If push fails, report the error and stop.
