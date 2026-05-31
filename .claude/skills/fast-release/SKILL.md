---
name: fast-release
description: |
  Generate bilingual (Chinese + English) version release documents following standard
  GitHub release note format. Auto-assigns semantic version numbers with type suffixes
  (e.g. v0.1.1-b1 for internal test, v1.0.0 for stable). Saves to docs/version/.
  Triggers: "/fast-release", "fast release", "generate release notes", "发版",
  "版本发布文档", "写发布说明", "release version".
---

# Fast Release — 版本发布文档生成器

Generate bilingual version release documents following standard GitHub release format.

**Language**: All document content MUST be generated in BOTH Simplified Chinese (简体中文) and English. The Chinese version is the primary document; the English version is a faithful translation.

---

## Version Numbering Rules

### Scheme

```
v<MAJOR>.<MINOR>.<PATCH>[-<type><sub>]
```

| Segment | Meaning | Trigger |
|---------|---------|---------|
| MAJOR | Breaking changes, architecture rewrite | `--major` or `--version` |
| MINOR | New features, non-breaking | `--minor` or `--version` |
| PATCH | Bug fixes, patches | `--patch` or `--version` (default) |
| type | Release phase: `a` (alpha), `b` (beta/内测), `rc` (release candidate) | `--type <type>` |
| sub | Incrementing serial within the type | auto-incremented |

### Auto-Increment Logic

When not given an explicit `--version`, derive the new version from:

1. **Read the latest tag or existing version from `docs/version/` directories** — find the highest version.
2. **Read git commits since the last tag** to determine the nature of changes:
   - At least one `feat:` commit → bump MINOR, reset PATCH to 0
   - Only `fix:` / `chore:` commits → bump PATCH
   - Any commit with `BREAKING CHANGE` or a `!` after type → bump MAJOR, reset MINOR and PATCH to 0
3. **If `--major` / `--minor` / `--patch` is specified**, force that segment increment.
4. **If `--type <type>` is specified**, append the type suffix and auto-increment the sub-number from the latest matching `v<MAJOR>.<MINOR>.<PATCH>-<type><N>` tag.
5. **Stable releases** (no `--type`, or `--type stable`) have NO suffix.

### Examples

```
Starting from no tags:
  /fast-release                    → v0.1.0 (initial minor)
  /fast-release --type beta        → v0.1.0-b1
  /fast-release --type beta        → v0.1.0-b2
  /fast-release --major            → v1.0.0
  /fast-release --patch            → v1.0.1
  /fast-release --version v0.2.0-a1 → v0.2.0-a1 (explicit)
```

---

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--version <vX.Y.Z[-typeN]>` | Exact version override — skip all auto-increment |
| `--major` | Force major version bump |
| `--minor` | Force minor version bump |
| `--patch` | Force patch version bump (default when no feats present) |
| `--type <alpha\|beta\|rc\|stable>` | Release type. `beta` = 内测, `stable` = 正式版 (no suffix) |
| `--title "<title>"` | Custom release title |
| `--date <YYYY-MM-DD>` | Release date (default: today) |
| `--from <ref>` | Starting git ref for change log accumulation (default: last tag or first commit) |
| `--to <ref>` | Ending git ref (default: HEAD) |

---

## Output Structure

```
docs/version/<version>-<YYYY-MM-DD>/
├── RELEASE.zh-CN.md     # Chinese release notes
├── RELEASE.en.md        # English release notes
└── assets/              # (optional) screenshots, diagrams
```

---

## Document Template

Each release document follows the GitHub Releases standard format:

### 1. Header

```markdown
# <Project Name> <Version> — <Release Title>

**Release Date:** <YYYY-MM-DD>
**Version:** <version>
**Type:** <Alpha / Beta (Internal Test) / Release Candidate / Stable>
**Author:** <git config user.name>
```

### 2. TL;DR (optional, for larger releases)

```markdown
## TL;DR

A 2-3 sentence summary of this release's main theme — what it unlocks or resolves at a high level.
```

### 3. Highlights / What's New

```markdown
## ✨ Highlights

- **Major Feature A** — Brief description of the most impactful change.
- **Major Feature B** — Brief description.
...
```

### 4. Changelog (by category)

```markdown
## 📋 Changelog

### 🚀 Features

- **Feature name** (`scope`): Description of what was added, with affected file paths.
- ...

### 🐛 Bug Fixes

- **Fix description** (`scope`): What was wrong and how it was fixed.
- ...

### 🔧 Improvements

- **Improvement description** (`scope`): Refactors, performance, or DX improvements.
- ...

### 📝 Documentation

