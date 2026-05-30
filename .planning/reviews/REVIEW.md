---
phase: code-review
reviewed: 2026-05-30T12:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - src/electron/main/main.js
  - src/python/modules/audio/audio_pipeline.py
  - src/python/modules/camera/camera_pipeline.py
  - src/python/modules/fusion/identity_fusion.py
  - src/python/modules/llm/llm_provider.py
  - src/python/modules/pose/gesture_classifier.py
  - src/python/modules/skill_loader/skill_loader.py
  - src/python/modules/state/state_machine.py
  - src/python/modules/tts/text_to_speech.py
  - src/python/requirements.txt
  - src/python/server/conversation.py
  - src/python/server/main.py
findings:
  critical: 2
  warning: 19
  info: 9
  total: 30
status: issues_found
---

# Code Review Report

**Reviewed:** 2026-05-30T12:00:00Z
**Depth:** Standard
**Files Reviewed:** 12
**Status:** Issues Found

## Summary

Reviewed 12 source files spanning the Frank project's Electron main process, Python inference server, and core modules (audio, camera, identity fusion, LLM, pose/gesture, skill loader, state machine, TTS, conversation). Identified **2 critical**, **19 warning**, and **9 info** findings.

The most severe issues are: (1) a coroutine never awaited in `ConversationOrchestrator.handle_text_input` causing silent message loss in text input mode, and (2) an invalid OpenWakeWord model name that silently disables wake word detection entirely. Beyond these, the codebase shows recurring patterns of unhandled coroutine callbacks, silent error swallowing, missing debounce on events, and evidence queue management defects in the fusion engine.

---

## Critical Issues

### CR-01: Coroutine never awaited in `handle_text_input` — assistant message silently dropped

**File:** `src/python/server/conversation.py:154`

**Issue:** The `handle_text_input` method calls `self._on_assistant_message({'text': response})` without the `await` keyword, and without checking whether the callback is a coroutine function. The callback is set to `on_assistant_message` in `main.py:471`, which is an `async def` function. Calling a coroutine function without `await` creates a coroutine object that is garbage-collected and never executed, producing a `RuntimeWarning: coroutine 'on_assistant_message' was never awaited`. The assistant's response is silently lost for all text-based input. The sister method `process_speech` correctly handles this pattern at lines 116-120 with `iscoroutinefunction` checks and `await`.

**Fix:** Apply the same pattern used in `process_speech` (lines 116-120):

```python
# In handle_text_input, replace line 154-155:
if response and self._on_assistant_message:
    if asyncio.iscoroutinefunction(self._on_assistant_message):
        await self._on_assistant_message({'text': response})
    else:
        self._on_assistant_message({'text': response})
```

### CR-02: OpenWakeWord model name invalid — wake word detection always disabled

**File:** `src/python/modules/audio/audio_pipeline.py:209`

**Issue:** The OpenWakeWord model is initialized with `wakeword_models=[self.wake_word_text]` where `self.wake_word_text` defaults to `'Hey Frank'`. OpenWakeWord's `Model` constructor expects either a pre-trained model name (e.g., `"alexa"`, `"hey_jarvis"`) or a file path to a custom ONNX model. `'Hey Frank'` with a space and mixed case matches no built-in model. The `Model()` constructor raises an exception (caught by the bare `except` at line 212), setting `self._wake_word_model = None`. Wake word detection at line 331 checks `if self._wake_word_model` and always skips. The wake word feature is entirely non-functional with the default configuration, and the only error message is a generic `logger.warning` at INFO level.

**Fix:** Use a valid pre-trained model name from OpenWakeWord, or accept the model name as a separate configuration field distinct from the trigger phrase text:

```python
# Option 1: Use a built-in model name from config
wake_model_name = self.wake_word_config.get('model_name', 'hey_jarvis')
self._wake_word_model = Model(wakeword_models=[wake_model_name], inference_framework='onnx')

# Option 2: Separate the trigger text from the model identifier
self.wake_word_text = self.wake_word_config.get('text', 'Hey Frank')
wake_model_name = self.wake_word_config.get('model', 'hey_jarvis')
self._wake_word_model = Model(wakeword_models=[wake_model_name], inference_framework='onnx')
```

---

## Warnings

### WR-01: Windows registry command vulnerable to shell injection

**File:** `src/electron/main/main.js:30`

