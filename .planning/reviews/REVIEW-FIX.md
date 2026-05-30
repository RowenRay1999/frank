---
phase: code-review
fixed_at: 2026-05-30T12:30:00Z
review_path: .planning/reviews/REVIEW.md
iteration: 1
findings_in_scope: 21
fixed: 20
skipped: 1
status: partial
---

# Phase code-review: Code Review Fix Report

**Fixed at:** 2026-05-30T12:30:00Z
**Source review:** .planning/reviews/REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 21 (2 critical + 19 warning)
- Fixed: 20
- Skipped: 1

## Fixed Issues

### CR-01: Coroutine never awaited in `handle_text_input`

**Files modified:** `src/python/server/conversation.py`
**Commit:** 7fda467
**Applied fix:** Added `asyncio.iscoroutinefunction` check and `await` before calling `self._on_assistant_message` in `handle_text_input`, matching the pattern used in `process_speech`.

### CR-02: OpenWakeWord model name invalid

**Files modified:** `src/python/modules/audio/audio_pipeline.py`
**Commit:** 6161ced
**Applied fix:** Changed `Model(wakeword_models=[self.wake_word_text], ...)` to use a separate config field `self.wake_word_config.get('model', 'hey_jarvis')` instead of the trigger phrase text.

### WR-01: Windows registry command vulnerable to shell injection

**Files modified:** `src/electron/main/main.js`
**Commit:** 0b323c0
**Applied fix:** Replaced `execSync` with `spawnSync` and argument arrays for registry `add`/`delete` operations.

### WR-02: `scheduleReconnect` prints warning but ignores it

**Files modified:** `src/electron/main/main.js`
**Commit:** ec475c6
**Applied fix:** Simplified to a single `let safeBackoff` variable that defaults to fallback values when config is invalid.

### WR-03: Tray menu setInterval never cleaned up

**Files modified:** `src/electron/main/main.js`
**Commit:** 67db91c
**Applied fix:** Stored the interval ID in `trayUpdateInterval` and added cleanup in the `before-quit` handler.

### WR-04: `asyncio.run_coroutine_threadsafe` futures never handled

**Files modified:** `src/python/modules/audio/audio_pipeline.py`
**Commit:** bdcad3f
**Applied fix:** Added `future.add_done_callback()` to all `run_coroutine_threadsafe` calls to log exceptions from callback coroutines.

### WR-05: `snr` variable may be undefined in voiceprint extraction logging

**Files modified:** `src/python/modules/audio/audio_pipeline.py`
**Commit:** 1e5ede8
**Applied fix:** Initialized `snr = 0.0` before the try block to prevent `NameError`.

### WR-06: No debounce on face_lost event

**Files modified:** `src/python/modules/camera/camera_pipeline.py`
**Commit:** 8ad9da3
**Applied fix:** Added `_no_face_frames` counter requiring 3 consecutive no-face frames before emitting `face_lost`.

### WR-07: Camera error callback floods on disconnect

**Files modified:** `src/python/modules/camera/camera_pipeline.py`
**Commit:** 5f3a1ed
**Applied fix:** Added `_last_error_time` dict with 5-second debounce per error code.

### WR-08: Evidence queues never drained, evaluate runs on stale data

**Files modified:** `src/python/modules/fusion/identity_fusion.py`
**Commit:** ec9e5f4
**Applied fix:** Changed `has_new` to use timestamp comparison (`_last_face_event_time > _last_evaluated` or `_last_voice_event_time > _last_evaluated`) instead of queue length.

### WR-09: `EVIDENCE_MIN_COUNT` defined but never used

**Files modified:** `src/python/modules/fusion/identity_fusion.py`
**Commit:** 37ce13a
**Applied fix:** Added evidence_count gate in `_evaluate()` -- downgrades CONFIRMED to TENTATIVE when `evidence_count < EVIDENCE_MIN_COUNT`.

### WR-10: Fusion engine process loop calls `update_member` on every cycle

**Files modified:** `src/python/modules/fusion/identity_fusion.py`
**Commit:** c2635d0
**Applied fix:** Added `_last_active_update` throttle -- calls `update_member` at most once per 60 seconds.

### WR-11: Honorific gender inference from name is fragile

**Files modified:** `src/python/modules/llm/llm_provider.py`
**Commit:** f5a1aef
**Applied fix:** Added `honorific_map` for role-based honorifics. Only adult role uses name-based gender inference.

### WR-12: `match_custom_gesture` loads all custom gestures from DB on every call

**Files modified:** `src/python/modules/pose/gesture_classifier.py`
**Commit:** 72b62ab
**Applied fix:** Added `_gesture_cache` and `_cache_dirty` flag to reload from DB only when dirty.

### WR-13: `deserialize_embedding` imported but unused in `match_custom_gesture`

**Files modified:** `src/python/modules/pose/gesture_classifier.py`
**Commit:** 0b25246
**Applied fix:** Removed unused `deserialize_embedding` from import.

### WR-14: Skill watcher task crashes silently on error

**Files modified:** `src/python/modules/skill_loader/skill_loader.py`
**Commit:** d2dd3b8
**Applied fix:** Wrapped watcher loop body in try-except with error logging and recovery sleep.

### WR-15: Timeout monitor race condition on state machine restart

**Files modified:** `src/python/modules/state/state_machine.py`
**Commit:** 9f555bf
**Applied fix:** Always cancel existing timeout task before creating a new one, preventing concurrent monitors.

### WR-16: Blocking `playsound` call in async context

**Files modified:** `src/python/modules/tts/text_to_speech.py`
**Commit:** d09a139
**Applied fix:** Wrapped `winsound.PlaySound` and `subprocess.run` in `loop.run_in_executor`.

### WR-17: `broadcast_event` silently swallows all exceptions

**Files modified:** `src/python/server/main.py`
**Commit:** 3fca8e3
**Applied fix:** Changed `except Exception: pass` to log at DEBUG level.

### WR-19: STT model may not be ready when first speech is processed

**Files modified:** `src/python/server/conversation.py`
**Commit:** 1054e6d
**Applied fix:** Added STT readiness check before transcribing.

## Skipped Issues

### WR-18: Lambda callbacks create asyncio tasks that may fire after shutdown

**File:** `src/python/server/main.py:580-604`
**Reason:** Code context differs from review -- the base git version does not contain the lambda callbacks with `asyncio.create_task(broadcast_event(...))` that the review finding references. Those callbacks exist only in the uncommitted working copy modifications.

**Original issue:** Lambda callbacks capture `asyncio.create_task` and call it when the event fires. During shutdown, the event loop may be closed, causing `RuntimeError: Event loop is closed`.

---

_Fixed: 2026-05-30T12:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
