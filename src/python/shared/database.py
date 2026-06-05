"""
Frank 本地生物特征数据库

SQLite 数据库存储：
- members: 已标识成员的 embedding + 元数据
- unidentified: 自动发现的未标识人物
- skill_preferences: 每个成员的技能偏好
- schema_version: 数据库版本管理

安全原则：embedding 是不可逆特征向量，不出设备，不联网
"""

import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger('frank.database')

# 项目根目录（database.py 在 src/python/shared/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

DEFAULT_DB_PATH = PROJECT_ROOT / 'data' / 'frank.db'
SCHEMA_VERSION = 5

# 线程锁（SQLite 单写多读模式）
_db_lock = threading.RLock()


def get_db_path() -> Path:
    """获取数据库路径，确保目录存在"""
    db_dir = DEFAULT_DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DB_PATH


@contextmanager
def get_connection():
    """获取数据库连接（上下文管理器，自动提交/关闭）"""
    db_path = get_db_path()
    with _db_lock:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_database():
    """初始化数据库：创建表 + 检查 schema 版本"""
    db_path = get_db_path()
    logger.info(f'Initializing database at {db_path}')

    with get_connection() as conn:
        # Schema 版本表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # 成员表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'guest',
                face_embedding BLOB,
                typical_distance_cm REAL,
                voice_embedding BLOB,
                labeled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_active_at TEXT NOT NULL DEFAULT (datetime('now')),
                appearance_count INTEGER NOT NULL DEFAULT 0,
                face_quality_score REAL DEFAULT 0,
                voice_quality_score REAL DEFAULT 0
            )
        """)

        # 未标识人物表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS unidentified (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                face_embedding BLOB,
                typical_distance_cm REAL,
                voice_embedding BLOB,
                appearance_count INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                face_quality_score REAL DEFAULT 0
            )
        """)

        # 技能偏好表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_preferences (
                member_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                preferences_json TEXT DEFAULT '{}',
                PRIMARY KEY (member_id, skill_name),
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # Phase 5: 自定义手势表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_gestures (
                id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                name TEXT NOT NULL,
                gesture_type TEXT NOT NULL DEFAULT 'custom',
                landmarks_template BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # Phase 5: 手势动作绑定表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gesture_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gesture_id TEXT NOT NULL,
                action TEXT NOT NULL,
                params_json TEXT DEFAULT '{}',
                member_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (gesture_id) REFERENCES custom_gestures(id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
            )
        """)

        # 自动清理日志表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cleanup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cleaned_at TEXT NOT NULL DEFAULT (datetime('now')),
                person_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                reason TEXT NOT NULL
            )
        """)

        # 检查并应用 schema 版本
        current = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        current_version = current['v'] if current and current['v'] else 0

        if current_version < 3:
            logger.info('Running schema migration to version 3...')
            # 角色迁移：adult→admin, child→member
            # 移除旧 CHECK 约束（重建 members 表）
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS members_new (
                        id TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'guest',
                        face_embedding BLOB,
                        typical_distance_cm REAL,
                        voice_embedding BLOB,
                        labeled INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        last_active_at TEXT NOT NULL DEFAULT (datetime('now')),
                        appearance_count INTEGER NOT NULL DEFAULT 0,
                        face_quality_score REAL DEFAULT 0,
                        voice_quality_score REAL DEFAULT 0,
                        face_thumbnail TEXT,
                        voiceprint_spectrum TEXT,
                        last_recognized_at TEXT,
                        recognition_confidence REAL DEFAULT 0
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO members_new SELECT id, display_name, CASE WHEN role='adult' THEN 'admin' WHEN role='child' THEN 'member' ELSE role END, face_embedding, typical_distance_cm, voice_embedding, labeled, created_at, last_active_at, appearance_count, face_quality_score, voice_quality_score, NULL, NULL, NULL, 0 FROM members")
                conn.execute("DROP TABLE members")
                conn.execute("ALTER TABLE members_new RENAME TO members")
            except Exception:
                pass
            conn.execute("UPDATE members SET role = 'admin' WHERE role = 'adult'")
            conn.execute("UPDATE members SET role = 'member' WHERE role = 'child'")
            # 新增角色 unregistered（如果 roles 表存在）
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO roles (name, display_name, level, description, permissions_json, skills_json, daily_limit_minutes, badge)
                    VALUES ('unregistered', '未登记', 0, '系统自动发现的未标识人物，无任何权限',
                        '{}', '[]', 0, '⬜')
                """)
            except Exception:
                pass
            # 更新 roles 表已有角色
            try:
                conn.execute("UPDATE roles SET display_name = '管理员' WHERE name = 'admin'")
                conn.execute("UPDATE roles SET display_name = '成员' WHERE name = 'member'")
            except Exception:
                pass
            # 新增字段：members 表
            for col, col_def in [
                ('face_thumbnail', 'TEXT'),
                ('voiceprint_spectrum', 'TEXT'),
                ('last_recognized_at', 'TEXT'),
                ('recognition_confidence', 'REAL DEFAULT 0'),
            ]:
                try:
                    conn.execute(f"ALTER TABLE members ADD COLUMN {col} {col_def}")
                except Exception:
                    pass
            # 新增字段：unidentified 表
            for col, col_def in [
                ('face_thumbnail', 'TEXT'),
                ('voiceprint_spectrum', 'TEXT'),
            ]:
                try:
                    conn.execute(f"ALTER TABLE unidentified ADD COLUMN {col} {col_def}")
                except Exception:
                    pass

        if current_version < 4:
            logger.info('Running schema migration to version 4 (command_history)...')
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS command_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_id TEXT NOT NULL,
                        type TEXT NOT NULL CHECK(type IN ('conversation', 'task')),
                        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                        summary TEXT NOT NULL DEFAULT '',
                        detail TEXT NOT NULL DEFAULT '',
                        FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cmd_history_member
                    ON command_history(member_id, timestamp)
                """)
            except Exception as e:
                logger.warning(f'Schema v4 migration partially failed: {e}')

        if current_version < 5:
            logger.info('Running schema migration to version 5 (face_gallery)...')
            # members 表新增 face_gallery 列
            try:
                conn.execute("ALTER TABLE members ADD COLUMN face_gallery TEXT")
            except Exception:
                pass  # 列可能已存在
            # unidentified 表也新增 face_gallery
            try:
                conn.execute("ALTER TABLE unidentified ADD COLUMN face_gallery TEXT")
            except Exception:
                pass
            # person_tracks 表（离线分析和调试）
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS person_tracks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        track_id INTEGER NOT NULL,
                        track_start REAL NOT NULL,
                        track_end REAL,
                        bound_member_id TEXT,
                        max_appearance_count INTEGER DEFAULT 0,
                        avg_face_score REAL DEFAULT 0.0
                    )
                """)
            except Exception:
                pass

        if current_version < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )
            logger.info(f'Database schema updated to version {SCHEMA_VERSION}')

    # 确保 faces 截图目录存在
    faces_dir = DEFAULT_DB_PATH.parent / 'faces'
    faces_dir.mkdir(parents=True, exist_ok=True)

    # 设置文件权限（仅当前用户读写）
    _secure_file(db_path)

    logger.info(f'Database initialized: {db_path} (schema v{SCHEMA_VERSION})')


def _secure_file(path: Path):
    """限制文件权限为当前用户读写"""
    try:
        if os.name == 'nt':  # Windows
            import subprocess
            subprocess.run(
                ['icacls', str(path), '/inheritance:r', '/grant:r',
                 f'{os.environ.get("USERNAME", "Everyone")}:(R,W)'],
                capture_output=True, check=False
            )
        else:  # Unix
            os.chmod(path, 0o600)
    except Exception as e:
        logger.warning(f'Failed to secure database file: {e}')


# ─── Embedding 序列化 ──────────────────────────────────────

def serialize_embedding(emb: np.ndarray) -> bytes:
    """numpy float32 数组 → bytes (BLOB)"""
    if emb is None:
        return None
    # L2 归一化
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb.astype(np.float32).tobytes()


def deserialize_embedding(data: bytes, dim: int) -> np.ndarray | None:
    """bytes (BLOB) → numpy float32 数组"""
    if data is None:
        return None
    emb = np.frombuffer(data, dtype=np.float32)
    if len(emb) != dim:
        logger.warning(f'Embedding dimension mismatch: expected {dim}, got {len(emb)}')
        return None
    return emb


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度（假设已 L2 归一化，等价于点积）"""
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))