**Issue:** `execSync` with string interpolation runs via `cmd.exe /c` on Windows. While `process.execPath` is not user-controlled in normal operation, a path containing double-quote characters (`"`) could break out of the quoting and inject arbitrary commands. The variable `appPath` should be validated or `execFile`/`spawn` should be used with array arguments instead.

**Fix:**
```javascript
// Use spawn with argument array instead of execSync with string
const { spawnSync } = require('child_process');
if (enabled) {
  spawnSync('reg', ['add', regKey, '/v', regValue, '/t', 'REG_SZ', '/d', appPath, '/f']);
} else {
  spawnSync('reg', ['delete', regKey, '/v', regValue, '/f']);
}
```

### WR-02: `scheduleReconnect` prints warning but ignores it

**File:** `src/electron/main/main.js:133-139`

**Issue:** When `backoff` is invalid (not an array or empty), the code prints a warning but continues to reference the original `backoff` variable for `safeBackoff` computation. The warning has no effect on behavior since `safeBackoff` is constructed from the same `backoff` that was just deemed invalid. The warning is misleading — it suggests remediation but the variable isn't corrected.

**Fix:**
```javascript
let safeBackoff = config.websocket?.reconnect_backoff;
if (!Array.isArray(safeBackoff) || safeBackoff.length === 0) {
    console.warn('[Frank] Invalid reconnect_backoff config, using defaults');
    safeBackoff = [1, 2, 4, 8, 16, 30];
}
// Remove the redundant backoff check below
```

### WR-03: Tray menu setInterval never cleaned up

**File:** `src/electron/main/main.js:405`

**Issue:** The `setInterval` at line 405 (5-second tray menu update) is never cleared. On `before-quit` (line 474), all other resources are cleaned up but this interval leaks. If the tray is later destroyed (e.g., during a re-create cycle), the interval still fires and calls `tray.setContextMenu()` on a potentially null reference.

**Fix:** Store the interval ID and clear it in `before-quit`:
```javascript
// Store interval ID in module scope
let trayUpdateInterval = null;
// At creation:
trayUpdateInterval = setInterval(...);
// In before-quit:
if (trayUpdateInterval) {
    clearInterval(trayUpdateInterval);
    trayUpdateInterval = null;
}
```

### WR-04: `asyncio.run_coroutine_threadsafe` futures never handled

**File:** `src/python/modules/audio/audio_pipeline.py:378, 391, 448, 481, 488`

**Issue:** Every call to `asyncio.run_coroutine_threadsafe()` returns a `concurrent.futures.Future` whose result is never retrieved. Exceptions raised inside the callback coroutine are silently lost. If a callback raises, the exception is only visible via the event loop's default exception handler, providing no traceability.

**Fix:** Add `.add_done_callback()` to log errors, or wrap the coroutine target in a try-except:
```python
future = asyncio.run_coroutine_threadsafe(
    self._emit_voice_start(payload), self._main_loop)
future.add_done_callback(lambda f: f.result() if f.exception() is None else logger.error(f'Callback error: {f.exception()}'))
```

### WR-05: `snr` variable may be undefined in voiceprint extraction logging

**File:** `src/python/modules/audio/audio_pipeline.py:445`

**Issue:** The `snr` variable is assigned inside a `try` block (line 424). If an exception occurs before that line (e.g., `np.mean(speech ** 2)` raises for NaN/inf values), the `except Exception: pass` at line 429 catches it but `snr` is never assigned. The f-string at line 445 (`f'... SNR={snr:.1f}dB'`) then raises `NameError`. This is caught by the outer `except` at line 454, but the voiceprint extraction silently fails with no useful diagnostic.

**Fix:** Initialize `snr` before the try block:
```python
snr = 0.0  # safe default
try:
    ...
    snr = 10 * np.log10(...)
except Exception:
    pass
```

### WR-06: No debounce on face_lost event

**File:** `src/python/modules/camera/camera_pipeline.py:269-270`

**Issue:** A single frame where no face is detected triggers `_emit_face_lost()`. Brief occlusion, motion blur, or detection jitter causes rapid face_lost/face_detected cycling. This floods the Electron client and the state machine with redundant events.

**Fix:** Add a grace period (e.g., 3 consecutive frames) before emitting face_lost:
```python
self._no_face_frames = 0  # class attribute
# In capture loop:
if current_count == 0 and self._faces_last_frame > 0:
    self._no_face_frames += 1
    if self._no_face_frames >= 3:  # debounce
        await self._emit_face_lost()
        self._no_face_frames = 0
elif current_count > 0:
    self._no_face_frames = 0
```

