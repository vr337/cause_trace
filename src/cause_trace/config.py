"""配置中心。

所有敏感配置通过环境变量注入（ADR-06），仓库内不落明文密钥。
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """服务配置，环境变量统一使用 `CAUSE_` 前缀。"""

    model_config = SettingsConfigDict(
        env_prefix="CAUSE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "mysql+pymysql://cause:causepass@127.0.0.1:3306/cause?charset=utf8mb4"
    # 沙箱执行 SQL 时的只读数仓连接串；未配置时 /execute 返回 SBX_UNAVAILABLE
    warehouse_readonly_url: str | None = None
    # sandbox-runner 内部鉴权令牌，仅 insight-agent 可调用
    sandbox_internal_token: str = "dev-internal-token"
    sandbox_image: str = "cause-trace-sandbox:latest"
    sandbox_default_timeout_s: int = 30
    sandbox_default_max_rows: int = 100_000
    sandbox_max_output_bytes: int = 1_048_576
    sql_conservation_tolerance: float = 1e-9


def get_settings() -> Settings:
    return Settings()