# ─── 图库序列化 ─────────────────────────────────────────────

def serialize_gallery(embeddings: list) -> str | None:
    """人脸图库列表 → JSON 字符串（base64 编码每个 embedding）"""
    import base64
    import json
    if not embeddings:
        return None
    encoded = []
    for emb in embeddings:
        if emb is None:
            continue
        # L2 归一化
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        b64 = base64.b64encode(emb.astype(np.float32).tobytes()).decode('ascii')
        encoded.append(b64)
    return json.dumps(encoded) if encoded else None


def deserialize_gallery(gallery_json: str, dim: int = 512) -> list:
    """JSON 字符串 → 人脸图库列表"""
    import base64
    import json
    if not gallery_json:
        return []
    try:
        encoded = json.loads(gallery_json)
    except (json.JSONDecodeError, TypeError):
        return []
    embeddings = []
    for b64 in encoded:
        try:
            data = base64.b64decode(b64)
            emb = np.frombuffer(data, dtype=np.float32)
            if len(emb) == dim:
                embeddings.append(emb)
            else:
                logger.warning(f'Gallery embedding dim mismatch: expected {dim}, got {len(emb)}')
        except Exception as e:
            logger.warning(f'Gallery deserialize error: {e}')
    return embeddings


def search_by_face_gallery(query_emb: np.ndarray, top_n: int = 3,
                           threshold: float = 0.5) -> list[tuple[dict, float]]:
    """max-pooling 图库匹配：对每个 member 的所有 gallery embedding 取最高相似度"""
    if query_emb is None:
        return []

    query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE labeled = 1 AND (face_embedding IS NOT NULL OR face_gallery IS NOT NULL)"
        ).fetchall()

    results = []
    for row in rows:
        best_score = 0.0
        gallery = deserialize_gallery(row['face_gallery']) if row['face_gallery'] else []
        # 如果无图库，回退到旧版单 embedding
        if not gallery and row['face_embedding']:
            stored = deserialize_embedding(row['face_embedding'], 512)
            if stored is not None:
                best_score = cosine_similarity(query_emb, stored)
        else:
            for gallery_emb in gallery:
                score = cosine_similarity(query_emb, gallery_emb)
                if score > best_score:
                    best_score = score

        if best_score >= threshold:
            results.append((_row_to_dict(row), best_score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


def update_face_gallery(member_id: str, embeddings: list):
    """更新成员的 face_gallery"""
    gallery_json = serialize_gallery(embeddings)
    with get_connection() as conn:
        conn.execute(
            "UPDATE members SET face_gallery = ? WHERE id = ?",
            (gallery_json, member_id)
        )
    logger.debug(f'Face gallery updated for member {member_id[:8]}... ({len(embeddings)} embeddings)')


def append_to_face_gallery(member_id: str, embedding: np.ndarray, max_samples: int = 10):
    """向图库追加一个 embedding（增量扩展）"""
    with get_connection() as conn:
        row = conn.execute("SELECT face_gallery FROM members WHERE id = ?", (member_id,)).fetchone()
    if not row:
        return

    gallery = deserialize_gallery(row['face_gallery']) if row['face_gallery'] else []
    # 检查与已有样本的最小距离
    min_dist = min(
        (1.0 - cosine_similarity(embedding, g) for g in gallery),
        default=1.0
    )
    if min_dist > 0.2:  # 足够新颖才加入
        gallery.append(embedding)
        # 超过上限时移除离群点
        if len(gallery) > max_samples:
            mean_emb = np.mean(gallery, axis=0)
            mean_emb = mean_emb / (np.linalg.norm(mean_emb) or 1.0)
            distances = [1.0 - cosine_similarity(g, mean_emb) for g in gallery]
            worst_idx = distances.index(max(distances))
            gallery.pop(worst_idx)
        update_face_gallery(member_id, gallery)
        logger.debug(f'Appended to face gallery for {member_id[:8]}... (total: {len(gallery)})')


def audit_face_gallery(member_id: str, min_quality: float = 0.6):
    """质量审计：移除低质量样本（按与图库均值的距离判断）"""
    with get_connection() as conn:
        row = conn.execute("SELECT face_gallery FROM members WHERE id = ?", (member_id,)).fetchone()
    if not row or not row['face_gallery']:
        return

    gallery = deserialize_gallery(row['face_gallery'])
    if len(gallery) <= 2:
        return  # 样本太少不审计

    mean_emb = np.mean(gallery, axis=0)
    mean_emb = mean_emb / (np.linalg.norm(mean_emb) or 1.0)

    # 计算每个样本与均值的距离，移除最差的 20%
    distances = [1.0 - cosine_similarity(g, mean_emb) for g in gallery]
    threshold_pct = np.percentile(distances, 80)
    pruned = [g for g, d in zip(gallery, distances) if d <= threshold_pct]

    if len(pruned) < len(gallery):
        update_face_gallery(member_id, pruned)
        logger.info(f'Face gallery audited for {member_id[:8]}...: {len(gallery)} -> {len(pruned)}')


# ─── 成员 CRUD ─────────────────────────────────────────────

def add_member(display_name: str, role: str = 'guest',
               face_emb: np.ndarray = None, voice_emb: np.ndarray = None,
               typical_distance: float = None, labeled: bool = True) -> str:
    """添加成员，返回 member_id"""
    import uuid
    member_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO members (id, display_name, role, face_embedding,
                   typical_distance_cm, voice_embedding, labeled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            member_id, display_name, role,
            serialize_embedding(face_emb),
            typical_distance,
            serialize_embedding(voice_emb),
            1 if labeled else 0
        ))

    logger.info(f'Member added: {display_name} (role={role}, id={member_id[:8]}...)')
    return member_id


def get_member(member_id: str) -> dict | None:
    """获取单个成员"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    return _row_to_dict(row) if row else None


def update_member(member_id: str, **kwargs):
    """更新成员字段"""
    allowed = {'display_name', 'role', 'face_embedding', 'typical_distance_cm',
               'voice_embedding', 'last_active_at', 'appearance_count',
               'face_quality_score', 'voice_quality_score', 'labeled'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return

    # 序列化 embedding 字段
    if 'face_embedding' in updates:
        updates['face_embedding'] = serialize_embedding(updates['face_embedding'])
    if 'voice_embedding' in updates:
        updates['voice_embedding'] = serialize_embedding(updates['voice_embedding'])

    set_clause = ', '.join(f'{k} = ?' for k in updates)
    values = list(updates.values()) + [member_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE members SET {set_clause} WHERE id = ?",
            values
        )

    logger.debug(f'Member updated: {member_id[:8]}... fields={list(updates.keys())}')


def delete_member(member_id: str):
    """删除成员（级联删除 skill_preferences）"""
    with get_connection() as conn:
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    logger.info(f'Member deleted: {member_id[:8]}...')


def list_all_members() -> list[dict]:
    """列出所有已标识成员（JSON 安全：排除 BLOB 列）"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE labeled = 1 ORDER BY role, display_name"
        ).fetchall()
    return [_row_to_json_dict(r) for r in rows]


