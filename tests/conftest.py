"""共享 fixtures。

仓储层测试跑在 SQLite 内存库上：不需要 MySQL 就能验证模型关系、约束与树操作，
迁移脚本本身由 test_migration.py 单独校验。

模型按 Spec 5.1 使用 bigint 主键，SQLite 不认这种自增写法，这里把主键的
BigInteger 编译成 INTEGER PRIMARY KEY，其余类型保持原样，避免为测试改模型。
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cause_trace.db.base import Base  # noqa: E402
from cause_trace.db import models  # noqa: E402,F401 - 注册元数据


def _sqlite_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:", future=True)

    @compiles(BigInteger, "sqlite")  # noqa: F811 - SQLAlchemy 的编译期改写
    def _compile_bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001, ARG001
        return "INTEGER"

    return engine


@pytest.fixture
def session() -> Iterator[Session]:
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as db:
        yield db
