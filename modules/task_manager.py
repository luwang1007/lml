# pyright: reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportAny=false, reportMissingTypeArgument=false, reportUnannotatedClassAttribute=false, reportUnnecessaryComparison=false, reportArgumentType=false

import threading
import uuid
from datetime import datetime


class TaskManager:
    _lock = threading.Lock()
    _tasks: dict = {}

    @classmethod
    def create(cls) -> str:
        task_id = str(uuid.uuid4())
        with cls._lock:
            cls._tasks[task_id] = {
                'task_id': task_id,
                'status': 'pending',
                'progress': 0,
                'current_step': '等待开始...',
                'model_status': {},
                'result': None,
                'error': None,
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
        return task_id

    @classmethod
    def update(cls, task_id: str, progress: int, step: str, model_status: dict = None) -> None:
        with cls._lock:
            if task_id not in cls._tasks:
                return
            t = cls._tasks[task_id]
            if t['status'] == 'cancelled':
                return
            t['status'] = 'running'
            t['progress'] = progress
            t['current_step'] = step
            if model_status is not None:
                t['model_status'] = model_status
            t['updated_at'] = datetime.now().isoformat()

    @classmethod
    def complete(cls, task_id: str, result: dict) -> None:
        with cls._lock:
            if task_id not in cls._tasks:
                return
            t = cls._tasks[task_id]
            if t['status'] == 'cancelled':
                return
            t['status'] = 'done'
            t['progress'] = 100
            t['current_step'] = '完成'
            t['result'] = result
            t['updated_at'] = datetime.now().isoformat()

    @classmethod
    def fail(cls, task_id: str, error: str) -> None:
        with cls._lock:
            if task_id not in cls._tasks:
                return
            t = cls._tasks[task_id]
            if t['status'] == 'cancelled':
                return
            t['status'] = 'failed'
            t['error'] = error
            t['updated_at'] = datetime.now().isoformat()

    @classmethod
    def cancel(cls, task_id: str) -> None:
        with cls._lock:
            if task_id in cls._tasks:
                cls._tasks[task_id]['status'] = 'cancelled'
                cls._tasks[task_id]['updated_at'] = datetime.now().isoformat()

    @classmethod
    def get(cls, task_id: str) -> dict | None:
        with cls._lock:
            return cls._tasks.get(task_id)

    @classmethod
    def is_cancelled(cls, task_id: str) -> bool:
        with cls._lock:
            t = cls._tasks.get(task_id)
            return t is not None and t['status'] == 'cancelled'