def get_member_by_id(member_id: str) -> dict | None:
    """按 ID 查询单成员（JSON 安全：排除 BLOB 列）"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM members WHERE id = ?", (member_id,)
        ).fetchone()
    if row is None:
        return None
    return _row_to_json_dict(row)


def get_member_history(member_id: str, max_age_days: int | None = None) -> list[dict]:
    """查询成员的指令历史记录

    Args:
        member_id: 成员 ID
        max_age_days: 最大保留天数，None 表示无限期
    """
    with get_connection() as conn:
        if max_age_days is not None:
            rows = conn.execute(
                """SELECT id, member_id, type, timestamp, summary, detail
                   FROM command_history
                   WHERE member_id = ?
                     AND timestamp >= datetime('now', ?)
                   ORDER BY timestamp DESC""",
                (member_id, f'-{max_age_days} days')
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, member_id, type, timestamp, summary, detail
                   FROM command_history
                   WHERE member_id = ?
                   ORDER BY timestamp DESC""",
                (member_id,)
            ).fetchall()
    return [dict(r) for r in rows]


def insert_command_history(member_id: str, cmd_type: str, summary: str, detail: str = ''):
    """写入一条指令历史记录"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO command_history (member_id, type, summary, detail)
               VALUES (?, ?, ?, ?)""",
            (member_id, cmd_type, summary, detail)
        )


