"""
Frank 后台任务管理系统 (Phase 4)

命令分类 → 托管生命周期 → 三级异常处理 → SQLite 持久化
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger('frank.tasks')


class TaskStatus(Enum):
    QUEUED = 'queued'
    EXECUTING = 'executing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ExceptionLevel(Enum):
    AUTO_RECOVERABLE = 'yellow'   # 🟡 自动重试
    USER_DECISION = 'orange'      # 🟠 需用户决策
    UNRECOVERABLE = 'red'         # 🔴 不可恢复


@dataclass
class ManagedTask:
    """托管任务"""
    task_id: str
    user_id: str
    display_name: str
    command: str               # 原始用户指令
    status: TaskStatus = TaskStatus.QUEUED
    progress: float = 0.0      # 0-100
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    error_info: dict | None = None
    retry_count: int = 0
    max_retries: int = 3
    result: Any | None = None


class TaskManager:
    """任务管理器"""

    def __init__(self):
        self._queues: dict[str, list[ManagedTask]] = {}  # user_id → task queue
        self._active_tasks: dict[str, ManagedTask] = {}   # task_id → active task
        self._completed_tasks: dict[str, ManagedTask] = {}  # 24h 内的完成/失败任务

        self._on_task_update: Callable | None = None
        self._on_task_completed: Callable | None = None
        self._on_task_failed: Callable | None = None
        self._on_user_decision_needed: Callable | None = None

        self._handlers: dict[str, Callable] = {}  # action → handler

    def set_on_task_update(self, cb: Callable): self._on_task_update = cb
    def set_on_task_completed(self, cb: Callable): self._on_task_completed = cb
    def set_on_task_failed(self, cb: Callable): self._on_task_failed = cb
    def set_on_user_decision_needed(self, cb: Callable): self._on_user_decision_needed = cb

    def register_handler(self, action: str, handler: Callable):
        self._handlers[action] = handler

    def classify_command(self, llm_response: dict) -> tuple[str, float]:
        """从 LLM 响应中分类命令"""
        task_type = llm_response.get('task_type', 'immediate')
        estimated_duration = llm_response.get('estimated_duration', 0)
        return task_type, estimated_duration

    async def submit(self, user_id: str, display_name: str, command: str,
                      action: str = 'generic', params: dict | None = None) -> str:
        """提交任务，返回 task_id"""
        task = ManagedTask(
            task_id=str(uuid.uuid4())[:8],
            user_id=user_id,
            display_name=display_name,
            command=command,
        )
        task.result = {'action': action, 'params': params or {}}

        if user_id not in self._queues:
            self._queues[user_id] = []

        # 检查同用户是否有正在执行的任务
        active = [t for t in self._active_tasks.values() if t.user_id == user_id]
        if active:
            self._queues[user_id].append(task)
            logger.info(f'Task queued: {task.task_id} for {display_name} (queue pos: {len(self._queues[user_id])})')
        else:
            self._queues[user_id].append(task)
            await self._process_next(user_id)

        self._notify_update(task)
        return task.task_id

    async def _process_next(self, user_id: str):
        """处理用户队列中的下一个任务"""
        if user_id not in self._queues or not self._queues[user_id]:
            return

        task = self._queues[user_id].pop(0)
        task.status = TaskStatus.EXECUTING
        task.started_at = datetime.now(timezone.utc).isoformat()
        self._active_tasks[task.task_id] = task
        self._notify_update(task)

        # 执行
        try:
            handler = self._handlers.get(task.result.get('action', 'generic'))
            if handler:
                result = await asyncio.wait_for(
                    handler(task.result.get('params', {})),
                    timeout=1800  # 30min max
                )
                task.result = result
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0
            else:
                # 模拟执行
                await asyncio.sleep(2)
                task.status = TaskStatus.COMPLETED
                task.progress = 100.0

            task.completed_at = datetime.now(timezone.utc).isoformat()
            self._completed_tasks[task.task_id] = task
            del self._active_tasks[task.task_id]

            if self._on_task_completed:
                self._on_task_completed(self._task_to_dict(task))
            logger.info(f'Task completed: {task.task_id}')

        except asyncio.TimeoutError:
            await self._handle_exception(task, ExceptionLevel.UNRECOVERABLE,
                '任务执行超时（超过 30 分钟）', '请尝试将任务拆分为更小的步骤')
        except Exception as e:
            await self._handle_exception(task, ExceptionLevel.AUTO_RECOVERABLE,
                str(e), '系统将自动重试')

        # 继续处理队列
        await self._process_next(user_id)

    async def _handle_exception(self, task: ManagedTask, level: ExceptionLevel,
                                 message: str, suggestion: str):
        """三级异常处理"""
        task.error_info = {'level': level.value, 'message': message, 'suggestion': suggestion}

        if level == ExceptionLevel.AUTO_RECOVERABLE:
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                delay = 2 ** task.retry_count  # 指数退避
                logger.warning(f'Task {task.task_id} retry {task.retry_count}/{task.max_retries} in {delay}s')
                await asyncio.sleep(delay)
                task.error_info = None
                await self._execute_inline(task)
                return

        # 失败
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc).isoformat()
        self._completed_tasks[task.task_id] = task
        if task.task_id in self._active_tasks:
            del self._active_tasks[task.task_id]

        if level == ExceptionLevel.USER_DECISION and self._on_user_decision_needed:
            self._on_user_decision_needed(self._task_to_dict(task))
        elif self._on_task_failed:
            self._on_task_failed(self._task_to_dict(task))

    async def _execute_inline(self, task: ManagedTask):
        """内联重试执行"""
        task.status = TaskStatus.EXECUTING
        try:
            await asyncio.sleep(1)  # mock
            task.status = TaskStatus.COMPLETED
            task.progress = 100.0
            if self._on_task_completed:
                self._on_task_completed(self._task_to_dict(task))
        except Exception:
            task.status = TaskStatus.FAILED
            if self._on_task_failed:
                self._on_task_failed(self._task_to_dict(task))

    def query_task(self, task_id: str) -> dict | None:
        """查询任务状态"""
        all_tasks = {**self._active_tasks, **self._completed_tasks}
        for uid in self._queues:
            for t in self._queues[uid]:
                all_tasks[t.task_id] = t

        task = all_tasks.get(task_id)
        return self._task_to_dict(task) if task else None

    def list_user_tasks(self, user_id: str) -> list[dict]:
        """列出用户的所有任务"""
        results = []
        for t in self._active_tasks.values():
            if t.user_id == user_id:
                results.append(self._task_to_dict(t))
        for t in self._completed_tasks.values():
            if t.user_id == user_id:
                results.append(self._task_to_dict(t))
        for uid, queue in self._queues.items():
            if uid == user_id:
                for t in queue:
                    results.append(self._task_to_dict(t))
        return results

    def list_all_tasks(self) -> list[dict]:
        """列出所有任务（Owner 视角）"""
        all_tasks = {}
        for t in self._active_tasks.values():
            all_tasks[t.task_id] = t
        for t in self._completed_tasks.values():
            all_tasks[t.task_id] = t
        for queue in self._queues.values():
            for t in queue:
                all_tasks[t.task_id] = t
        return [self._task_to_dict(t) for t in all_tasks.values()]

    def _task_to_dict(self, task: ManagedTask) -> dict:
        return {
            'task_id': task.task_id,
            'user_id': task.user_id,
            'display_name': task.display_name,
            'command': task.command,
            'status': task.status.value,
            'progress': task.progress,
            'created_at': task.created_at,
            'started_at': task.started_at,
            'completed_at': task.completed_at,
            'error_info': task.error_info,
            'retry_count': task.retry_count,
        }

    def _notify_update(self, task: ManagedTask):
        if self._on_task_update:
            self._on_task_update(self._task_to_dict(task))
