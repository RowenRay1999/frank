"""
Frank 配置管理模块
加载 config/frank.yaml 配置文件
"""

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger('frank.config')

# 项目根目录（config.py 在 src/python/shared/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_config: dict[str, Any] | None = None


def get_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """加载并返回配置（带缓存）。

    配置文件路径查找顺序：
    1. 传入的 config_path
    2. PROJECT_ROOT / config / frank.yaml
    """
    global _config

    if _config is not None and config_path is None:
        return _config

    if config_path is None:
        config_path = PROJECT_ROOT / 'config' / 'frank.yaml'

    config_path = Path(config_path)

    if not config_path.exists():
        logger.warning(f'Config file not found: {config_path}, using defaults')
        _config = _get_defaults()
        return _config

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            _config = yaml.safe_load(f)
        logger.info(f'Config loaded from {config_path}')
        return _config
    except Exception as e:
        logger.error(f'Failed to load config: {e}')
        _config = _get_defaults()
        return _config


def reload_config():
    """强制重新加载配置"""
    global _config
    _config = None
    return get_config()


def _deep_merge(base: dict, update: dict) -> dict:
    """深度合并两个字典，update 的值覆盖 base"""
    for key, value in update.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def update_config(partial: dict, config_path: str | Path | None = None) -> dict:
    """部分更新配置并写回 YAML 文件。

    Args:
        partial: 要更新的配置键值对（支持嵌套）
        config_path: 配置文件路径，默认 PROJECT_ROOT / config / frank.yaml

    Returns:
        更新后的完整配置
    """
    global _config

    if config_path is None:
        config_path = PROJECT_ROOT / 'config' / 'frank.yaml'

    config_path = Path(config_path)

    # 确保已有配置加载
    current = get_config(config_path)

    # 深度合并
    _deep_merge(current, partial)
    _config = current

    # 写回 YAML
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        logger.info(f'Config updated and saved to {config_path}')
    except Exception as e:
        logger.error(f'Failed to write config: {e}')
        raise

    return current


def reset_config(config_path: str | Path | None = None) -> dict:
    """重置配置为默认值并写回 YAML 文件"""
    defaults = _get_defaults()
    return update_config(defaults, config_path)


def _get_defaults() -> dict[str, Any]:
    return {
        'camera': {
            'device_id': 0,
            'width': 640,
            'height': 480,
            'fps_idle': 1,
            'fps_aware': 5,
            'fps_active': 10,
            'detection_confidence': 0.7,
        },
        'microphone': {
            'device_id': None,
            'sample_rate': 16000,
            'chunk_size': 512,
            'channels': 1,
            'bits_per_sample': 16,
            'ring_buffer_seconds': 10,
            'pre_trigger_seconds': 1.5,
            'silence_threshold_ms': 800,
        },
        'wake_word': {
            'text': 'Hey Frank',
            'model': 'openwakeword',
            'confidence_threshold': 0.7,
            'face_cooldown_ms': 1000,
        },
        'websocket': {
            'host': 'localhost',
            'port': 8765,
            'port_max_retries': 15,
            'heartbeat_interval': 5,
            'heartbeat_missed_max': 3,
            'reconnect_backoff': [1, 2, 4, 8, 16, 30],
        },
        'state_machine': {
            'timeout_aware_to_idle': 30,
            'timeout_auth_delay': 2,
            'timeout_chat_to_auth': 300,
            'timeout_auth_to_idle': 60,
        },
        'logging': {
            'level': 'INFO',
            'file': 'logs/frank.log',
            'max_size_mb': 10,
            'backup_count': 3,
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        },
        'app': {
            'auto_start': True,
            'minimize_to_tray': True,
            'always_on_top': False,
            'language': 'zh-CN',
        },
        'llm': {
            'provider': 'openai',
            'model': 'gpt-4o-mini',
            'base_url': None,
            'api_key_env': 'FRANK_LLM_API_KEY',
            'timeout': 15,
            'max_tokens': 1024,
            'temperature': 0.7,
            'max_history_rounds': 10,
        },
        'tts': {
            'voice': 'zh-CN-YunxiNeural',
            'speed': 1.0,
            'retry_count': 2,
            'volume': 0.8,
        },
        'wakefree': {
            'enabled': True,
            'face_required': True,
            'face_window_seconds': 2,
        },
        'visual_intent': {
            'enabled': True,
            'gaze_threshold': 10.0,
            'gaze_duration': 2.0,
            'nod_threshold': 0.015,
            'shake_threshold': 0.015,
        },
        'multi_output': {
            'secondary_audio_device_id': None,
            'secondary_display_id': None,
        },
        'tasks': {
            'max_retries': 3,
            'retry_backoff_base': 2,
            'history_retention_hours': 24,
        },
        'pose': {
            'enabled': True,
            'min_detection_confidence': 0.5,
            'min_tracking_confidence': 0.5,
            'model_complexity': 1,
        },
        'gesture': {
            'enabled': True,
            'dtw_threshold': 0.65,
            'debounce_seconds': 3,
            'window_frames': 30,
        },
        'privacy': {
            'auto_clean': True,
            'clean_days': 30,
            'notify_days': 3,
        },
    }