def get_member_stats() -> dict:
    """获取成员统计信息"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(appearance_count), 0) as total_visits FROM members WHERE labeled = 1"
        ).fetchone()
    return {
        'members_count': row['c'] if row else 0,
        'total_visits': row['total_visits'] if row else 0,
    }


def list_unidentified() -> list[dict]:
    """列出所有未标识人物（JSON 安全：排除 BLOB 列）"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM unidentified ORDER BY last_seen_at DESC"
        ).fetchall()
    return [_row_to_json_dict(r) for r in rows]


# ─── 相似度搜索 ────────────────────────────────────────────

def search_by_face_embedding(query_emb: np.ndarray, top_n: int = 3,
                              threshold: float = 0.5) -> list[tuple[dict, float]]:
    """按人脸 embedding 相似度搜索，返回 [(member_dict, score), ...]"""
    if query_emb is None:
        return []

    query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)

    # 搜索已标识成员
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE face_embedding IS NOT NULL AND labeled = 1"
        ).fetchall()

    results = []
    for row in rows:
        stored_emb = deserialize_embedding(row['face_embedding'], 512)
        if stored_emb is not None:
            score = cosine_similarity(query_emb, stored_emb)
            if score >= threshold:
                results.append((_row_to_dict(row), score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


def search_by_voice_embedding(query_emb: np.ndarray, top_n: int = 3,
                               threshold: float = 0.5) -> list[tuple[dict, float]]:
    """按声纹 embedding 相似度搜索"""
    if query_emb is None:
        return []

    query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM members WHERE voice_embedding IS NOT NULL AND labeled = 1"
        ).fetchall()

    results = []
    for row in rows:
        stored_emb = deserialize_embedding(row['voice_embedding'], 192)
        if stored_emb is not None:
            score = cosine_similarity(query_emb, stored_emb)
            if score >= threshold:
                results.append((_row_to_dict(row), score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_n]


def search_unidentified_by_face(query_emb: np.ndarray, threshold: float = 0.6) -> list[tuple[dict, float]]:
    """在未标识人物中搜索匹配的人脸"""
    if query_emb is None:
        return []

    query_emb = query_emb / (np.linalg.norm(query_emb) or 1.0)

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM unidentified WHERE face_embedding IS NOT NULL"
        ).fetchall()

    results = []
    for row in rows:
        stored_emb = deserialize_embedding(row['face_embedding'], 512)
        if stored_emb is not None:
            score = cosine_similarity(query_emb, stored_emb)
            if score >= threshold:
                results.append((_row_to_dict(row), score))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ─── Embedding 更新 ────────────────────────────────────────

def update_embeddings(member_id: str, new_face_emb: np.ndarray | None = None,
                       new_voice_emb: np.ndarray | None = None,
                       weight_old: float = 0.7):
    """自适应 embedding 更新：加权平均 0.7×旧 + 0.3×新"""
    member = get_member(member_id)
    if not member:
        logger.warning(f'update_embeddings: member {member_id} not found')
        return

    updates = {}

    if new_face_emb is not None:
        old_emb = deserialize_embedding(member.get('face_embedding'), 512)
        if old_emb is not None:
            new_emb = new_face_emb / (np.linalg.norm(new_face_emb) or 1.0)
            blended = weight_old * old_emb + (1 - weight_old) * new_emb
            updates['face_embedding'] = blended / (np.linalg.norm(blended) or 1.0)
        else:
            updates['face_embedding'] = new_face_emb

    if new_voice_emb is not None:
        old_emb = deserialize_embedding(member.get('voice_embedding'), 192)
        if old_emb is not None:
            new_emb = new_voice_emb / (np.linalg.norm(new_voice_emb) or 1.0)
            blended = weight_old * old_emb + (1 - weight_old) * new_emb
            updates['voice_embedding'] = blended / (np.linalg.norm(blended) or 1.0)
        else:
            updates['voice_embedding'] = new_voice_emb

    if updates:
        update_member(member_id, **updates, last_active_at=datetime.now(timezone.utc).isoformat())
        logger.debug(f'Embeddings updated for {member_id[:8]}...')


# ─── 未标识人物管理 ────────────────────────────────────────

def add_unidentified(display_name: str, face_emb: np.ndarray = None,
                      voice_emb: np.ndarray = None, typical_distance: float = None) -> str:
    """添加未标识人物"""
    import uuid
    person_id = str(uuid.uuid4())

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO unidentified (id, display_name, face_embedding,
                   typical_distance_cm, voice_embedding, appearance_count,
                   first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))
        """, (
            person_id, display_name,
            serialize_embedding(face_emb),
            typical_distance,
            serialize_embedding(voice_emb),
        ))

    logger.info(f'Unidentified person added: {display_name}')
    return person_id


def update_unidentified(person_id: str, face_emb: np.ndarray = None,
                         voice_emb: np.ndarray = None):
    """更新未标识人物的特征和计数"""
    updates = {
        'last_seen_at': datetime.now(timezone.utc).isoformat(),
        'appearance_count': '(SELECT appearance_count + 1 FROM unidentified WHERE id = ?)',
    }

    with get_connection() as conn:
        if face_emb is not None:
            # 加权平均更新
            row = conn.execute(
                "SELECT face_embedding FROM unidentified WHERE id = ?", (person_id,)
            ).fetchone()
            if row and row['face_embedding']:
                old = deserialize_embedding(row['face_embedding'], 512)
                if old is not None:
                    new_emb = face_emb / (np.linalg.norm(face_emb) or 1.0)
                    blended = 0.6 * old + 0.4 * new_emb
                    face_emb = blended / (np.linalg.norm(blended) or 1.0)
            conn.execute(
                "UPDATE unidentified SET face_embedding = ?, last_seen_at = datetime('now') WHERE id = ?",
                (serialize_embedding(face_emb), person_id)
            )

        # 增加出现计数
        conn.execute(
            "UPDATE unidentified SET appearance_count = appearance_count + 1, last_seen_at = datetime('now') WHERE id = ?",
            (person_id,)
        )


def get_next_visitor_name() -> str:
    """获取下一个访客序列名"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT display_name FROM unidentified ORDER BY display_name DESC LIMIT 1"
        ).fetchone()

    if row and row['display_name']:
        try:
            num = int(row['display_name'].split('-')[1])
            return f'访客-{num + 1:03d}'
        except (IndexError, ValueError):
            pass
    return '访客-001'


