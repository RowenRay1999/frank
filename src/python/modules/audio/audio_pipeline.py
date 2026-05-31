"""
Frank 音频采集管线

负责：
1. 麦克风设备枚举
2. PyAudio 音频采集（16kHz / 16bit / mono）
3. 10 秒环形缓冲区
4. Silero VAD 语音活动检测
5. OpenWakeWord 唤醒词检测
6. SpeechBrain ECAPA-TDNN 声纹提取（Phase 2）

Phase 2: 新增声纹 embedding 提取，用于身份识别
"""

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Any, Callable

import numpy as np

logger = logging.getLogger('frank.audio')

VOICEPRINT_EMBEDDING_DIM = 192
MIN_SPEECH_DURATION = 1.5  # 最少语音时长（秒）
MIN_SNR_DB = 10.0  # 最低信噪比

# ─── 环形缓冲区 ───────────────────────────────────────────

class RingBuffer:
    """线程安全的环形音频缓冲区"""

    def __init__(self, capacity_seconds: float, sample_rate: int):
        self.capacity = int(capacity_seconds * sample_rate)
        self._buffer = deque(maxlen=self.capacity)
        self._lock = threading.Lock()
        self.sample_rate = sample_rate

    def append(self, samples: np.ndarray):
        """追加音频样本"""
        with self._lock:
            self._buffer.extend(samples.tolist())

    def get_all(self) -> tuple[np.ndarray, float]:
        """获取缓冲区全部内容，返回 (array, timestamp)"""
        with self._lock:
            data = np.array(list(self._buffer), dtype=np.float32)
            return data, time.time()

    def get_segment(self, pre_seconds: float, post_samples: int = 0) -> np.ndarray:
        """获取触发点前 pre_seconds 秒的音频段 + post_samples 个样本"""
        with self._lock:
            pre_count = int(pre_seconds * self.sample_rate)
            data = list(self._buffer)

            # 从末尾往前取 pre_count 个样本
            start = max(0, len(data) - pre_count - post_samples)
            end = len(data) + post_samples
            segment = data[start:min(end, len(data))]

            if len(segment) == 0:
                return np.array([], dtype=np.float32)
            return np.array(segment, dtype=np.float32)

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def __len__(self):
        return len(self._buffer)


# ─── 音频管线 ─────────────────────────────────────────────

