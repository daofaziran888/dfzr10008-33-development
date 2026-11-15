"""质量反馈与产品准入的共用规则。

数据质量反馈不只用于记录问题：未解决的高严重度反馈会冻结对应数据产品的
认证准入与发布准入。产品定义、产品认证、质量反馈三处都从这里取同一份判定，
避免各自维护一套口径。
"""
from __future__ import annotations

from typing import Any, Iterable

from app.store import store

FEEDBACK_MODULE = "feedback"
PRODUCT_MODULE = "product"

RESOLVED_STATUSES = {"已解决", "已关闭"}
UNRESOLVED_STATUSES = {"待处理", "处理中"}
HIGH_SEVERITIES = {"高", "严重", "紧急", "P0", "P1"}

GATE_FROZEN = "冻结"
GATE_OPEN = "可准入"


def _text(value: Any) -> str:
    return str(value or "").strip()


def entry_status(entry: dict[str, Any]) -> str:
    """反馈的当前处理状态：以 status 为准，兼容只写了“处理状态”的历史数据。"""
    return _text(entry.get("status")) or _text(entry.get("处理状态")) or "待处理"


def entry_severity(entry: dict[str, Any]) -> str:
    return _text(entry.get("严重程度")) or "中"


def is_resolved(entry: dict[str, Any]) -> bool:
    return entry_status(entry) in RESOLVED_STATUSES


def is_unresolved(entry: dict[str, Any]) -> bool:
    return not is_resolved(entry)


def is_high_severity(entry: dict[str, Any]) -> bool:
    return entry_severity(entry) in HIGH_SEVERITIES


def feedback_product_refs(entry: dict[str, Any]) -> set[str]:
    """一条反馈可能通过产品编号、产品名称或“数据产品”字段关联到产品。"""
    refs: set[str] = set()
    for key in ("产品编号", "数据产品", "数据产品名称"):
        value = _text(entry.get(key))
        if value:
            refs.add(value)
    return refs


def resolve_product(ref: Any) -> dict[str, Any] | None:
    """按主键、产品编号或产品名称找到数据产品。"""
    text = _text(ref)
    if not text:
        return None
    for row in store.rows(PRODUCT_MODULE):
        if text == _text(row.get("产品编号")) or text == _text(row.get("产品名称")):
            return row
    if text.isdigit():
        entry_id = int(text)
        for row in store.rows(PRODUCT_MODULE):
            if int(row.get("id", 0)) == entry_id:
                return row
    return None


def feedback_for_product(product: dict[str, Any] | str) -> list[dict[str, Any]]:
    """取出关联到某个产品的全部反馈记录，按反馈时间升序。"""
    if isinstance(product, dict):
        keys = {
            _text(product.get("产品编号")),
            _text(product.get("产品名称")),
        }
    else:
        found = resolve_product(product)
        keys = (
            {_text(found.get("产品编号")), _text(found.get("产品名称"))}
            if found
            else {_text(product)}
        )
    keys.discard("")
    rows = [
        row
        for row in store.rows(FEEDBACK_MODULE)
        if feedback_product_refs(row) & keys
    ]
    return sorted(rows, key=lambda row: _text(row.get("反馈时间")))


def gate_for_product(product: dict[str, Any] | str) -> dict[str, Any]:
    """计算产品的质量准入结果：有未解决的高严重度反馈即冻结。"""
    resolved = product if isinstance(product, dict) else resolve_product(product)
    code = _text(resolved.get("产品编号")) if resolved else _text(product)
    name = _text(resolved.get("产品名称")) if resolved else ""
    entries = feedback_for_product(resolved if resolved is not None else code)
    unresolved = [row for row in entries if is_unresolved(row)]
    high_unresolved = [row for row in unresolved if is_high_severity(row)]
    frozen = bool(high_unresolved)
    blockers = [
        {
            "反馈编号": _text(row.get("反馈编号")),
            "反馈类型": _text(row.get("反馈类型")),
            "严重程度": entry_severity(row),
            "处理状态": entry_status(row),
            "反馈人": _text(row.get("反馈人")),
            "反馈时间": _text(row.get("反馈时间")),
        }
        for row in high_unresolved
    ]
    reason = ""
    if blockers:
        codes = "、".join(item["反馈编号"] or "未编号反馈" for item in blockers)
        reason = f"存在未解决的高严重度反馈（{codes}），认证与发布准入已冻结"
    result = GATE_FROZEN if frozen else GATE_OPEN
    return {
        "产品编号": code,
        "产品名称": name,
        "未解决反馈数量": len(unresolved),
        "高严重度未解决数量": len(high_unresolved),
        "准入结果": result,
        "认证准入": result,
        "发布准入": result,
        "冻结原因": reason,
        "阻断反馈": blockers,
    }


def summarize_gate(gate: dict[str, Any]) -> dict[str, Any]:
    """把准入结果铺到列表行上时使用的字段子集。"""
    return {
        "未解决反馈数量": gate["未解决反馈数量"],
        "高严重度未解决反馈数量": gate["高严重度未解决数量"],
        "准入结果": gate["准入结果"],
        "认证准入": gate["认证准入"],
        "发布准入": gate["发布准入"],
        "冻结原因": gate["冻结原因"],
        "阻断反馈": gate["阻断反馈"],
    }


def unresolved_count(entries: Iterable[dict[str, Any]] | None = None) -> int:
    rows = list(entries) if entries is not None else store.rows(FEEDBACK_MODULE)
    return sum(1 for row in rows if is_unresolved(row))