def cleanup_unidentified(days_threshold: int = 30, min_appearances: int = 5):
    """清理长期未出现的未标识人物"""
    with get_connection() as conn:
        # 查询待清理的
        rows = conn.execute("""
            SELECT * FROM unidentified
            WHERE appearance_count < ?
              AND last_seen_at < datetime('now', ?)
        """, (min_appearances, f'-{days_threshold} days')).fetchall()

        if not rows:
            logger.debug('No unidentified persons to clean up')
            return []

        cleaned = []
        for row in rows:
            d = _row_to_dict(row)
            conn.execute("DELETE FROM unidentified WHERE id = ?", (d['id'],))
            conn.execute("""
                INSERT INTO cleanup_log (person_id, display_name, reason)
                VALUES (?, ?, ?)
            """, (d['id'], d['display_name'],
                  f'超过{days_threshold}天未出现（共{d["appearance_count"]}次）'))
            cleaned.append(d)

        logger.info(f'Cleaned up {len(cleaned)} unidentified persons')
        return cleaned


def convert_to_member(unidentified_id: str, display_name: str, role: str = 'guest') -> str:
    """将未标识人物转换为已标识成员（转移所有关联数据）

    注意：所有操作在单一连接+事务内完成，确保原子性。
    不使用 add_member() 以避免嵌套 get_connection() 导致 _db_lock 死锁。
    """
    import uuid

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM unidentified WHERE id = ?", (unidentified_id,)
        ).fetchone()

        if not row:
            raise ValueError(f'Unidentified person {unidentified_id} not found')

        # 内联创建成员（使用当前连接，避免嵌套锁）
        member_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO members (id, display_name, role, face_embedding,
                   typical_distance_cm, voice_embedding, labeled)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (
            member_id, display_name, role,
            row['face_embedding'],  # 直接使用原始 BLOB，无需反序列化再序列化
            row['typical_distance_cm'],
            row['voice_embedding'],
        ))

        # 转移附加数据：缩略图、声纹频谱、出现统计、时间戳
        columns = [c[1] for c in conn.execute("PRAGMA table_info(unidentified)").fetchall()]
        updates = []
        params = []
        if 'face_thumbnail' in columns and row['face_thumbnail']:
            updates.append("face_thumbnail = ?")
            params.append(row['face_thumbnail'])
        if 'voiceprint_spectrum' in columns and row['voiceprint_spectrum']:
            updates.append("voiceprint_spectrum = ?")
            params.append(row['voiceprint_spectrum'])
        updates.append("appearance_count = ?")
        params.append(row['appearance_count'] or 0)
        updates.append("created_at = ?")
        params.append(row['first_seen_at'])
        updates.append("last_active_at = ?")
        params.append(row['last_seen_at'])
        params.append(member_id)
        conn.execute(
            f"UPDATE members SET {', '.join(updates)} WHERE id = ?",
            params,
        )

        # 删除未标识记录
        conn.execute("DELETE FROM unidentified WHERE id = ?", (unidentified_id,))

        logger.info(f'Converted {unidentified_id[:8]}... → member {display_name} ({member_id[:8]}...)')
        return member_id