class AudioPipeline:
    """麦克风采集 + VAD + 唤醒词管线"""

    def __init__(self, config: dict[str, Any] | None = None, wake_word_config: dict[str, Any] | None = None):
        self.config = config or {}
        self.wake_word_config = wake_word_config or {}

        # 音频参数
        self.sample_rate = self.config.get('sample_rate', 16000)
        self.chunk_size = self.config.get('chunk_size', 512)
        self.channels = self.config.get('channels', 1)
        self.bits_per_sample = self.config.get('bits_per_sample', 16)
        self.device_id = self.config.get('device_id')

        # 环形缓冲区
        self.ring_buffer_seconds = self.config.get('ring_buffer_seconds', 10)
        self.pre_trigger_seconds = self.config.get('pre_trigger_seconds', 1.5)
        self.silence_threshold_ms = self.config.get('silence_threshold_ms', 800)
        self._ring_buffer: RingBuffer | None = None

        # VAD
        self.vad_threshold = 0.5
        self._vad_model = None
        self._voice_active = False
        self._silence_start: float | None = None

        # 唤醒词
        self.wake_word_text = self.wake_word_config.get('text', 'Hey Frank')
        self.wake_word_confidence = self.wake_word_config.get('confidence_threshold', 0.7)
        self.face_cooldown_ms = self.wake_word_config.get('face_cooldown_ms', 1000)
        self._wake_word_model = None

        # Phase 2: 声纹提取
        self._voiceprint_model = None
        self._speech_buffer: list[np.ndarray] = []  # 当前语音段缓冲
        self._speech_start_time: float | None = None
        self._voiceprint_task: asyncio.Task | None = None

        # 状态
        self._running = False
        self._stream = None
        self._pyaudio = None
        self._process_thread: threading.Thread | None = None
        self._main_loop = None  # 主事件循环引用（后台线程安全调度用）

        # 回调
        self._on_voice_start: Callable | None = None
        self._on_voice_end: Callable | None = None
        self._on_wake_word: Callable | None = None
        self._on_voiceprint: Callable | None = None  # Phase 2
        self._on_stt_trigger: Callable | None = None  # Phase 3
        self._on_error: Callable | None = None

        # 预览推送
        self._preview_active = False
        self._on_preview_spectrum: Callable | None = None
        self._current_level_db = -60.0  # 当前麦克风电平 (dB)，供 device.status 广播
        self._latest_voiceprint_matches: list = []  # 最新声纹匹配结果，供预览窗口

    # ─── 回调设置 ───────────────────────────────────────

    def set_on_voice_start(self, callback: Callable):
        self._on_voice_start = callback

    def set_on_voice_end(self, callback: Callable):
        self._on_voice_end = callback

    def set_on_wake_word(self, callback: Callable):
        self._on_wake_word = callback

    def set_on_voiceprint(self, callback: Callable):
        """Phase 2: 声纹 embedding 回调"""
        self._on_voiceprint = callback

    def set_on_stt_trigger(self, callback: Callable):
        """Phase 3: 唤醒词命中后触发 STT 链"""
        self._on_stt_trigger = callback

    def set_on_error(self, callback: Callable):
        self._on_error = callback

    def set_preview_active(self, active: bool):
        """开启/关闭预览频谱推送"""
        self._preview_active = active

    def set_on_preview_spectrum(self, callback: Callable):
        """预览频谱数据回调（FFT bins, VAD, level, pitch）"""
        self._on_preview_spectrum = callback

    def update_voiceprint_matches(self, matches: list):
        """由融合引擎调用，更新当前声纹匹配结果供预览窗口显示"""
        self._latest_voiceprint_matches = matches or []

    # ─── 设备枚举 ───────────────────────────────────────

    @staticmethod
    def enumerate_devices() -> list[dict[str, Any]]:
        """枚举可用音频输入设备"""
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            devices = []
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0:
                    devices.append({
                        'id': i,
                        'name': info.get('name', f'Device {i}'),
                        'sample_rates': [8000, 16000, 44100, 48000],
                        'channels': info.get('maxInputChannels', 1),
                    })
            p.terminate()
            return devices
        except Exception as e:
            logger.warning(f'Failed to enumerate audio devices: {e}')
            return []

    # ─── 启动/停止 ───────────────────────────────────────

    async def start(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """启动音频采集"""
        if params:
            self.device_id = params.get('device_id', self.device_id)
            self.sample_rate = params.get('sample_rate', self.sample_rate)

        # 初始化 PyAudio
        try:
            import pyaudio
            self._pyaudio = pyaudio.PyAudio()
        except Exception as e:
            await self._emit_error('MIC_NOT_FOUND',
                f'无法初始化音频系统: {e}', True,
                '请确认音频驱动已安装')
            raise RuntimeError(f'PyAudio init failed: {e}')

        # 初始化环形缓冲区
        self._ring_buffer = RingBuffer(self.ring_buffer_seconds, self.sample_rate)

        # 初始化 VAD
        try:
            from silero_vad import load_silero_vad, read_audio, VADIterator
            self._vad_model = load_silero_vad()
            logger.info('Silero VAD model loaded')
        except Exception as e:
            logger.warning(f'Silero VAD load failed: {e}, using energy-based VAD fallback')
            self._vad_model = None

        # 初始化唤醒词
        try:
            from openwakeword import Model
            wake_model_name = self.wake_word_config.get('model', 'hey_jarvis')
            self._wake_word_model = Model(wakeword_models=[wake_model_name], inference_framework='onnx')
            logger.info(f'OpenWakeWord model loaded: "{wake_model_name}"')
        except Exception as e:
            logger.warning(f'OpenWakeWord load failed: {e}, wake word detection disabled')
            self._wake_word_model = None

        # Phase 2: 初始化声纹模型 (SpeechBrain ECAPA-TDNN)
        try:
            from speechbrain.inference.speaker import SpeakerRecognition
            self._voiceprint_model = SpeakerRecognition.from_hparams(
                source='speechbrain/spkrec-ecapa-voxceleb',
                savedir='data/models/speechbrain-ecapa',
                run_opts={'device': 'cpu'},
            )
            logger.info('SpeechBrain ECAPA-TDNN voiceprint model loaded')
        except Exception as e:
            logger.warning(f'SpeechBrain load failed: {e}, voiceprint disabled')
            self._voiceprint_model = None

        # 打开音频流
        try:
            device_index = self.device_id if self.device_id is not None else None
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback,
            )
        except Exception as e:
            await self._emit_error('MIC_NOT_FOUND',
                f'无法打开麦克风 (device_id={self.device_id}): {e}', True,
                '请检查麦克风连接，或在设置中选择其他麦克风设备')
            raise RuntimeError(f'Mic open failed: {e}')

        self._running = True
        self._main_loop = asyncio.get_running_loop()
        self._stream.start_stream()

        # 启动处理线程
        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._process_thread.start()

        logger.info(f'Audio pipeline started: sample_rate={self.sample_rate}, chunk={self.chunk_size}')
        return {'device_id': self.device_id, 'sample_rate': self.sample_rate, 'chunk_size': self.chunk_size}

    async def stop(self):
        """停止音频采集"""
        self._running = False

        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None

        self._ring_buffer = None
        self._vad_model = None
        self._wake_word_model = None
        self._main_loop = None

        logger.info('Audio pipeline stopped')

    async def configure(self, params: dict[str, Any]) -> dict[str, Any]:
        """动态更新配置"""
        if 'device_id' in params:
            self.device_id = params['device_id']
        if 'wake_word_text' in params:
            self.wake_word_text = params['wake_word_text']

        if self._running:
            await self.stop()
            await self.start()

        return {'device_id': self.device_id, 'wake_word_text': self.wake_word_text}

    # ─── 音频回调 ───────────────────────────────────────

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio 回调：将音频数据推入环形缓冲区"""
        if status:
            logger.warning(f'Audio callback status: {status}')

        if self._ring_buffer is not None:
            # int16 → float32 归一化
            samples = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
            self._ring_buffer.append(samples)

        # paContinue = 0 (PyAudio constant, avoiding import at module level)
        return (in_data, 0)

    # ─── 处理循环 ───────────────────────────────────────

    def _process_loop(self):
        """后台处理线程：定期扫描环形缓冲区，执行 VAD + 唤醒词检测"""
        logger.info('Audio processing loop started')
        chunk_samples = int(self.sample_rate * 0.032)  # ~32ms

        while self._running:
            try:
                if self._ring_buffer is None or len(self._ring_buffer) < chunk_samples:
                    time.sleep(0.01)
                    continue

                # 获取最新 chunk
                all_data, _ = self._ring_buffer.get_all()
                if len(all_data) < chunk_samples:
                    time.sleep(0.01)
                    continue

                chunk = all_data[-chunk_samples:]

                # VAD 检测
                speech_prob = self._detect_vad(chunk)
                self._handle_vad(speech_prob)

                # 唤醒词检测
                if self._wake_word_model and speech_prob > 0.3:
                    self._detect_wake_word(all_data)

                # 预览频谱推送 (~20Hz)
                if self._preview_active and self._on_preview_spectrum and self._ring_buffer and len(self._ring_buffer) >= 512:
                    try:
                        recent = all_data[-512:]
                        # FFT 频谱
                        fft = np.abs(np.fft.rfft(recent))
                        bins = 32
                        bin_size = len(fft) // bins
                        spectrum = [float(np.mean(fft[i*bin_size:(i+1)*bin_size])) for i in range(bins)]
                        # 归一化
                        max_val = max(spectrum) if max(spectrum) > 0 else 1.0
                        spectrum = [s / max_val for s in spectrum]
                        # 音量电平 (dB)
                        rms = np.sqrt(np.mean(recent ** 2))
                        level_db = float(20 * np.log10(max(rms, 1e-6)))
                        self._current_level_db = level_db  # 存储为实例属性供 device.status 读取
                        # 基频估计 (简单自相关)
                        pitch_hz = 0.0
                        if rms > 0.01:
                            corr = np.correlate(recent, recent, mode='full')
                            corr = corr[len(corr)//2:]
                            corr = corr / (corr[0] + 1e-10)
                            peaks = np.where(corr[16:] > 0.5)[0]
                            if len(peaks) > 0:
                                lag = peaks[0] + 16
                                pitch_hz = float(self.sample_rate / lag) if lag > 0 else 0.0
                        spectrum_msg = {
                            'spectrum_bins': spectrum,
                            'vad_prob': float(speech_prob),
                            'level_db': level_db,
                            'wake_word_trigger': False,
                            'pitch_hz': pitch_hz,
                            'voiceprint_matches': self._latest_voiceprint_matches,
                        }
                        if self._main_loop and self._main_loop.is_running():
                            asyncio.run_coroutine_threadsafe(
                                self._on_preview_spectrum(spectrum_msg),
                                self._main_loop
                            )
                    except Exception:
                        logger.debug('Preview spectrum computation failed', exc_info=True)

                time.sleep(0.01)

            except Exception as e:
                logger.error(f'Process loop error: {e}')
                time.sleep(0.1)

    # ─── VAD ────────────────────────────────────────────

    def _detect_vad(self, chunk: np.ndarray) -> float:
        """检测语音活动概率"""
        # Silero VAD
        if self._vad_model:
            try:
                # Silero VAD 期望 512 或 1024 样本的 tensor
                import torch
                if len(chunk) >= 512:
                    audio_tensor = torch.from_numpy(chunk[:512]).float()
                    prob = self._vad_model(audio_tensor, self.sample_rate).item()
                    return prob
            except Exception:
                pass

        # 能量降级方案
        energy = np.sqrt(np.mean(chunk ** 2))
        # 简单阈值：RMS > 0.01 视为语音
        return min(1.0, energy * 50)

    def _handle_vad(self, speech_prob: float):
        """处理 VAD 结果，触发 voice_start / voice_end 事件 + 语音段缓冲"""
        is_speech = speech_prob >= self.vad_threshold

        if is_speech:
            # 缓冲当前 chunk 用于声纹提取
            if self._ring_buffer:
                all_data, _ = self._ring_buffer.get_all()
                chunk = all_data[-min(len(all_data), self.chunk_size):]
                self._speech_buffer.append(chunk)

            if not self._voice_active:
                self._voice_active = True
                self._silence_start = None
                self._speech_start_time = time.time()
                self._speech_buffer = [chunk] if self._ring_buffer else []
                if self._main_loop and self._main_loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._emit_voice_start({'speech_probability': speech_prob}),
                        self._main_loop
                    )
                    future.add_done_callback(
                        lambda f: logger.error(f'Callback error: {f.exception()}') if f.exception() else None
                    )


        elif not is_speech and self._voice_active:
            if self._silence_start is None:
                self._silence_start = time.time()
            elif time.time() - self._silence_start >= self.silence_threshold_ms / 1000.0:
                self._voice_active = False
                self._silence_start = None
                # 提取声纹
                self._try_extract_voiceprint()
                if self._main_loop and self._main_loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._emit_voice_end({}),
                        self._main_loop
                    )
                    future.add_done_callback(
                        lambda f: logger.error(f'Callback error: {f.exception()}') if f.exception() else None
                    )


    # ─── 声纹提取 (Phase 2) ────────────────────────────

    def _try_extract_voiceprint(self):
        """在语音段结束时尝试提取声纹"""
        if self._voiceprint_model is None or not self._speech_buffer:
            return

        # 合并语音段
        speech = np.concatenate(self._speech_buffer)
        duration = len(speech) / self.sample_rate

        # 质量门控：最少时长
        if duration < MIN_SPEECH_DURATION:
            logger.debug(f'Speech too short for voiceprint: {duration:.1f}s < {MIN_SPEECH_DURATION}s')
            self._speech_buffer = []
            return

        # 质量门控：SNR（简单能量比估计）
        snr = 0.0  # safe default
        try:
            energy = np.mean(speech ** 2)
            if energy < 1e-6:
                self._speech_buffer = []
                return
            # 取前 0.1s 作为噪声估计
            noise_samples = int(self.sample_rate * 0.1)
            noise = speech[:min(noise_samples, len(speech))]
            noise_energy = np.mean(noise ** 2) if len(noise) > 0 else 1e-10
            snr = 10 * np.log10(max(energy, 1e-10) / max(noise_energy, 1e-10))
            if snr < MIN_SNR_DB:
                logger.debug(f'SNR too low for voiceprint: {snr:.1f}dB < {MIN_SNR_DB}dB')
                self._speech_buffer = []
                return
        except Exception:
            pass

        # 提取 192-dim embedding
        try:
            import torch
            # SpeechBrain 需要 16kHz 单声道 tensor
            audio_tensor = torch.from_numpy(speech).float().unsqueeze(0)
            embedding = self._voiceprint_model.encode_batch(audio_tensor)
            emb_np = embedding.squeeze().detach().cpu().numpy()

            # L2 归一化
            norm = np.linalg.norm(emb_np)
            if norm > 0:
                emb_np = emb_np / norm

            logger.debug(f'Voiceprint extracted: duration={duration:.1f}s, SNR={snr:.1f}dB')

            # 推送到回调
            if self._main_loop and self._main_loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._emit_voiceprint({'embedding': emb_np.tolist(), 'duration': duration}),
                    self._main_loop
                )
                future.add_done_callback(
                    lambda f: logger.error(f'Callback error: {f.exception()}') if f.exception() else None
                )


        except Exception as e:
            logger.error(f'Voiceprint extraction error: {e}')
        finally:
            self._speech_buffer = []

    # ─── 唤醒词 ─────────────────────────────────────────

    def _detect_wake_word(self, audio_data: np.ndarray):
        """检测唤醒词"""
        if self._wake_word_model is None:
            return

        try:
            # OpenWakeWord 需要至少 0.5 秒的音频
            min_samples = int(self.sample_rate * 0.5)
            if len(audio_data) < min_samples:
                return

            # 取最后 2 秒进行检测
            window_samples = int(self.sample_rate * 2)
            window = audio_data[-min(len(audio_data), window_samples):]

            predictions = self._wake_word_model.predict(window)
            for model_name, score in predictions.items():
                if score > self.wake_word_confidence:
                    logger.info(f'Wake word "{model_name}" detected! Confidence: {score:.3f}')
                    if self._main_loop and self._main_loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            self._emit_wake_word({'text': model_name, 'confidence': float(score)}),
                            self._main_loop
                        )
                        future.add_done_callback(
                            lambda f: logger.error(f'Callback error: {f.exception()}') if f.exception() else None
                        )
                        # Phase 3: STT trigger — extract audio segment + send to STT
                        if self._on_stt_trigger:
                            audio_segment = self._ring_buffer.get_segment(self.pre_trigger_seconds)
                            future2 = asyncio.run_coroutine_threadsafe(
                                self._on_stt_trigger(audio_segment),
                                self._main_loop
                            )
                            future2.add_done_callback(
                                lambda f: logger.error(f'Callback error: {f.exception()}') if f.exception() else None
                            )

        except Exception as e:
            logger.debug(f'Wake word detection error: {e}')

    # ─── 事件发送 ───────────────────────────────────────

    async def _emit_voice_start(self, payload: dict):
        if self._on_voice_start:
            if asyncio.iscoroutinefunction(self._on_voice_start):
                await self._on_voice_start(payload)
            else:
                self._on_voice_start(payload)

    async def _emit_voice_end(self, payload: dict):
        if self._on_voice_end:
            if asyncio.iscoroutinefunction(self._on_voice_end):
                await self._on_voice_end(payload)
            else:
                self._on_voice_end(payload)

    async def _emit_wake_word(self, payload: dict):
        if self._on_wake_word:
            if asyncio.iscoroutinefunction(self._on_wake_word):
                await self._on_wake_word(payload)
            else:
                self._on_wake_word(payload)

    async def _emit_voiceprint(self, payload: dict):
        """Phase 2: 声纹 embedding 事件"""
        if self._on_voiceprint:
            emb_list = payload.get('embedding', [])
            emb_np = np.array(emb_list, dtype=np.float32) if emb_list else None
            if asyncio.iscoroutinefunction(self._on_voiceprint):
                await self._on_voiceprint(emb_np, payload.get('duration', 0))
            else:
                self._on_voiceprint(emb_np, payload.get('duration', 0))

    async def _emit_error(self, code: str, message: str, recoverable: bool, suggestion: str):
        payload = {'code': code, 'message': message, 'recoverable': recoverable, 'suggestion': suggestion}
        if self._on_error:
            if asyncio.iscoroutinefunction(self._on_error):
                await self._on_error(payload)
            else:
                self._on_error(payload)

    def __repr__(self) -> str:
        return f'AudioPipeline(running={self._running}, voice_active={self._voice_active})'
