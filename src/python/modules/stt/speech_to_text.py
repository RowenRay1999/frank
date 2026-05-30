"""
Frank 语音转文字模块 (Phase 3)

faster-whisper medium 模型：中文优先，CPU 实时转写
"""

import asyncio
import logging
import time
from typing import Any, Callable

import numpy as np

logger = logging.getLogger('frank.stt')

# 延迟导入
_faster_whisper = None
_WhisperModel = None


class SpeechToText:
    """faster-whisper 语音转文字"""

    def __init__(self, model_size: str = 'medium', device: str = 'cpu',
                 compute_type: str = 'int8', language: str = 'zh'):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._model = None
        self._ready = False
        self._loading = False

        # 回调
        self._on_transcription: Callable | None = None
        self._on_error: Callable | None = None

    def set_on_transcription(self, callback: Callable):
        self._on_transcription = callback

    def set_on_error(self, callback: Callable):
        self._on_error = callback

    @property
    def is_ready(self) -> bool:
        return self._ready

    async def load_model(self):
        """异步加载模型"""
        if self._loading or self._ready:
            return
        self._loading = True

        try:
            logger.info(f'Loading faster-whisper {self.model_size} model...')
            from faster_whisper import WhisperModel
            import os

            model_path = os.path.join('data', 'models', f'faster-whisper-{self.model_size}')
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=model_path,
            )
            self._ready = True
            logger.info('faster-whisper model loaded')
        except Exception as e:
            logger.error(f'Failed to load faster-whisper: {e}')
            self._ready = False
            if self._on_error:
                self._on_error({'code': 'STT_MODEL_FAILED', 'message': str(e)})
        finally:
            self._loading = False

    async def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> dict | None:
        """转写音频段为文本"""
        if not self._ready:
            logger.warning('STT model not ready, queuing transcription...')
            return None

        start_time = time.time()
        try:
            # faster-whisper 需要 float32 数组
            audio_f32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio

            segments, info = self._model.transcribe(
                audio_f32,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                ),
            )

            # 合并所有 segments
            texts = []
            total_confidence = 0.0
            segment_count = 0
            for seg in segments:
                texts.append(seg.text)
                total_confidence += seg.avg_logprob
                segment_count += 1

            text = ' '.join(texts).strip()
            avg_confidence = total_confidence / segment_count if segment_count > 0 else 0.0
            duration_ms = (time.time() - start_time) * 1000

            result = {
                'text': text,
                'confidence': avg_confidence,
                'duration_ms': duration_ms,
                'language': info.language,
                'language_probability': info.language_probability,
            }

            logger.info(f'STT: "{text[:50]}..." ({duration_ms:.0f}ms, conf={avg_confidence:.3f})')

            if self._on_transcription:
                if asyncio.iscoroutinefunction(self._on_transcription):
                    await self._on_transcription(result)
                else:
                    self._on_transcription(result)

            return result

        except Exception as e:
            logger.error(f'STT transcription error: {e}')
            if self._on_error:
                self._on_error({'code': 'STT_FAILED', 'message': str(e)})
            return None

    def transcribe_sync(self, audio: np.ndarray, sample_rate: int = 16000) -> dict | None:
        """同步转写（供非 async 上下文调用）"""
        if not self._ready or self._model is None:
            return None

        try:
            audio_f32 = audio.astype(np.float32) if audio.dtype != np.float32 else audio
            segments, info = self._model.transcribe(
                audio_f32, language=self.language, beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            texts = [seg.text for seg in segments]
            return {
                'text': ' '.join(texts).strip(),
                'confidence': 0.0,
                'duration_ms': 0,
                'language': info.language,
            }
        except Exception as e:
            logger.error(f'STT sync transcription error: {e}')
            return None
