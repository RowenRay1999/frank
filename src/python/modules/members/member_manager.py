"""
Frank 成员管理系统

负责：
- 主人手动注册（引导采集人脸+声纹）
- 成员 CRUD 与查询
- 未标识人物标识与转换
- 成员删除与隐私保护
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import numpy as np

from src.python.shared.database import (
    add_member, get_member, update_member, delete_member,
    list_all_members, list_unidentified,
    convert_to_member, get_database_stats,
    update_unidentified,
)

logger = logging.getLogger('frank.members')


class RegistrationStep(Enum):
    IDLE = 'idle'
    INFO = 'info'           # 填写姓名+角色
    FACE_CAPTURE = 'face'   # 采集人脸
    VOICE_CAPTURE = 'voice' # 采集声纹
    VERIFY = 'verify'       # 验证
    DONE = 'done'


@dataclass
class RegistrationSession:
    """注册会话状态"""
    session_id: str
    display_name: str = ''
    role: str = 'guest'
    step: RegistrationStep = RegistrationStep.IDLE
    face_samples: list[np.ndarray] = field(default_factory=list)
    voice_samples: list[np.ndarray] = field(default_factory=list)
    face_required: int = 5
    voice_required: int = 3
    created_at: float = field(default_factory=time.time)

    @property
    def face_progress(self) -> float:
        return len(self.face_samples) / self.face_required

    @property
    def voice_progress(self) -> float:
        return len(self.voice_samples) / self.voice_required

    @property
    def is_face_done(self) -> bool:
        return len(self.face_samples) >= self.face_required

    @property
    def is_voice_done(self) -> bool:
        return len(self.voice_samples) >= self.voice_required


# 声纹采集随机句子库
VOICE_SAMPLE_SENTENCES = [
    '今天的天气很适合出门散步',
    '我喜欢在早晨喝一杯热咖啡',
    '弗兰克帮我查一下明天的日程',
    '请帮我把客厅的灯关掉',
    '下午三点有个重要的会议',
    '周末我们一起去公园吧',
    '这段话用来采集我的声音特征',
    '你好弗兰克，今天有什么新鲜事',
    '记得提醒我晚上八点吃药',
    '帮我放一首轻松的音乐',
]


class MemberManager:
    """成员管理器"""

    def __init__(self):
        self._registration: RegistrationSession | None = None
        self._on_registration_update: Callable | None = None

    def set_on_registration_update(self, callback: Callable):
        self._on_registration_update = callback

    # ─── 注册流程 ───────────────────────────────────────

    def start_registration(self) -> str:
        """开始注册，返回 session_id"""
        import uuid
        session_id = str(uuid.uuid4())[:8]
        self._registration = RegistrationSession(session_id=session_id)
        self._registration.step = RegistrationStep.INFO
        logger.info(f'Registration started: {session_id}')
        return session_id

    def set_registration_info(self, display_name: str, role: str) -> dict:
        """Step 1: 设置姓名和角色"""
        if not self._registration:
            raise RuntimeError('No active registration session')

        self._registration.display_name = display_name
        self._registration.role = role
        self._registration.step = RegistrationStep.FACE_CAPTURE

        return self._get_registration_status()

    def add_face_sample(self, embedding: np.ndarray) -> dict:
        """Step 2: 添加人脸样本"""
        if not self._registration:
            raise RuntimeError('No active registration session')

        if self._registration.step != RegistrationStep.FACE_CAPTURE:
            raise RuntimeError(f'Expected step {RegistrationStep.FACE_CAPTURE}, got {self._registration.step}')

        self._registration.face_samples.append(embedding)

        if self._registration.is_face_done:
            self._registration.step = RegistrationStep.VOICE_CAPTURE

        return self._get_registration_status()

    def add_voice_sample(self, embedding: np.ndarray) -> dict:
        """Step 3: 添加声纹样本"""
        if not self._registration:
            raise RuntimeError('No active registration session')

        if self._registration.step != RegistrationStep.VOICE_CAPTURE:
            raise RuntimeError(f'Expected step {RegistrationStep.VOICE_CAPTURE}, got {self._registration.step}')

        self._registration.voice_samples.append(embedding)

        if self._registration.is_voice_done:
            self._registration.step = RegistrationStep.VERIFY

        return self._get_registration_status()

    def verify_and_register(self) -> dict:
        """Step 4: 验证并完成注册"""
        if not self._registration:
            raise RuntimeError('No active registration session')

        if not self._registration.is_face_done or not self._registration.is_voice_done:
            raise RuntimeError('Not enough samples collected')

        # 计算平均 embedding
        face_emb = np.mean(self._registration.face_samples, axis=0)
        voice_emb = np.mean(self._registration.voice_samples, axis=0)

        # 注册为成员
        member_id = add_member(
            display_name=self._registration.display_name,
            role=self._registration.role,
            face_emb=face_emb,
            voice_emb=voice_emb,
        )

        self._registration.step = RegistrationStep.DONE

        result = {
            'member_id': member_id,
            'display_name': self._registration.display_name,
            'role': self._registration.role,
            'face_samples': len(self._registration.face_samples),
            'voice_samples': len(self._registration.voice_samples),
        }

        logger.info(f'Registration complete: {self._registration.display_name} (role={self._registration.role})')
        self._registration = None

        if self._on_registration_update:
            try:
                self._on_registration_update({'status': 'complete', **result})
            except Exception:
                pass

        return result

    def cancel_registration(self):
        """取消注册"""
        if self._registration:
            logger.info(f'Registration cancelled: {self._registration.display_name or self._registration.session_id}')
        self._registration = None

    def _get_registration_status(self) -> dict:
        if not self._registration:
            return {'status': 'idle'}

        return {
            'status': 'in_progress',
            'session_id': self._registration.session_id,
            'display_name': self._registration.display_name,
            'role': self._registration.role,
            'step': self._registration.step.value,
            'face_progress': self._registration.face_progress,
            'voice_progress': self._registration.voice_progress,
            'face_required': self._registration.face_required,
            'voice_required': self._registration.voice_required,
        }

    @staticmethod
    def get_voice_sample_sentence(index: int) -> str:
        """获取声纹采集用的随机句子"""
        return VOICE_SAMPLE_SENTENCES[index % len(VOICE_SAMPLE_SENTENCES)]

    # ─── 成员查询 ───────────────────────────────────────

    @staticmethod
    def get_member(member_id: str) -> dict | None:
        return get_member(member_id)

    @staticmethod
    def list_members() -> list[dict]:
        """列出所有已标识成员（含统计信息）"""
        return list_all_members()

    @staticmethod
    def list_pending() -> list[dict]:
        """列出待标识人物"""
        return list_unidentified()

    # ─── 标识操作 ───────────────────────────────────────

    @staticmethod
    def identify_person(unidentified_id: str, display_name: str, role: str = 'guest',
                         merge_to_member_id: str | None = None) -> str:
        """将未标识人物转换为已标识成员

        如果 merge_to_member_id 指定，则将特征合并到该成员
        """
        if merge_to_member_id:
            # 合并模式：更新现有成员的 embedding
            unid = list_unidentified()
            target = next((p for p in unid if p['id'] == unidentified_id), None)
            if target:
                existing = get_member(merge_to_member_id)
                if existing:
                    from src.python.shared.database import (
                        deserialize_embedding, update_embeddings
                    )
                    # 提取未标识人物的 embedding 并合并
                    face_emb = deserialize_embedding(target.get('face_embedding'), 512)
                    voice_emb = deserialize_embedding(target.get('voice_embedding'), 192)
                    update_embeddings(merge_to_member_id, new_face_emb=face_emb, new_voice_emb=voice_emb)
                    # 删除未标识记录
                    from src.python.shared.database import get_connection
                    with get_connection() as conn:
                        conn.execute("DELETE FROM unidentified WHERE id = ?", (unidentified_id,))
                    logger.info(f'Merged unidentified {unidentified_id[:8]}... into member {merge_to_member_id[:8]}...')
                    return merge_to_member_id

            return convert_to_member(unidentified_id, display_name, role)
        else:
            return convert_to_member(unidentified_id, display_name, role)

    # ─── 成员管理 ───────────────────────────────────────

    @staticmethod
    def update_member_info(member_id: str, display_name: str = None, role: str = None):
        """更新成员信息"""
        updates = {}
        if display_name:
            updates['display_name'] = display_name
        if role:
            updates['role'] = role
        if updates:
            update_member(member_id, **updates)

    @staticmethod
    def remove_member(member_id: str, anonymize_chat: bool = True):
        """删除成员"""
        member = get_member(member_id)
        if not member:
            raise ValueError(f'Member {member_id} not found')

        display_name = member.get('display_name', 'Unknown')

        # TODO Phase 3: 处理对话历史匿名化
        delete_member(member_id)
        logger.info(f'Member removed: {display_name} (anonymize_chat={anonymize_chat})')

    # ─── 声纹频谱 ───────────────────────────────────────

    @staticmethod
    def update_voiceprint_spectrum(member_id: str, spectrum_bins: list[float]):
        import json
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE members SET voiceprint_spectrum = ? WHERE id = ?",
                (json.dumps(spectrum_bins), member_id)
            )

    @staticmethod
    def update_unidentified_spectrum(unid_id: str, spectrum_bins: list[float]):
        import json
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE unidentified SET voiceprint_spectrum = ? WHERE id = ?",
                (json.dumps(spectrum_bins), unid_id)
            )

    # ─── 人脸缩略图 ─────────────────────────────────────

    @staticmethod
    def update_face_thumbnail(member_id: str, thumbnail_path: str):
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE members SET face_thumbnail = ? WHERE id = ?",
                (thumbnail_path, member_id)
            )

    @staticmethod
    def update_unidentified_thumbnail(unid_id: str, thumbnail_path: str):
        from src.python.shared.database import get_connection
        with get_connection() as conn:
            conn.execute(
                "UPDATE unidentified SET face_thumbnail = ? WHERE id = ?",
                (thumbnail_path, unid_id)
            )

    @staticmethod
    def get_stats() -> dict:
        return get_database_stats()
