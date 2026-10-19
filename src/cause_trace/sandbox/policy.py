"""SQL 静态解析白名单（Spec 14.2）。

LLM 生成的 SQL 一律先过 AST 校验再执行：只放行单条 SELECT，写操作、DDL、
系统库与文件函数全部拦下，并在无 LIMIT 时自动补上限，避免一次查询拖垮数仓。
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from cause_trace.errors import SandboxPolicyError

DIALECT = "mysql"

FORBIDDEN_SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}

# 兼容不同 sqlglot 版本：某个节点类型不存在时直接跳过
_WRITE_NODE_NAMES = (
    "Insert",
    "Update",
    "Delete",
    "Drop",
    "Alter",
    "TruncateTable",
    "Create",
    "Grant",
    "Revoke",
    "Merge",
    "Command",
)
WRITE_NODE_TYPES = tuple(
    node for node in (getattr(exp, name, None) for name in _WRITE_NODE_NAMES) if node is not None
)

FORBIDDEN_FUNCTIONS = {"load_file", "sleep", "benchmark"}

# 方言解析可能把这些片段吞进字符串或注释，再用关键字兜底
FORBIDDEN_KEYWORDS = ("into outfile", "into dumpfile", "load data")


def _policy_error(message: str) -> SandboxPolicyError:
    return SandboxPolicyError(message, code="SBX_POLICY_VIOLATION")


def _write_blocked(message: str) -> SandboxPolicyError:
    return SandboxPolicyError(message, code="SBX_WRITE_BLOCKED")


_INTO_TYPE = getattr(exp, "Into", None)


def _check_functions(expression: exp.Expression) -> None:
    # 不同 sqlglot 版本会把 LOAD_FILE 归到专用节点或 Anonymous，两种都要覆盖
    for node in expression.find_all(exp.Func):
        names = {str(getattr(node, "name", "")).lower(), node.sql_name().lower()}
        if names & FORBIDDEN_FUNCTIONS:
            raise _policy_error(f"禁止调用危险函数：{node.sql()}")
    if _INTO_TYPE is not None and expression.find(_INTO_TYPE) is not None:
        raise _policy_error("禁止 INTO OUTFILE / DUMPFILE 文件操作")


def _collect_tables(expression: exp.Expression) -> set[str]:
    """只收集规范名：带库名时用 `库.表`，否则用裸表名，避免白名单比较时重复放行。"""
    tables: set[str] = set()
    for table in expression.find_all(exp.Table):
        schema = table.db.lower() if table.db else ""
        if schema in FORBIDDEN_SYSTEM_SCHEMAS:
            raise _policy_error(f"禁止访问系统库：{schema}")
        name = f"{schema}.{table.name.lower()}" if schema else table.name.lower()
        tables.add(name)
    return tables


def _apply_limit(expression: exp.Expression, max_rows: int) -> str:
    if isinstance(expression, exp.Select):
        limit = expression.args.get("limit")
        if limit is None:
            return expression.limit(max_rows).sql(dialect=DIALECT)
        literal = limit.expression
        if isinstance(literal, exp.Literal) and literal.is_int and int(literal.this) > max_rows:
            return expression.limit(max_rows).sql(dialect=DIALECT)
        return expression.sql(dialect=DIALECT)
    # UNION / 子查询：只能在外层再套一层 LIMIT
    return f"SELECT * FROM ({expression.sql(dialect=DIALECT)}) AS _limited LIMIT {int(max_rows)}"


def validate_sql(
    sql: str,
    *,
    max_rows: int = 100_000,
    allowed_tables: Iterable[str] | None = None,
) -> str:
    """校验通过后返回带 LIMIT 的 SQL；违规时抛 ``SBX_WRITE_BLOCKED`` / ``SBX_POLICY_VIOLATION``。"""
    text = (sql or "").strip()
    if not text:
        raise _policy_error("SQL 不能为空")

    lowered = text.lower()
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in lowered:
            raise _policy_error(f"SQL 含被禁止的关键字：{keyword}")

    try:
        statements = [s for s in sqlglot.parse(text, read=DIALECT) if s is not None]
    except ParseError as exc:
        raise _policy_error(f"SQL 解析失败：{exc}") from exc

    if not statements:
        raise _policy_error("SQL 不能为空")
    if len(statements) > 1:
        raise _policy_error("不允许多语句执行")

    expression = statements[0]
    for node in expression.walk():
        if isinstance(node, WRITE_NODE_TYPES):
            raise _write_blocked(f"检测到写操作或 DDL：{type(node).__name__}")

    if not isinstance(expression, exp.Select | exp.Union | exp.Subquery):
        raise _policy_error("仅允许 SELECT 查询")

    _check_functions(expression)

    # 系统库检查与白名单无关，任何时候都要做
    tables = _collect_tables(expression)
    if allowed_tables is not None:
        allowed = {t.lower() for t in allowed_tables}
        for table in tables:
            if table not in allowed:
                raise _policy_error(f"表不在白名单内：{table}")

    return _apply_limit(expression, max_rows)
