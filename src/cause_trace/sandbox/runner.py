"""沙箱执行器（T-03）：Docker 隔离执行 Python、只读执行 SQL、资源限额。

安全边界（Spec 14）：

- SQL 只能以只读账号执行，执行前经 ``policy.validate_sql`` AST 白名单；
- Python 在 Docker 容器内执行：只读根文件系统、无网络、断网、降权、限额、
  超时后强制销毁，不挂载宿主机目录；
- 结果集行数与输出大小均服务端截断。
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from cause_trace.config import Settings, get_settings
from cause_trace.errors import SandboxPolicyError, SandboxUnavailableError
from cause_trace.sandbox.policy import validate_sql


@dataclass
class ExecutionRequest:
    exec_type: str
    code: str
    user_id: int | None = None
    timeout_s: int | None = None
    max_rows: int | None = None
    allowed_tables: list[str] | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    task_id: str
    status: str
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    duration_ms: int = 0
    stdout: str = ""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "error": self.error,
        }


class DockerBuilder:
    """构造受限容器执行命令（Spec 14.1 / 14.4）。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def command(self, *, memory_mb: int = 512, cpus: float = 1.0) -> list[str]:
        return [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network=none",
            "--read-only",
            "--memory",
            f"{memory_mb}m",
            "--memory-swap",
            f"{memory_mb}m",
            "--cpus",
            str(cpus),
            "--pids-limit",
            "64",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            self.settings.sandbox_image,
            "python",
            "-I",
            "-",
        ]


class DockerPythonRunner:
    """在 Docker 容器内执行 Python 代码，代码经 stdin 传入，结果经 stdout 返回。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.builder = DockerBuilder(self.settings)

    def run(self, request: ExecutionRequest, timeout_s: int) -> ExecutionResult:
        task_id = f"sbx-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        max_output = self.settings.sandbox_max_output_bytes
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                self.builder.command(),
                input=request.code,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailableError("宿主机未安装 Docker，无法执行沙箱任务") from exc
        except subprocess.TimeoutExpired:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ExecutionResult(
                task_id=task_id,
                status="timeout",
                duration_ms=duration_ms,
                error="SBX_TIMEOUT",
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout = completed.stdout[:max_output]
        truncated_output = len(completed.stdout) > max_output
        if completed.returncode != 0:
            return ExecutionResult(
                task_id=task_id,
                status="failed",
                duration_ms=duration_ms,
                stdout=stdout,
                error=(completed.stderr or "SBX_EXECUTION_FAILED")[:2000],
                truncated=truncated_output,
            )

        return ExecutionResult(
            task_id=task_id,
            status="success",
            duration_ms=duration_ms,
            stdout=stdout,
            truncated=truncated_output,
        )


class SqlRunner:
    """通过只读账号执行已通过白名单校验的 SQL。"""

    def __init__(self, settings: Settings | None = None, engine: Engine | None = None) -> None:
        self.settings = settings or get_settings()
        self._engine = engine

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            url = self.settings.warehouse_readonly_url
            if not url:
                raise SandboxUnavailableError(
                    "未配置 CAUSE_WAREHOUSE_READONLY_URL，沙箱无法执行 SQL"
                )
            self._engine = create_engine(url, pool_pre_ping=True, pool_recycle=1800)
        return self._engine

    def run(self, request: ExecutionRequest, timeout_s: int, max_rows: int) -> ExecutionResult:
        task_id = f"sbx-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        safe_sql = validate_sql(
            request.code, max_rows=max_rows, allowed_tables=request.allowed_tables
        )
        started = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                # MySQL 会话级执行超时（毫秒）
                conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME={int(timeout_s * 1000)}"))
                result = conn.execute(text(safe_sql), request.params or {})
                columns = list(result.keys())
                fetched = result.fetchmany(max_rows + 1)
        except SandboxPolicyError:
            raise
        except Exception as exc:  # 数据库侧错误统一包装为执行失败
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ExecutionResult(
                task_id=task_id,
                status="failed",
                duration_ms=duration_ms,
                error=str(exc)[:2000],
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        truncated = len(fetched) > max_rows
        rows = [list(row) for row in fetched[:max_rows]]
        return ExecutionResult(
            task_id=task_id,
            status="success",
            columns=columns,
            rows=_json_safe(rows),
            row_count=len(rows),
            truncated=truncated,
            duration_ms=duration_ms,
        )


def _json_safe(rows: list[list[Any]]) -> list[list[Any]]:
    """把 datetime / Decimal 等不可 JSON 序列化的值转成字符串。"""
    safe: list[list[Any]] = []
    for row in rows:
        safe_row: list[Any] = []
        for value in row:
            if value is None or isinstance(value, int | float | bool | str):
                safe_row.append(value)
            else:
                safe_row.append(str(value))
        safe.append(safe_row)
    return safe


def dumps_result(result: ExecutionResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False)
