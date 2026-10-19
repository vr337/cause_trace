"""报告七章节 payload JSON Schema（PRD 第 9 章 / Spec ADR-05）。

报告正文统一引用该 schema，入库前与导出前各校验一次。
"""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from cause_trace.errors import ReportPayloadError

CONTRIBUTION_ITEM = {
    "type": "object",
    "required": ["factor", "contribution", "contribution_rate", "direction"],
    "properties": {
        "factor": {"type": "string", "minLength": 1},
        "contribution": {"type": "number"},
        "contribution_rate": {"type": "number"},
        "direction": {"type": "string", "enum": ["up", "down", "flat"]},
    },
    "additionalProperties": True,
}

REPORT_PAYLOAD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "cause_trace 七章节归因报告",
    "type": "object",
    "required": ["meta", "sections"],
    "properties": {
        "meta": {
            "type": "object",
            "required": ["title", "domain_id", "metric_id", "window_start", "window_end", "baseline"],
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "domain_id": {"type": "integer"},
                "metric_id": {"type": "integer"},
                "window_start": {"type": "string"},
                "window_end": {"type": "string"},
                "baseline": {"type": "string", "enum": ["dod", "yoy", "target"]},
                "generated_at": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "sections": {
            "type": "array",
            "minItems": 7,
            "maxItems": 7,
            "items": {
                "type": "object",
                "required": ["id", "title", "content"],
                "properties": {
                    "id": {
                        "type": "string",
                        "enum": [
                            "background",
                            "factor_contribution",
                            "drilldown_evidence",
                            "conclusion",
                            "evidence_chain",
                            "what_if",
                            "action_plan",
                        ],
                    },
                    "title": {"type": "string", "minLength": 1},
                    "content": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": True,
}

# PRD 第 9 章：七章节编号与标题，供组装器与导出层共用
SECTION_DEFINITIONS: list[tuple[str, str]] = [
    ("background", "异动背景与问题定义"),
    ("factor_contribution", "因子贡献率拆解"),
    ("drilldown_evidence", "细分维度下钻证据"),
    ("conclusion", "核心归因结论"),
    ("evidence_chain", "因果证据链与检验置信度"),
    ("what_if", "What-If 情景模拟结论"),
    ("action_plan", "可落地策略行动清单"),
]

_validator = Draft202012Validator(REPORT_PAYLOAD_SCHEMA)


def validate_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """校验报告 payload，失败抛 ``BIZ_INVALID_REPORT_PAYLOAD``。"""
    try:
        _validator.validate(payload)
    except ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        raise ReportPayloadError(f"报告 payload 校验失败（{path}）：{exc.message}") from exc

    section_ids = [section["id"] for section in payload["sections"]]
    expected = [section_id for section_id, _ in SECTION_DEFINITIONS]
    if section_ids != expected:
        raise ReportPayloadError(
            f"报告章节顺序或数量不符，期望 {expected}，实际 {section_ids}"
        )
    return payload


def schema_json() -> str:
    return json.dumps(REPORT_PAYLOAD_SCHEMA, ensure_ascii=False, indent=2)


def empty_section_payload(
    meta: dict[str, Any], contents: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """按七章节骨架组装 payload，缺失章节补空对象后仍可通过校验。"""
    contents = contents or {}
    return {
        "meta": meta,
        "sections": [
            {"id": section_id, "title": title, "content": contents.get(section_id, {})}
            for section_id, title in SECTION_DEFINITIONS
        ],
    }
