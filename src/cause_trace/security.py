"""认证与密钥整改（T-25 / FR-01、ADR-06）。

- 业务接口按 introspection 返回的 scope 做细粒度鉴权；
- 敏感配置一律从环境变量读取，代码与仓库内不出现明文密钥；
- 启动时校验必需密钥是否就位，缺失即明确报错，不静默使用弱默认值。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException

SCOPE_ADMIN = "admin:cause"
SCOPE_READ = "read:insight-agent"
SCOPE_WRITE = "write:insight-agent"


@dataclass(frozen=True)
class Principal:
    user_id: int
    scopes: frozenset[str]

    def require(self, scope: str) -> None:
        if SCOPE_ADMIN in self.scopes or scope in self.scopes:
            return
        raise HTTPException(status_code=403, detail=f"缺少权限：{scope}")


def require_scope(scope: str):
    """FastAPI 依赖工厂：从请求头解析主体并校验 scope。"""

    def dependency(
        x_user_id: str | None = Header(default=None),
        x_scopes: str | None = Header(default=None),
    ) -> Principal:
        if not x_user_id:
            raise HTTPException(status_code=401, detail="未认证：缺少 X-User-Id")
        scopes = frozenset(item.strip() for item in (x_scopes or "").split(",") if item.strip())
        principal = Principal(user_id=int(x_user_id), scopes=scopes)
        principal.require(scope)
        return principal

    return dependency


def read_secret(name: str, *, required: bool = False) -> str | None:
    """读取密钥：只认环境变量，不回落到配置文件或代码常量。"""
    value = os.environ.get(name)
    if required and not value:
        raise RuntimeError(f"缺少必需密钥环境变量：{name}")
    return value


def unsafe_defaults_in_use() -> list[str]:
    """列出仍在用开发默认值的敏感项，供部署自检与审计。"""
    risky: list[str] = []
    if not os.environ.get("CAUSE_SANDBOX_INTERNAL_TOKEN"):
        risky.append("CAUSE_SANDBOX_INTERNAL_TOKEN")
    if not os.environ.get("CAUSE_DATABASE_URL"):
        risky.append("CAUSE_DATABASE_URL")
    return risky