- **Doc change** (`scope`): What documentation was added or updated.
- ...

### ⚠️ Breaking Changes

- **Change description** — what breaks and migration path.
- ...
(Only include if applicable)
```

### 5. Upgrade Guide (if applicable)

```markdown
## 📦 Upgrade Guide

Steps for upgrading from the previous version:
1. ...
2. ...
```

### 6. Known Issues

```markdown
## ⚠️ Known Issues

- **Issue description** — workaround if available.
- ...
```

### 7. Contributors

```markdown
## 👥 Contributors

- <list of authors from git log between versions>
```

### 8. Full Commit List (collapsed)

```markdown
<details>
<summary>📜 Full Commit List</summary>

- `hash` — commit summary
- ...

</details>
```

---

## Workflow

### Step 1 — Gather Context

```bash
# Find the latest version tag
git tag --sort=-v:refname | head -5

# Find existing version directories
ls docs/version/ 2>/dev/null || echo "none"

# Get git log since the last tag (or from the first commit)
git log <last_tag>..HEAD --oneline --format="%h %s"
```

### Step 2 — Determine the Version

Apply the [Version Numbering Rules](#version-numbering-rules):

1. Parse user parameters (`--version`, `--major`, `--minor`, `--patch`, `--type`).
2. If `--version` is given, use it exactly.
3. Otherwise, analyze commits since the last tag and apply increment rules.
4. Confirm the computed version with the user before proceeding.

### Step 3 — Analyze Changes

```bash
# Full diff summary
git diff --stat <last_tag>..HEAD

# Commit messages grouped by conventional commit type
git log <last_tag>..HEAD --format="%s" | sort | uniq -c

# List of changed files by module
git diff --name-only <last_tag>..HEAD
```

Classify each change into categories:
- 🚀 Features (feat:)
- 🐛 Bug Fixes (fix:)
- 🔧 Improvements (refactor:, perf:, build:, chore:)
- 📝 Documentation (docs:)
- ⚠️ Breaking Changes (BREAKING CHANGE, `!`)

### Step 4 — Generate the Documents

Write TWO files in `docs/version/<version>-<YYYY-MM-DD>/`:

1. `RELEASE.zh-CN.md` — Chinese release notes (primary)
2. `RELEASE.en.md` — English release notes (translation)

**For each:** Follow the [Document Template](#document-template). The Chinese version is authoritative for content; the English version must faithfully translate all sections, adapting idioms naturally.

### Step 5 — Confirm and Commit

1. Present a summary of the generated documents to the user.
2. Show the version, file paths, and key highlights.
3. Ask: "是否确认生成并提交此版本发布文档？(Generate and commit these release docs?)"
4. On confirmation, optionally commit the files:
   ```bash
   git add docs/version/<version>-<YYYY-MM-DD>/
   git commit -m "概要：docs: release <version> — <title>

   内容：
   - 新增 <version> 版本发布文档（中英文）
   - 中文版: docs/version/<version>-<YYYY-MM-DD>/RELEASE.zh-CN.md
   - 英文版: docs/version/<version>-<YYYY-MM-DD>/RELEASE.en.md
   影响：文档
   测试：无
   备注：自动生成 by fast-release
   作者：<author>"
   ```
   (Do NOT auto-push — let the user decide.)

---

## Quick Reference

| User says | Action |
|-----------|--------|
| `/fast-release` | Auto-detect, bump PATCH or MINOR, generate bilingual release |
| `/fast-release --type beta` | First/next beta release, e.g. v0.1.0-b1 |
| `/fast-release --major` | Major version bump, e.g. v1.0.0 |
| `/fast-release --version v1.0.0-rc1` | Exact version, no auto-increment |
| `/fast-release --type stable` | Stable release (no suffix) |
| `发版` or `版本发布` | Same as `/fast-release` |

---

## Guardrails

1. **Always confirm the computed version** with the user before generating documents — especially when auto-incrementing.
2. **Never overwrite existing release documents** — if `docs/version/<version>-<date>/` already exists, warn and ask whether to overwrite or choose a different date.
3. **Classify commits accurately** — a `feat:` commit IS a feature; don't mislabel it as a fix. When in doubt, read the commit body.
4. **Include file paths** in changelog entries so readers can click through.
5. **Breaking changes MUST be highlighted** prominently with migration instructions.
6. **If there are no new commits** since the last tag, inform the user and stop — nothing to release.
7. **Both language versions must be complete** — no "see Chinese version" shortcuts in the English document.
8. **Conventional commit type prefixes** in the changelog are auto-detected from commit messages using the same rules as `fast-git-push`.