### WR-07: Camera error callback floods on disconnect

**File:** `src/python/modules/camera/camera_pipeline.py:245-249`

**Issue:** When the camera is disconnected, every capture loop iteration (~10/sec) fires `_emit_error('CAM_DISCONNECTED', ...)`. There is no debounce, so errors accumulate rapidly in the Electron client.

**Fix:** Track the last error emit time per error code and debounce:
```python
# class attribute:
self._last_error_time: dict[str, float] = {}
# In capture loop:
if now - self._last_error_time.get('CAM_DISCONNECTED', 0) > 5:
    await self._emit_error(...)
    self._last_error_time['CAM_DISCONNECTED'] = now
```

### WR-08: Evidence queues never drained, evaluate runs on stale data

**File:** `src/python/modules/fusion/identity_fusion.py:279-281, 156-159`

**Issue:** The face and voice evidence queues (`_face_queue`, `_voice_queue`) are append-only — items are never removed after evaluation. The `has_new` check at line 279-280 is always `True` once any evidence exists, causing `_evaluate()` to run every 300ms on the same evidence. This also inflates `evidence_count` with each redundant evaluation pass (line 180: `self._state.evidence_count + 1`).

**Fix:** Only set `has_new` when new evidence has arrived since the last evaluation. Add a `_last_evaluated` timestamp, or clear processed items from the queues:
```python
self._last_evaluated = 0.0
has_new = (self._last_face_event_time > self._last_evaluated or 
           self._last_voice_event_time > self._last_evaluated)
# After evaluate:
self._last_evaluated = time.time()
```

### WR-09: `EVIDENCE_MIN_COUNT` defined but never used

**File:** `src/python/modules/fusion/identity_fusion.py:82`

**Issue:** The constant `EVIDENCE_MIN_COUNT = 2` is defined but never referenced in `_evaluate()` or anywhere else. Either remove it or implement the evidence accumulation gate it was intended for.

**Fix:** Either remove the constant or add the check to `_evaluate()`:
```python
# After computing new_state:
if new_state.evidence_count < self.EVIDENCE_MIN_COUNT:
    new_state.status = IdentityStatus.TENTATIVE  # insufficient evidence
```

### WR-10: Fusion engine process loop calls `update_member` on every cycle

**File:** `src/python/modules/fusion/identity_fusion.py:303-304`

**Issue:** When the state is CONFIRMED, `update_member(new_state.member_id, last_active_at=...)` is called every 300ms, even if the same identity was already confirmed. This writes to the SQLite database on every loop iteration, generating unnecessary disk I/O.

**Fix:** Only update `last_active_at` when it changes by more than a threshold (e.g., 60 seconds):
```python
if new_state.member_id:
    now_iso = datetime.now(timezone.utc).isoformat()
    if not hasattr(self, '_last_active_update') or \
       (time.time() - self._last_active_update) > 60:
        update_member(new_state.member_id, last_active_at=now_iso)
        self._last_active_update = time.time()
```

### WR-11: Honorific gender inference from name is fragile

**File:** `src/python/modules/llm/llm_provider.py:242`

**Issue:** The honorific is inferred by checking if `'女士'` is in the display name, and defaulting to `'先生'` otherwise. This is incorrect for: (1) names containing neither indicator (e.g., "Zhang San" → "Zhang San先生"), (2) children or guests, (3) users whose display name uses non-Chinese conventions. The role or identity data should contain an explicit gender/title field.

**Fix:** Add an explicit `honorific` or `title` field to identity data, or at minimum use `role` to select appropriate honorifics:
```python
honorific_map = {'owner': '主人', 'adult': '', 'child': '', 'guest': '访客'}
honorific = honorific_map.get(role, display_name)
if role in ('adult', 'owner') and '女士' not in display_name:
    honorific = f'{display_name}先生'
```

### WR-12: `match_custom_gesture` loads all custom gestures from DB on every call

**File:** `src/python/modules/pose/gesture_classifier.py:374`

**Issue:** Every call to `match_custom_gesture` executes `SELECT * FROM custom_gestures` without any caching. As the number of custom gestures grows, this query returns more data, and the subsequent loop iterates over all rows. There is no cache invalidation or pagination.

