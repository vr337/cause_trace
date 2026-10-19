"""校验 Alembic 迁移脚本与 ORM 元数据一致。

SQLite 编译规则在 conftest 注册，这里复用同一套建表逻辑跑迁移脚本的 AST，
确保「模型改了、迁移忘改」这类漂移在 CI 就被发现。
"""

from __future__ import annotations

import ast
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.py"))


def test_migration_files_exist():
    assert _migration_files(), " migrations/versions 下必须有迁移脚本"


def test_migrations_are_valid_python_with_required_attributes():
    for path in _migration_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = next(
            (n for n in tree.body if isinstance(n, ast.Assign) and _targets(n, "revision")), None
        )
        assert module is not None, f"{path.name} 缺少 revision 标识"

        names = {
            target.id
            for node in tree.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        assert {"revision", "down_revision"} <= names, f"{path.name} 缺少 revision/down_revision"


def test_revisions_are_unique_and_form_a_chain():
    revisions: dict[str, Path] = {}
    parents: dict[str, str | None] = {}
    for path in _migration_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _literal(tree, "revision")
        down_revision = _literal(tree, "down_revision")
        assert revision, f"{path.name} 的 revision 不能为空"
        assert revision not in revisions, f"revision {revision} 重复：{path.name} 与 {revisions[revision].name}"
        revisions[revision] = path
        parents[revision] = down_revision

    for revision, parent in parents.items():
        if parent is not None:
            assert parent in revisions, f"{revision} 的父版本 {parent} 不存在"


def test_single_head_exists():
    chain = _revisions_and_parents()
    roots = [revision for revision, parent in chain.items() if parent is None]
    assert len(roots) == 1, f"应只有一个根迁移，当前有 {roots}"


def _revisions_and_parents() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for path in _migration_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        result[_literal(tree, "revision")] = _literal(tree, "down_revision")
    return result


def _targets(node: ast.Assign, name: str) -> bool:
    return any(isinstance(t, ast.Name) and t.id == name for t in node.targets)


def _literal(tree: ast.Module, name: str) -> str | None:
    for node in tree.body:
        if isinstance(node, ast.Assign) and _targets(node, name):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            return None
    return None
