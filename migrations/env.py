"""Alembic 运行环境：`cause` 库连接串通过 CAUSE_DATABASE_URL 注入。"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# 导入模型包本身即是目的：注册 metadata，autogenerate 才能看到全部表
from cause_trace.db import models  # noqa: F401
from cause_trace.db.base import Base, get_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# alembic.ini 不保存连接串，避免凭据入库
config.set_main_option("sqlalchemy.url", os.environ.get("CAUSE_DATABASE_URL") or get_database_url())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