**Fix:** Cache the loaded gestures and invalidate on registration/deletion:
```python
self._gesture_cache: list | None = None
self._cache_dirty = True
# In match_custom_gesture:
if self._cache_dirty:
    with get_connection() as conn:
        self._gesture_cache = conn.execute("SELECT * FROM custom_gestures").fetchall()
    self._cache_dirty = False
# In register/delete:
self._cache_dirty = True
```

### WR-13: `deserialize_embedding` imported but unused in `match_custom_gesture`

**File:** `src/python/modules/pose/gesture_classifier.py:365`

**Issue:** `deserialize_embedding` is imported from `database` on line 365 but never called. Dead import.

**Fix:** Remove `deserialize_embedding` from the import:
```python
from src.python.shared.database import get_connection  # remove deserialize_embedding
```

### WR-14: Skill watcher task crashes silently on error

**File:** `src/python/modules/skill_loader/skill_loader.py:188-201`

**Issue:** The `_watch` inner function has no try-except. If `self.skills_dir.iterdir()` raises a `PermissionError` or `FileNotFoundError`, the entire watcher coroutine crashes silently. No error is logged, and the task is permanently dead.

**Fix:** Wrap the loop body in try-except:
```python
async def _watch():
    seen = set(self.skills.keys())
    while True:
        try:
            await asyncio.sleep(5)
            if not self.skills_dir.exists():
                continue
            # ... rest of logic ...
        except Exception as e:
            logger.error(f'Skill watcher error: {e}')
            await asyncio.sleep(5)
```

### WR-15: Timeout monitor race condition on state machine restart

**File:** `src/python/modules/state/state_machine.py:175-177`

**Issue:** When `stop()` is called, `_running = False` and the task is cancelled. However, if a new `_do_transition` occurs while the old task's cancellation is still in flight (e.g., the old task is in `await asyncio.sleep(1)`), `_running` is set back to True. When the old task wakes up, it checks `while self._running:` which is now True, and continues running. This creates two concurrent timeout monitors, both issuing state transitions.

**Fix:** Cancel the old task and await its completion before starting a new one:
```python
def _do_transition(self, new_state, trigger):
    # ... transition logic ...
    if self._timeout_task and not self._timeout_task.done():
        self._timeout_task.cancel()
    self._timeout_task = asyncio.create_task(self._timeout_monitor())
    self._running = True
```

### WR-16: Blocking `playsound` call in async context

**File:** `src/python/modules/tts/text_to_speech.py:101`

**Issue:** `playsound(file_path)` is a synchronous blocking call. In the async `speak()` method awaited via `_play_audio`, this blocks the entire asyncio event loop for the duration of the audio file playback (potentially many seconds). No other coroutines can run during playback.

**Fix:** Run playback in a thread executor to avoid blocking the event loop:
```python
async def _play_audio(self, file_path: str):
    loop = asyncio.get_running_loop()
    try:
        import platform
        if platform.system() == 'Windows':
            from playsound import playsound
            await loop.run_in_executor(None, playsound, file_path)
        else:
            import subprocess
            await loop.run_in_executor(None, lambda: subprocess.run(
                ['ffplay', '-nodisp', '-autoexit', file_path],
                capture_output=True, timeout=30))
    except Exception as e:
        logger.error(f'Audio playback error: {e}')
        raise
```

### WR-17: `broadcast_event` silently swallows all exceptions

**File:** `src/python/server/main.py:367-369`

**Issue:** The `except Exception: pass` in the broadcast loop makes debugging WebSocket send failures impossible. If a client disconnects mid-broadcast, the error is hidden.

**Fix:** Log the exception at DEBUG level:
```python
for ws in list(connected_clients):
    try:
        await send_message(ws, msg_type, payload)
    except Exception as e:
        logger.debug(f'Broadcast to client failed: {e}')
```

### WR-18: Lambda callbacks create asyncio tasks that may fire after shutdown

**File:** `src/python/server/main.py:580-604` (multiple locations)

**Issue:** Lambda callbacks (lines 580, 588, 590, 598, 600, 603) capture `asyncio.create_task` and call it when the event fires. During graceful shutdown, the event loop may be closing or stopped, causing `asyncio.create_task()` to raise `RuntimeError: Event loop is closed`. These are one-shot lambdas set during initialization; they don't check if the loop is running.

**Fix:** Check loop status before creating tasks, or use a robust wrapper:
```python
def _safe_broadcast(msg_type):
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            asyncio.create_task(broadcast_event(msg_type, info))
    except RuntimeError:
        pass  # event loop is closing
```

### WR-19: STT model may not be ready when first speech is processed

