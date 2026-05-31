# Frank v0.1.0-b1 — First Beta Release

**Release Date:** 2026-05-31
**Version:** v0.1.0-b1
**Type:** Beta (Internal Test)
**Author:** Rowen

---

## TL;DR

Frank's first beta release is here. This is a desktop AI assistant platform built on an Electron + Python hybrid architecture, integrating speech recognition, camera pipelines, identity fusion, and LLM-powered conversation. This release establishes the full infrastructure skeleton and delivers a major glassmorphism-style main panel UI redesign.

---

## ✨ Highlights

- **Full-Window Main Panel UI Redesign** — Expanded from 360×500 to 800×600, featuring oklch color space and glassmorphism visuals, a three-zone layout (Status / Monitor / Navigation), and a Frank Orb animated interaction sphere.
- **Slide-Over Panel System (PanelManager)** — Five non-destructive info panels (Settings, Members, Tasks, Identity, Notifications) overlaid above the main view.
- **Multimodal Perception Pipelines** — Audio (STT/TTS), Camera (Pose/Gesture), and Identity Fusion pipelines operational, with multi-person mode and wake-free command support.
- **Role Permissions + Skill Plugin System** — Backend role query APIs with permission matrices and skill allowlists; three built-in skills: reminder, schedule, weather.
- **Security & Stability Fixes** — Patched command injection, async scheduling hazards, and memory leaks from code review findings.

---

## 📋 Changelog

### 🚀 Features

- **Main Panel Full-Window Redesign** (`feat`): Comprehensive Electron frontend v1→v3 overhaul adopting a three-zone full-window layout (Status Bar / Monitor Area / Navigation Bar). Introduced PanelManager slide-over panel system supporting Settings, Members, Tasks, Identity, and Notification panels. Window resized from 360×500 to 800×600.
  - Affected files: [src/electron/renderer/app.js](src/electron/renderer/app.js), [src/electron/renderer/index.html](src/electron/renderer/index.html), [src/electron/renderer/styles.css](src/electron/renderer/styles.css), [design/main-panel.html](design/main-panel.html), [design/css/app.css](design/css/app.css)

- **Frank Orb Interaction Animation** (`feat`): Breathing / thinking / particle-effect animations paired with the glassmorphism visual style.
  - Affected files: [src/electron/renderer/app.js](src/electron/renderer/app.js), [src/electron/renderer/styles.css](src/electron/renderer/styles.css)

- **Chat Overlay & Inline Preview** (`feat`): Non-blocking conversational overlay with inline conversation preview.
  - Affected files: [src/electron/renderer/app.js](src/electron/renderer/app.js)

- **Window Control IPC** (`feat`): Minimize / close / exit confirmation / hide-to-tray functionality — full window lifecycle management.
  - Affected files: [src/electron/main/ipc.js](src/electron/main/ipc.js), [src/electron/main/main.js](src/electron/main/main.js), [src/electron/main/preload.js](src/electron/main/preload.js)

- **Media Device Enumeration API** (`feat`): Preload layer now exposes media device enumeration and role/settings event listeners.
  - Affected files: [src/electron/main/preload.js](src/electron/main/preload.js)

- **Four-Step Registration Wizard** (`feat`): Identity → Face → Voiceprint → Confirmation registration flow.
  - Affected files: [src/electron/renderer/app.js](src/electron/renderer/app.js)

- **Role Query APIs** (`feat`): Backend `role.list` / `role.info` endpoints with permission matrices and skill allowlists.
  - Affected files: [src/python/modules/role/role_manager.py](src/python/modules/role/role_manager.py)

- **Settings Read/Write APIs** (`feat`): Backend `settings.get` / `settings.update` endpoints with API key redaction.
  - Affected files: [src/python/shared/config.py](src/python/shared/config.py)

- **Deep Config Merge & YAML Write-Back** (`feat`): `config.py` now supports deep merge of configuration dicts and YAML file write-back.
  - Affected files: [src/python/shared/config.py](src/python/shared/config.py)

- **Design Token System** (`feat`): Complete design token suite — oklch color space, spacing scale, animation easing curves.
  - Affected files: [design/css/app.css](design/css/app.css), [src/electron/renderer/styles.css](src/electron/renderer/styles.css)

- **Core Infrastructure** (`build`): Project scaffold — Electron frontend + Python backend process architecture. Core Python modules implemented: Audio Pipeline, Camera Pipeline, Speech-to-Text (STT), Text-to-Speech (TTS), Pose Detection, Gesture Recognition, Identity Fusion, LLM Integration, Multi-Person Mode, Wake-Free Commands, Visual Intent, State Machine, Task Management, Role Permissions, Skill Loader.
  - Affected files: all modules under [src/python/](src/python/)

- **Skill Plugin System** (`build`): Three built-in skills — reminder, schedule, weather.
  - Affected files: [skills/reminder/](skills/reminder/), [skills/schedule/](skills/schedule/), [skills/weather/](skills/weather/), [src/python/modules/skill_loader/skill_loader.py](src/python/modules/skill_loader/skill_loader.py)