# ─── 工具 ──────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    """将 sqlite3.Row 转为 dict"""
    d = dict(row)
    # 不反序列化 embedding（按需调用 deserialize_embedding）
    return d


def _row_to_json_dict(row: sqlite3.Row) -> dict:
    """将 sqlite3.Row 转为 JSON 可序列化的 dict（排除 bytes/BLOB 列）"""
    d = {}
    for key in row.keys():
        val = row[key]
        if isinstance(val, bytes):
            continue  # 排除 face_embedding / voice_embedding 等 BLOB 列
        d[key] = val
    return d


def get_database_stats() -> dict:
    """获取数据库统计信息"""
    with get_connection() as conn:
        members = conn.execute("SELECT COUNT(*) as c FROM members WHERE labeled = 1").fetchone()
        unid = conn.execute("SELECT COUNT(*) as c FROM unidentified").fetchone()
        owner = conn.execute("SELECT COUNT(*) as c FROM members WHERE role = 'owner' AND labeled = 1").fetchone()

    return {
        'members_count': members['c'] if members else 0,
        'unidentified_count': unid['c'] if unid else 0,
        'has_owner': (owner['c'] if owner else 0) > 0,
        'db_path': str(get_db_path()),
        'schema_version': SCHEMA_VERSION,
    }
