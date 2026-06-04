"""
Frank 技能插件系统 (Phase 4)

插件结构: manifest.json + handler.py + prompt.md
自动发现 + 子进程隔离 + 热加载
"""

import asyncio
import json
import logging
import multiprocessing
import os
import sys
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger('frank.skills')


def _run_skill_subprocess(path, params_json, q):
    """在子进程中运行技能 handler（模块级函数，支持 Windows spawn）"""
    import json
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('skill_handler', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, 'execute'):
            result = module.execute(json.loads(params_json))
            q.put({'success': True, 'result': result})
        else:
            q.put({'success': False, 'error': 'No execute() function'})
    except Exception as e:
        q.put({'success': False, 'error': str(e)})


class SkillPlugin:
    """技能插件"""

    def __init__(self, skill_dir: Path):
        self.dir = skill_dir
        self.name = skill_dir.name
        self.manifest: dict = {}
        self.prompt: str = ''
        self._loaded = False

    def load(self) -> bool:
        """加载插件"""
        try:
            manifest_path = self.dir / 'manifest.json'
            if not manifest_path.exists():
                logger.warning(f'No manifest.json in {self.dir}')
                return False

            with open(manifest_path, 'r', encoding='utf-8') as f:
                self.manifest = json.load(f)

            prompt_path = self.dir / 'prompt.md'
            if prompt_path.exists():
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    self.prompt = f.read()

            self._loaded = True
            logger.info(f'Skill loaded: {self.name} v{self.manifest.get("version", "?")}')
            return True
        except Exception as e:
            logger.error(f'Failed to load skill {self.name}: {e}')
            return False

    def get_prompt_context(self) -> str:
        """获取 LLM 上下文片段"""
        if not self.manifest:
            return ''
        keywords = ', '.join(self.manifest.get('trigger_keywords', []))
        description = self.manifest.get('description', '')
        return f'- **{self.manifest.get("display_name", self.name)}**: {description}\n  触发词: {keywords}\n'

    @property
    def is_loaded(self) -> bool:
        return self._loaded


class SkillLoader:
    """技能加载器"""

    def __init__(self, skills_dir: str = 'skills'):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, SkillPlugin] = {}
        self._watcher_task: asyncio.Task | None = None
        self._on_skills_changed: Callable | None = None

    def set_on_skills_changed(self, cb: Callable): self._on_skills_changed = cb

    def discover(self) -> int:
        """扫描并加载所有插件"""
        if not self.skills_dir.exists():
            logger.warning(f'Skills directory not found: {self.skills_dir}')
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            return 0

        count = 0
        for entry in self.skills_dir.iterdir():
            if entry.is_dir() and (entry / 'manifest.json').exists():
                plugin = SkillPlugin(entry)
                if plugin.load():
                    self.skills[plugin.name] = plugin
                    count += 1

        logger.info(f'Discovered {count} skills')
        return count

    def get_llm_context(self) -> str:
        """获取所有插件的 LLM 上下文"""
        if not self.skills:
            return ''

        parts = ['\n## 可用技能\n']
        for skill in self.skills.values():
            if skill.is_loaded:
                parts.append(skill.get_prompt_context())
        return '\n'.join(parts)

    async def execute_skill(self, skill_name: str, params: dict,
                             timeout: float = 10.0) -> dict:
        """在子进程中执行技能"""
        if skill_name not in self.skills:
            return {'error': f'Skill not found: {skill_name}'}

        skill = self.skills[skill_name]
        manifest = skill.manifest
        min_level = manifest.get('min_user_level', 'guest')
        max_timeout = min(timeout, 30 * 60 if manifest.get('estimated_runtime') == 'managed' else 10)

        # 权限校验：检查当前用户角色是否满足技能要求的最低角色等级
        role = params.get('role', 'guest')
        role_levels = {'owner': 3, 'admin': 2, 'member': 1, 'guest': 0, 'unregistered': -1}
        if role_levels.get(role, 0) < role_levels.get(min_level, 0):
            return {'error': f'Permission denied: requires min_user_level={min_level}, current role={role}'}

        handler_path = skill.dir / 'handler.py'
        if not handler_path.exists():
            return {'error': f'No handler.py for skill: {skill_name}'}

        try:
            # 子进程执行
            result_queue: multiprocessing.Queue = multiprocessing.Queue()

            proc = multiprocessing.Process(
                target=_run_skill_subprocess,
                args=(str(handler_path), json.dumps(params), result_queue),
            )
            proc.start()
            proc.join(timeout=max_timeout)

            if proc.is_alive():
                proc.terminate()
                proc.join()
                return {'error': f'Skill execution timeout ({max_timeout}s)'}

            if not result_queue.empty():
                return result_queue.get()

            return {'error': 'No result from skill execution'}

        except Exception as e:
            logger.error(f'Skill execution error ({skill_name}): {e}')
            return {'error': str(e)}

    def list_skills(self) -> list[dict]:
        """列出所有已加载技能"""
        return [
            {
                'name': s.name,
                'display_name': s.manifest.get('display_name', s.name),
                'version': s.manifest.get('version', '?'),
                'description': s.manifest.get('description', ''),
                'trigger_keywords': s.manifest.get('trigger_keywords', []),
                'min_user_level': s.manifest.get('min_user_level', 'guest'),
                'output_type': s.manifest.get('output_type', 'text'),
            }
            for s in self.skills.values() if s.is_loaded
        ]

    async def start_watcher(self):
        """启动文件监听（热加载）"""
        async def _watch():
            seen = set(self.skills.keys())
            while True:
                try:
                    await asyncio.sleep(5)
                    if not self.skills_dir.exists():
                        continue
                    current = set(
                        d.name for d in self.skills_dir.iterdir()
                        if d.is_dir() and (d / 'manifest.json').exists()
                    )
                    if current != seen:
                        self.skills.clear()
                        self.discover()
                        seen = set(self.skills.keys())
                        logger.info(f'Skills hot-reloaded: {len(self.skills)} skills')
                        if self._on_skills_changed:
                            self._on_skills_changed({'count': len(self.skills)})
                except Exception as e:
                    logger.error(f'Skill watcher error: {e}')
                    await asyncio.sleep(5)

        self._watcher_task = asyncio.create_task(_watch())
