"""数据库基础设施。

库划分遵循 Spec 5.3：归因业务表全部落在新建 `cause` 库，
数据库连接串通过环境变量 `CAUSE_DATABASE_URL` 注入，禁止在代码中硬编码凭据。
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""


DEFAULT_DATABASE_URL = "mysql+pymysql://cause:causepass@127.0.0.1:3306/cause?charset=utf8mb4"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    """读取数据库连接串，默认指向本地 dev 环境。"""
    return os.environ.get("CAUSE_DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine() -> Engine:
    """进程内复用同一个 Engine。"""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True, pool_recycle=3600)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务上下文：正常提交，异常回滚。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
