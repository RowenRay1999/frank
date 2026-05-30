"""
Frank (弗兰克) — Python 推理服务入口

负责：
1. 启动 asyncio WebSocket 服务器
2. 初始化摄像头、音频、状态机模块
3. 处理来自 Electron 的指令消息
4. 推送检测事件到 Electron

Phase 3: 对话智能 — STT + LLM + TTS + 免唤醒指令 + 视觉意图
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import websockets
from websockets.asyncio.server import serve

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.python.shared.config import get_config
from src.python.shared.message import Message, ErrorMessage
from src.python.shared.database import init_database
from src.python.modules.state.state_machine import StateMachine
from src.python.modules.camera.camera_pipeline import CameraPipeline
from src.python.modules.audio.audio_pipeline import AudioPipeline
from src.python.modules.fusion.identity_fusion import IdentityFusionEngine
from src.python.modules.role.role_manager import RoleManager
from src.python.modules.members.member_manager import MemberManager
# Phase 3 modules
from src.python.modules.stt.speech_to_text import SpeechToText
from src.python.modules.llm.llm_provider import LLMManager
from src.python.modules.tts.text_to_speech import TextToSpeech
from src.python.modules.wakefree.wakefree_commands import WakeFreeManager
from src.python.modules.visual_intent.visual_intent import VisualIntentDetector
from src.python.server.conversation import ConversationOrchestrator, ChatSubState
# Phase 4 modules
from src.python.modules.multi_person.multi_person import MultiPersonManager
from src.python.modules.task_manager.task_manager import TaskManager
from src.python.modules.skill_loader.skill_loader import SkillLoader
# Phase 5 modules
from src.python.modules.pose.pose_module import PoseModule, GestureEvent

# ─── 日志配置 ───────────────────────────────────────────────
config = get_config()
log_config = config.get('logging', {})
logging.basicConfig(
    level=getattr(logging, log_config.get('level', 'INFO')),
    format=log_config.get('format', '%(asctime)s [%(levelname)s] %(name)s: %(message)s'),
    handlers=[
        logging.FileHandler(log_config.get('file', 'logs/frank.log')),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger('frank.server')

# ─── 全局模块实例 ──────────────────────────────────────────
state_machine: StateMachine | None = None
camera_pipeline: CameraPipeline | None = None
audio_pipeline: AudioPipeline | None = None
fusion_engine: IdentityFusionEngine | None = None
role_manager: RoleManager | None = None
member_manager: MemberManager | None = None
# Phase 3
stt_module: SpeechToText | None = None
llm_manager: LLMManager | None = None
tts_module: TextToSpeech | None = None
wakefree_manager: WakeFreeManager | None = None
visual_detector: VisualIntentDetector | None = None
conversation: ConversationOrchestrator | None = None
# Phase 4
multi_person: MultiPersonManager | None = None
task_manager: TaskManager | None = None
skill_loader: SkillLoader | None = None
# Phase 5
pose_module: PoseModule | None = None
connected_clients: set = set()


# ─── 消息处理 ───────────────────────────────────────────────
def generate_msg_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def send_message(websocket, msg_type: str, payload: dict | None = None, in_reply_to: str | None = None):
    """发送 JSON 消息到 Electron"""
    msg = {
        'type': msg_type,
        'id': generate_msg_id(),
        'timestamp': now_iso(),
        'payload': payload or {},
    }
    if in_reply_to:
        msg['in_reply_to'] = in_reply_to
    await websocket.send(json.dumps(msg, ensure_ascii=False))


async def send_error(websocket, code: str, message: str, recoverable: bool = True, suggestion: str = '', in_reply_to: str | None = None):
    """发送错误消息"""
    payload = {
        'code': code,
        'message': message,
        'recoverable': recoverable,
        'suggestion': suggestion,
    }
    await send_message(websocket, 'error', payload, in_reply_to)


async def handle_message(websocket, raw_msg: str):
    """根据消息 type 字段分发到对应处理器"""
    try:
        data = json.loads(raw_msg)
    except json.JSONDecodeError:
        await send_error(websocket, 'INVALID_JSON', '消息格式无效，需要 JSON', False, '请检查消息格式')
        return

    msg_type = data.get('type', '')
    msg_id = data.get('id', '')
    payload = data.get('payload', {})

    logger.debug(f'Received: {msg_type} (id={msg_id})')

    try:
        match msg_type:
            # ── 状态机 ──
            case 'state.get':
                if state_machine:
                    info = state_machine.get_current_state()
                    await send_message(websocket, 'state.current', info, msg_id)
                else:
                    await send_error(websocket, 'STATE_NOT_INIT', '状态机未初始化', True, '请等待服务完全启动', msg_id)

            case 'state.transition':
                if state_machine:
                    result = state_machine.transition(payload.get('to'), payload.get('trigger', 'manual'))
                    await send_message(websocket, 'state.changed', result, msg_id)
                else:
                    await send_error(websocket, 'STATE_NOT_INIT', '状态机未初始化', True, '', msg_id)

            # ── 摄像头 ──
            case 'camera.start':
                if camera_pipeline:
                    result = await camera_pipeline.start(payload)
                    await send_message(websocket, 'camera.started', result, msg_id)
                else:
                    await send_error(websocket, 'CAM_NOT_INIT', '摄像头模块未初始化', True, '', msg_id)

            case 'camera.stop':
                if camera_pipeline:
                    await camera_pipeline.stop()
                    await send_message(websocket, 'camera.stopped', {}, msg_id)
                else:
                    await send_error(websocket, 'CAM_NOT_INIT', '摄像头模块未初始化', True, '', msg_id)

            case 'camera.configure':
                if camera_pipeline:
                    result = await camera_pipeline.configure(payload)
                    await send_message(websocket, 'camera.configured', result, msg_id)
                else:
                    await send_error(websocket, 'CAM_NOT_INIT', '摄像头模块未初始化', True, '', msg_id)

            # ── 麦克风 ──
            case 'mic.start':
                if audio_pipeline:
                    result = await audio_pipeline.start(payload)
                    await send_message(websocket, 'mic.started', result, msg_id)
                else:
                    await send_error(websocket, 'MIC_NOT_INIT', '麦克风模块未初始化', True, '', msg_id)

            case 'mic.stop':
                if audio_pipeline:
                    await audio_pipeline.stop()
                    await send_message(websocket, 'mic.stopped', {}, msg_id)
                else:
                    await send_error(websocket, 'MIC_NOT_INIT', '麦克风模块未初始化', True, '', msg_id)

            case 'mic.configure':
                if audio_pipeline:
                    result = await audio_pipeline.configure(payload)
                    await send_message(websocket, 'mic.configured', result, msg_id)
                else:
                    await send_error(websocket, 'MIC_NOT_INIT', '麦克风模块未初始化', True, '', msg_id)

            # ── 成员管理 (Phase 2) ──
            case 'member.list':
                members = member_manager.list_members() if member_manager else []
                await send_message(websocket, 'member.list', {'members': members}, msg_id)

            case 'member.pending':
                pending = member_manager.list_pending() if member_manager else []
                await send_message(websocket, 'member.pending', {'pending': pending}, msg_id)

            case 'member.register_start':
                if member_manager:
                    sid = member_manager.start_registration()
                    await send_message(websocket, 'member.register_started', {'session_id': sid}, msg_id)
                else:
                    await send_error(websocket, 'MEM_NOT_INIT', '成员模块未初始化', True, '', msg_id)

            case 'member.register_info':
                if member_manager:
                    result = member_manager.set_registration_info(
                        payload.get('display_name', ''), payload.get('role', 'guest'))
                    await send_message(websocket, 'member.register_info_ok', result, msg_id)
                else:
                    await send_error(websocket, 'MEM_NOT_INIT', '成员模块未初始化', True, '', msg_id)

            case 'member.register_cancel':
                if member_manager:
                    member_manager.cancel_registration()
                await send_message(websocket, 'member.register_cancelled', {}, msg_id)

            case 'member.identify':
                if member_manager:
                    result = member_manager.identify_person(
                        payload['unidentified_id'], payload['display_name'],
                        payload.get('role', 'guest'), payload.get('merge_to'))
                    await send_message(websocket, 'member.identified', result, msg_id)
                else:
                    await send_error(websocket, 'MEM_NOT_INIT', '成员模块未初始化', True, '', msg_id)

            case 'member.delete':
                if member_manager and payload.get('member_id'):
                    member_manager.remove_member(payload['member_id'])
                    await send_message(websocket, 'member.deleted', {}, msg_id)
                else:
                    await send_error(websocket, 'MEM_NOT_INIT', '成员模块未初始化', True, '', msg_id)

            # ── 身份查询 (Phase 2) ──
            case 'identity.get':
                identity = fusion_engine.get_current_identity() if fusion_engine else {}
                await send_message(websocket, 'identity.current', identity, msg_id)

            case 'identity.reset':
                if fusion_engine:
                    fusion_engine.reset_identity()
                await send_message(websocket, 'identity.reset_ok', {}, msg_id)

            # ── Phase 4: 任务管理 ──
            case 'task.list':
                tasks = task_manager.list_user_tasks(payload.get('user_id', '')) if task_manager else []
                await send_message(websocket, 'task.list', {'tasks': tasks}, msg_id)

            case 'task.list_all':
                tasks = task_manager.list_all_tasks() if task_manager else []
                await send_message(websocket, 'task.list_all', {'tasks': tasks}, msg_id)

            case 'task.get':
                t = task_manager.query_task(payload.get('task_id', '')) if task_manager else None
                await send_message(websocket, 'task.get', t or {}, msg_id)

            # ── Phase 4: 技能管理 ──
            case 'skill.list':
                skills = skill_loader.list_skills() if skill_loader else []
                await send_message(websocket, 'skill.list', {'skills': skills}, msg_id)

            case 'skill.execute':
                if skill_loader:
                    result = await skill_loader.execute_skill(
                        payload.get('skill_name', ''),
                        payload.get('params', {}),
                    )
                    await send_message(websocket, 'skill.result', result, msg_id)

            # ── Phase 4: 多人模式 ──
            case 'multi_person.status':
                status = multi_person.get_status() if multi_person else {}
                await send_message(websocket, 'multi_person.status', status, msg_id)

            # ── Phase 5: 手势管理 ──
            case 'gesture.register':
                if pose_module and payload.get('name') and payload.get('frames'):
                    from src.python.modules.pose.pose_module import PoseFrame
                    frames = [PoseFrame(
                        body_landmarks=__import__('numpy').array(f.get('body', []), dtype=__import__('numpy').float32) if f.get('body') else None,
                        frame_timestamp=f.get('t', 0)
                    ) for f in payload['frames']]
                    try:
                        gid = pose_module.register_custom_gesture(
                            payload['name'], frames,
                            payload.get('member_id', '')
                        )
                        await send_message(websocket, 'gesture.registered', {'gesture_id': gid}, msg_id)
                    except Exception as e:
                        await send_error(websocket, 'GESTURE_REG_FAILED', str(e), True, '', msg_id)

            case 'gesture.bind':
                if payload.get('gesture_id') and payload.get('action'):
                    pose_module.bind_custom_action(
                        payload['gesture_id'], payload['action'],
                        payload.get('params', {}),
                        payload.get('member_id', '')
                    )
                    await send_message(websocket, 'gesture.bound', {}, msg_id)

            case 'gesture.unbind':
                if payload.get('gesture_id'):
                    pose_module.unbind_custom_action(payload['gesture_id'])
                    await send_message(websocket, 'gesture.unbound', {}, msg_id)

            case 'gesture.list_bindings':
                bindings = pose_module.list_bindings() if pose_module else []
                await send_message(websocket, 'gesture.bindings_list', {'bindings': bindings}, msg_id)

            case 'gesture.list_custom':
                gestures = pose_module.list_custom_gestures() if pose_module else []
                await send_message(websocket, 'gesture.custom_list', {'gestures': gestures}, msg_id)

            case 'gesture.delete':
                if pose_module and payload.get('gesture_id'):
                    pose_module.delete_custom_gesture(payload['gesture_id'])
                    await send_message(websocket, 'gesture.deleted', {}, msg_id)

            # ── 心跳 ──
            case 'ping':
                await send_message(websocket, 'pong', {}, msg_id)

            # ── 未知 ──
            case _:
                await send_error(websocket, 'UNKNOWN_TYPE', f'未知消息类型: {msg_type}', True, f'支持的类型: state.*, camera.*, mic.*, ping', msg_id)

    except Exception as e:
        logger.exception(f'Error handling message {msg_type}')
        await send_error(websocket, 'INTERNAL_ERROR', str(e), True, '服务内部错误，请稍后重试', msg_id)


# ─── WebSocket 连接处理 ─────────────────────────────────────
async def ws_handler(websocket):
    """处理每个 WebSocket 连接"""
    client_id = str(uuid.uuid4())[:8]
    connected_clients.add(websocket)
    logger.info(f'Client connected: {client_id} (total: {len(connected_clients)})')

    # 发送就绪信号
    await send_message(websocket, 'server.ready', {
        'version': '0.2.0',
        'capabilities': ['camera', 'audio', 'state_machine', 'identity', 'members', 'roles'],
        'state': state_machine.get_current_state() if state_machine else None,
    })

    try:
        async for raw_msg in websocket:
            await handle_message(websocket, raw_msg)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f'Client disconnected: {client_id}')
    finally:
        connected_clients.discard(websocket)


async def broadcast_event(msg_type: str, payload: dict):
    """向所有连接的 Electron 客户端广播事件"""
    for ws in list(connected_clients):
        try:
            await send_message(ws, msg_type, payload)
        except Exception as e:
            logger.debug(f'Broadcast to client failed: {e}')


# ─── 事件回调（供模块使用）──────────────────────────────────
async def on_face_detected(payload: dict):
    if state_machine:
        state_machine.on_event('face_detected', payload)
    # Phase 4: update multi-person tracking
    if multi_person:
        faces = payload.get('faces', [])
        for face in faces:
            if face.get('embedding'):
                import hashlib
                emb_bytes = np.array(face['embedding'], dtype=np.float32).tobytes()
                pid = hashlib.md5(emb_bytes).hexdigest()[:12]
                multi_person.update_person(pid, face_embedding=face['embedding'])
    await broadcast_event('camera.face_detected', payload)


async def on_face_lost(payload: dict):
    if state_machine:
        state_machine.on_event('face_lost', payload)
    await broadcast_event('camera.face_lost', payload)


async def on_voice_start(payload: dict):
    if state_machine:
        state_machine.on_event('voice_start', payload)
    await broadcast_event('mic.voice_start', payload)


async def on_voice_end(payload: dict):
    await broadcast_event('mic.voice_end', payload)


async def on_wake_word(payload: dict):
    if state_machine:
        state_machine.on_event('wake_word', payload)
    await broadcast_event('mic.wake_word', payload)


async def on_state_changed(transition_info: dict):
    await broadcast_event('state.changed', transition_info)


async def on_camera_error(error_info: dict):
    await broadcast_event('camera.error', error_info)


async def on_face_embedding(embedding: np.ndarray, confidence: float):
    """Phase 2: 人脸 embedding → 融合引擎"""
    if fusion_engine:
        fusion_engine.submit_face_evidence(embedding, confidence)


async def on_voiceprint(embedding: np.ndarray, duration: float):
    """Phase 2: 声纹 embedding → 融合引擎"""
    if fusion_engine:
        fusion_engine.submit_voice_evidence(embedding, 1.0)


async def on_identity_confirmed(identity: dict):
    """融合引擎确认身份 → 状态机 + 角色管理"""
    logger.info(f'Identity confirmed: {identity.get("display_name")} (role={identity.get("role")})')
    if state_machine:
        state_machine.set_identity(identity)
        state_machine.on_event('identity_confirmed', identity)
    if role_manager and identity.get('member_id'):
        role_manager.create_session(
            identity['member_id'],
            identity.get('display_name', 'Unknown'),
            identity.get('role', 'guest'),
        )
    await broadcast_event('identity.confirmed', identity)


async def on_identity_changing(change_info: dict):
    await broadcast_event('identity.changing', change_info)


async def on_identity_unknown(info: dict):
    await broadcast_event('identity.unknown', info)


# ─── Phase 3 回调 ────────────────────────────────────────

async def on_stt_trigger(audio_data):
    """音频管线触发 STT"""
    if conversation:
        await conversation.process_speech(audio_data)
    await broadcast_event('chat.listening', {})


async def on_chat_sub_state_change(sub_state_info: dict):
    await broadcast_event('chat.sub_state', sub_state_info)


async def on_user_message(msg: dict):
    await broadcast_event('chat.user_message', msg)


async def on_assistant_message(msg: dict):
    await broadcast_event('chat.assistant_message', msg)


# ─── Phase 4 回调 ────────────────────────────────────────

async def on_multi_state_change(state_info: dict):
    await broadcast_event('multi_person.state', state_info)


async def on_person_join(person_info: dict):
    await broadcast_event('multi_person.join', person_info)


async def on_person_leave(person_info: dict):
    await broadcast_event('multi_person.leave', person_info)


async def on_mic_error(error_info: dict):
    await broadcast_event('mic.error', error_info)


# ─── Phase 5 回调 ────────────────────────────────────────

async def on_pose_frame(frame_rgb, frame_w: int, frame_h: int):
    """CameraPipeline 姿态帧回调 → PoseModule 处理
    PoseModule internal _dispatch_gesture already routes to on_gesture_detected via action slots.
    """
    if pose_module:
        pose_module.process_frame(frame_rgb, frame_w, frame_h)


async def on_gesture_detected(event: GestureEvent):
    """手势识别事件广播到 Electron + 状态机"""
    payload = {
        'gesture_type': event.gesture_type,
        'confidence': event.confidence,
        'gesture_id': event.gesture_id,
        'direction': event.direction,
        'timestamp': now_iso(),
    }

    # 广播到 Electron
    await broadcast_event('gesture.detected', payload)

    # 连接状态机
    if state_machine:
        if event.gesture_type == 'come_closer' and event.confidence >= 0.7:
            state_machine.on_event('gesture_detected', {
                'gesture_type': event.gesture_type,
                'confidence': event.confidence,
            })
        elif event.gesture_type == 'raise_hand' and event.confidence >= 0.7:
            # 举手 → 暂停/恢复对话
            current = state_machine.get_current_state()
            if current.get('state') == 'Chat':
                state_machine.on_event('gesture_detected', {
                    'gesture_type': event.gesture_type,
                    'action': 'toggle_pause',
                })

    logger.debug(f'Gesture detected: {event.gesture_type} (confidence={event.confidence:.2f})')


# ─── 主函数 ─────────────────────────────────────────────────
def find_available_port(start_port: int, max_retries: int = 15) -> int:
    """查找可用端口，冲突时自动递增"""
    import socket
    for offset in range(max_retries + 1):
        port = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                logger.warning(f'Port {port} is in use, trying {port + 1}...')
    raise RuntimeError(f'No available port in range {start_port}-{start_port + max_retries}')


async def main():
    global state_machine, camera_pipeline, audio_pipeline
    global fusion_engine, role_manager, member_manager
    global stt_module, llm_manager, tts_module, wakefree_manager, visual_detector, conversation
    global multi_person, task_manager, skill_loader
    global pose_module

    logger.info('=== Frank Inference Service Starting (Phase 5) ===')

    # 初始化数据库
    logger.info('Initializing database...')
    init_database()

    # 初始化角色和成员管理
    role_manager = RoleManager()
    member_manager = MemberManager()

    # 初始化融合引擎
    fusion_engine = IdentityFusionEngine()
    fusion_engine.set_on_identity_confirmed(on_identity_confirmed)
    fusion_engine.set_on_identity_changing(on_identity_changing)
    fusion_engine.set_on_identity_unknown(on_identity_unknown)
    await fusion_engine.start()

    # 初始化状态机
    state_machine = StateMachine(config=config.get('state_machine', {}))
    state_machine.set_on_state_changed(on_state_changed)

    # Phase 3: 初始化 STT（异步后台加载）
    stt_module = SpeechToText()
    stt_module.set_on_transcription(
        lambda result: asyncio.create_task(broadcast_event('stt.transcription', result))
    )
    asyncio.create_task(stt_module.load_model())

    # Phase 3: 初始化 LLM
    llm_manager = LLMManager(config.get('llm', {}))
    llm_manager.set_on_token(
        lambda token_info: asyncio.create_task(broadcast_event('llm.token', token_info))
    )
    llm_manager.set_on_response(
        lambda response_info: asyncio.create_task(broadcast_event('llm.response', response_info))
    )
    await llm_manager.initialize()

    # Phase 3: 初始化 TTS
    tts_module = TextToSpeech(config.get('tts', {}))
    tts_module.set_on_start(
        lambda info: asyncio.create_task(broadcast_event('tts.start', info))
    )
    tts_module.set_on_complete(
        lambda info: asyncio.create_task(broadcast_event('tts.complete', info))
    )
    tts_module.set_on_unavailable(
        lambda reason: asyncio.create_task(broadcast_event('tts.unavailable', reason))
    )

    # Phase 3: 初始化免唤醒指令
    wakefree_manager = WakeFreeManager()

    # Phase 3: 初始化视觉意图
    visual_detector = VisualIntentDetector(config.get('visual_intent', {}))
    visual_detector.initialize()

    # Phase 5: 初始化姿态/手势模块
    pose_module = PoseModule(
        pose_config=config.get('pose', {}),
        gesture_config=config.get('gesture', {}),
    )
    pose_module.initialize()
    pose_module.set_on_gesture_detected(on_gesture_detected)
    pose_module.set_state_provider(state_machine.get_current_state if state_machine else None)
    pose_module.register_default_actions()

    # Phase 4: 多人模式管理器
    multi_person = MultiPersonManager()
    multi_person.set_on_state_change(on_multi_state_change)
    multi_person.set_on_person_join(on_person_join)
    multi_person.set_on_person_leave(on_person_leave)

    # Phase 4: 任务管理器
    task_manager = TaskManager()

    # Phase 4: 技能加载器
    skill_loader = SkillLoader()
    skill_loader.discover()
    asyncio.create_task(skill_loader.start_watcher())

    # Phase 3: 对话编排器
    conversation = ConversationOrchestrator()
    conversation.set_modules(stt=stt_module, llm=llm_manager, tts=tts_module, wakefree=wakefree_manager)
    conversation.set_on_sub_state_change(on_chat_sub_state_change)
    conversation.set_on_user_message(on_user_message)
    conversation.set_on_assistant_message(on_assistant_message)

    # 初始化摄像头管线（Phase 4: 多脸输出回调）
    camera_pipeline = CameraPipeline(config=config.get('camera', {}))
    camera_pipeline.set_on_face_detected(on_face_detected)
    camera_pipeline.set_on_face_lost(on_face_lost)
    camera_pipeline.set_on_face_embedding(on_face_embedding)
    camera_pipeline.set_on_pose_frame(on_pose_frame)  # Phase 5
    camera_pipeline.set_on_error(on_camera_error)
    camera_pipeline.set_state_provider(state_machine.get_current_state)

    # 初始化音频管线 + STT 回调
    audio_pipeline = AudioPipeline(config=config.get('microphone', {}), wake_word_config=config.get('wake_word', {}))
    audio_pipeline.set_on_voice_start(on_voice_start)
    audio_pipeline.set_on_voice_end(on_voice_end)
    audio_pipeline.set_on_wake_word(on_wake_word)
    audio_pipeline.set_on_voiceprint(on_voiceprint)
    audio_pipeline.set_on_error(on_mic_error)
    # Phase 3: STT 回调 — wake word 触发对话
    audio_pipeline.set_on_stt_trigger(on_stt_trigger)

    # 启动 WebSocket 服务器
    ws_config = config.get('websocket', {})
    host = ws_config.get('host', 'localhost')
    port = find_available_port(ws_config.get('port', 8765), ws_config.get('port_max_retries', 15))

    # 将实际端口写入临时文件，供 Electron 读取
    port_file = PROJECT_ROOT / '.frank_port'
    port_file.write_text(str(port))
    logger.info(f'WebSocket server binding to {host}:{port} (port file: {port_file})')

    async with serve(ws_handler, host, port):
        # 服务启动完毕，日志输出后 Electron 会立即连接
        logger.info(f'Frank Inference Service ready on ws://{host}:{port}')

        # 启动采集管线（可降级，失败不影响 WS 服务）
        try:
            await camera_pipeline.start()
            logger.info('Camera pipeline started')
        except Exception as e:
            logger.warning(f'Camera pipeline start failed (degraded mode): {e}')

        try:
            await audio_pipeline.start()
            logger.info('Audio pipeline started')
        except Exception as e:
            logger.warning(f'Audio pipeline start failed (degraded mode): {e}')

        # 注册信号处理
        stop_event = asyncio.Event()

        def signal_handler():
            logger.info('Shutdown signal received')
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                pass  # Windows 不支持 add_signal_handler

        await stop_event.wait()

    # 清理
    logger.info('Shutting down...')
    if fusion_engine:
        await fusion_engine.stop()
    if camera_pipeline:
        await camera_pipeline.stop()
    if audio_pipeline:
        await audio_pipeline.stop()
    if pose_module:
        pose_module.close()
    logger.info('Frank Inference Service stopped')


if __name__ == '__main__':
    asyncio.run(main())