**File:** `src/python/server/main.py:582` and `src/python/server/conversation.py:82`

**Issue:** The STT model is loaded asynchronously via `asyncio.create_task(stt_module.load_model())`. If a wake word arrives before the model finishes loading, `conversation.process_speech` at line 82 calls `await self._stt_module.transcribe(...)` on a not-yet-ready module. The module may raise or return empty results depending on implementation.

**Fix:** Check STT readiness before transcribing:
```python
if self._stt_module:
    if hasattr(self._stt_module, 'is_ready') and not self._stt_module.is_ready:
        logger.warning('STT module not ready yet, skipping transcription')
        await self._change_sub_state(ChatSubState.LISTENING)
        return
    transcription = await self._stt_module.transcribe(audio_np, sample_rate)
```

---

## Info

### IN-01: `Math.random()` used for UUID generation

**File:** `src/electron/main/main.js:178`

**Issue:** UUIDs generated with `Math.random()` are not cryptographically secure. For WebSocket message IDs this is acceptable, but if UUIDs are later used for session tokens or security-sensitive identifiers, they must use `crypto.randomUUID()`.

**Fix:** Use `crypto.randomUUID()` for proper UUID v4:
```javascript
const crypto = require('crypto');
function generateUUID() {
    return crypto.randomUUID();
}
```

### IN-02: `dtw_distance` static method defined but never called

**File:** `src/python/modules/pose/gesture_classifier.py:293-307`

**Issue:** `_dtw_distance` implements dynamic time warping for sequence matching but `match_custom_gesture` uses cosine similarity on mean features instead. Approximately 15 lines of dead code.

**Fix:** Either remove the dead method or re-implement `match_custom_gesture` to use DTW for temporal alignment.

### IN-03: Imports inside method bodies

**File:** `src/python/modules/pose/gesture_classifier.py:341, 365, 406, 414`

**Issue:** `from src.python.shared.database import get_connection` is imported inside four separate method bodies. While Python caches modules after first import, this pattern is non-standard and makes the dependency less visible at the top of the file.

**Fix:** Move the shared import to the top of the file:
```python
from src.python.shared.database import get_connection, deserialize_embedding
```

### IN-04: `submit_voice_evidence` ignores the `confidence` parameter

**File:** `src/python/modules/fusion/identity_fusion.py:137-152`

**Issue:** The `confidence` parameter is accepted but never used — the method computes its own score from the database search. The caller in `main.py:427` always passes `1.0` which has no effect. This is dead code.

**Fix:** Either remove the unused parameter or use it as a prior/multiplier on the database score:
```python
ev.score = (matches[0][1] if matches else 0.0) * confidence
```

### IN-05: Unused `import sys` in skill_loader

**File:** `src/python/modules/skill_loader/skill_loader.py:14`

**Issue:** Module-level `import sys` is never referenced anywhere in the file. Dead import.

**Fix:** Remove the unused import.

### IN-06: `VADIterator` imported but unused in audio_pipeline.py

**File:** `src/python/modules/audio/audio_pipeline.py:199`

**Issue:** The import `from silero_vad import load_silero_vad, read_audio, VADIterator` includes `VADIterator` which is never used. Only `load_silero_vad` is called.

**Fix:** Remove `VADIterator` and `read_audio` from the import.

### IN-07: `conversation.py` does not use `ChatSubState.LISTENING` initial state

**File:** `src/python/server/conversation.py:27-28`

**Issue:** `ChatSubState` is fully defined and exported (used in `main.py:45`), but the initial sub-state `LISTENING` is set directly in `__init__` without any transition side effects (e.g., no callback fires). This is expected but the state enum could be reduced if this is the only use case.

### IN-08: Tray re-creates context menu from scratch every 5 seconds

**File:** `src/electron/main/main.js:405-439`

**Issue:** The `setInterval` at line 405 rebuilds the entire `Menu` from the template every 5 seconds, even though only the state label changes. This allocates a new `Menu` object every 5 seconds for the app's lifetime. Minor inefficiency; could use `menu.items[2].label` update instead.

### IN-09: `identity_fusion.py` imports `datetime` but doesn't use it at module level

**File:** `src/python/modules/fusion/identity_fusion.py:17`

**Issue:** `from datetime import datetime, timezone` is imported. `datetime.now(timezone.utc)` is used only in the `CONFIRMED` case at line 304, so this is used. Correct import.

---

_Reviewed: 2026-05-30T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
