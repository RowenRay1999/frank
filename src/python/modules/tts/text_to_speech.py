"""
Frank 文字转语音模块 (Phase 3)

edge-tts: 免费 Microsoft Edge TTS，中文自然度高
"""

import asyncio
import io
import logging
import os
import tempfile
from typing import Any, Callable

logger = logging.getLogger('frank.tts')


class TextToSpeech:
    """edge-tts 文字转语音"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.voice = self.config.get('voice', 'zh-CN-XiaoxiaoNeural')
        self.speed = self.config.get('speed', 1.0)
        self._speaking = False
        self._stop_requested = False

        self._on_start: Callable | None = None
        self._on_complete: Callable | None = None
        self._on_unavailable: Callable | None = None

    def set_on_start(self, cb: Callable): self._on_start = cb
    def set_on_complete(self, cb: Callable): self._on_complete = cb
    def set_on_unavailable(self, cb: Callable): self._on_unavailable = cb

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    async def speak(self, text: str, retry_count: int = 2) -> bool:
        """朗读文本"""
        if not text:
            return False

        self._speaking = True
        self._stop_requested = False

        if self._on_start:
            self._on_start({'text': text[:50]})

        tmp_path = None

        for attempt in range(retry_count + 1):
            try:
                import edge_tts

                # 生成音频
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=self.voice,
                    rate=f'{int((self.speed - 1) * 100):+d}%',
                )

                # 流式保存到临时文件
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                    tmp_path = tmp.name
                    await communicate.save(tmp.name)

                # 播放
                await self._play_audio(tmp_path)

                if self._on_complete:
                    self._on_complete({'text': text[:50]})
                self._speaking = False
                return True

            except Exception as e:
                logger.warning(f'TTS attempt {attempt + 1} failed: {e}')
                if attempt >= retry_count:
                    logger.error('TTS all retries exhausted, switching to text-only')
                    if self._on_unavailable:
                        self._on_unavailable({'reason': str(e)})
                await asyncio.sleep(0.5)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                        tmp_path = None
                    except OSError:
                        pass

        self._speaking = False
        return False

    async def _play_audio(self, file_path: str):
        """播放音频文件"""
        loop = asyncio.get_running_loop()
        try:
            import platform
            if platform.system() == 'Windows':
                try:
                    from playsound import playsound
                    await loop.run_in_executor(None, playsound, file_path)
                except Exception:
                    # fallback to winsound for WAV files
                    import winsound
                    await loop.run_in_executor(None, lambda: winsound.PlaySound(file_path, winsound.SND_FILENAME))
            else:
                # Linux/macOS: 使用系统命令
                import subprocess
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ['ffplay', '-nodisp', '-autoexit', file_path],
                    capture_output=True, timeout=30))
        except Exception as e:
            logger.error(f'Audio playback error: {e}')
            raise

    def stop(self):
        """停止当前播放"""
        self._stop_requested = True
        self._speaking = False

    def set_voice(self, voice: str):
        """切换语音"""
        self.voice = voice

    def set_speed(self, speed: float):
        """设置语速 (0.5-2.0)"""
        self.speed = max(0.5, min(2.0, speed))