### 🐛 Bug Fixes

- **Command Injection Fix** (`fix`): Replaced Electron main process `execSync` with parameterized `spawnSync` calls to eliminate shell injection risk.
  - Affected files: [src/electron/main/main.js](src/electron/main/main.js)

- **Async Scheduling Safety Fix** (`fix`): Audio pipeline now uses a stored main-loop reference instead of dynamic asyncio event loop retrieval, preventing scheduling hazards.
  - Affected files: [src/python/modules/audio/audio_pipeline.py](src/python/modules/audio/audio_pipeline.py)

- **MediaPipe Import Crash Fix** (`fix`): Camera pipeline MediaPipe module import now uses lazy loading with null-pointer guards to prevent startup crashes.
  - Affected files: [src/python/modules/camera/camera_pipeline.py](src/python/modules/camera/camera_pipeline.py)

- **Identity Fusion Gate Logic Fix** (`fix`): Fixed evidence accumulation gating — added evaluation deduplication and active-time update rate limiting.
  - Affected files: [src/python/modules/fusion/identity_fusion.py](src/python/modules/fusion/identity_fusion.py)

- **face_lost Jitter Fix** (`fix`): Camera pipeline face-loss debouncing with consecutive-frame smoothing and error-log rate limiting.
  - Affected files: [src/python/modules/camera/camera_pipeline.py](src/python/modules/camera/camera_pipeline.py)

- **Tray Timer Memory Leak Fix** (`fix`): Electron tray timer is now properly cleaned up to prevent memory leaks.
  - Affected files: [src/electron/main/main.js](src/electron/main/main.js)

### 🔧 Improvements

- **Permission Check Spec Update** (`fix`): Added skill `min_user_level` permission check specification and automatic unidentified-visitor discovery spec.
  - Affected files: [.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md)

- **State Machine Spec Update** (`fix`): Wake-word now supports direct transition from Idle/Aware states into Chat mode.
  - Affected files: [.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md), [openspec/specs/state-machine/spec.md](openspec/specs/state-machine/spec.md)

- **Project Configuration** (`build`): Added `frank.yaml` project config, `.gitignore`, and dev scripts (`dev.bat` / `setup.bat`).
  - Affected files: [config/frank.yaml](config/frank.yaml), [scripts/dev.bat](scripts/dev.bat), [scripts/setup.bat](scripts/setup.bat)

- **Dev Toolchain Integration** (`build`): Integrated CodeGraph code intelligence and Understand-Anything knowledge graph analysis tools.
  - Affected files: [.codegraph/](.codegraph/), [.understand-anything/](.understand-anything/)

### 📝 Documentation

- **System Architecture Docs** (`docs`): New project documentation suite — System Architecture, Identity Recognition, Interaction Model, Task Plugin System, Member Biometrics, Technology Stack.
  - Affected files: 6 spec documents under [docs/specs/](docs/specs/)

- **OpenSpec Change Proposals** (`feat`): Four planning documents: `fix-app-exit-and-close`, `fix-ui-pages-no-implementation`, `integrate-legacy-panels-v2`, `redesign-main-panel-ui`.
  - Affected files: [openspec/changes/](openspec/changes/)

- **Code Review Reports** (`fix`): Archived REVIEW.md / REVIEW-FIX.md covering security findings WR-03 through WR-10.
  - Affected files: [.planning/reviews/REVIEW.md](.planning/reviews/REVIEW.md), [.planning/reviews/REVIEW-FIX.md](.planning/reviews/REVIEW-FIX.md)

- **OpenSpec Spec Index** (`build`): Consolidated 23 OpenSpec specification documents under `openspec/specs/` covering all core modules.
  - Affected files: [openspec/specs/](openspec/specs/)

---

## 📦 Upgrade Guide

This is the initial beta release — no upgrade steps required.

**Environment Setup:**
1. Install Node.js 18+ and Python 3.10+
2. Run `scripts/setup.bat` to install dependencies
3. Run `scripts/dev.bat` to start in development mode

---

## ⚠️ Known Issues

- **UI Pages Not Yet Implemented** — Some panel pages (settings detail, member detail) currently show placeholder content awaiting implementation.
- **No Automated Tests for UI Rework** — The major UI refactor involves extensive frontend changes; manual validation of panel open/close, role queries, and settings persistence is recommended.
- **Core Pipeline Regression Testing Needed** — After security fixes, regression testing of the Audio, Camera, and Identity Fusion pipelines is recommended.

---

## 👥 Contributors

- Rowen
- Rowen Ray

---

<details>
<summary>📜 Full Commit List</summary>

- `4143875` — feat: redesign main panel UI: full-window layout + panel system + backend role & settings API integration
- `cf76047` — fix: resolve security vulnerabilities and async scheduling issues found in code review
- `a129330` — build: initialize Frank project infrastructure and core modules
- `5d4341c` — build: project initialization
- `fca9738` — Initial commit

</details>
