"""数据产品定义业务规则：状态流转、字段校验、筛选口径与质量准入都收在这里。

产品的「未解决反馈数量」与「准入结果」直接来自质量反馈模块：只要有未解决的高
严重度反馈，认证准入与发布准入都会冻结，发布动作会被拦下并说明阻断原因。
"""
from __future__ import annotations

from typing import Any

from app.services import quality_gate
from app.store import store

MODULE = "product"
REQUIRED_FIELDS = ["产品编号", "产品名称", "产品类型"]
STATUS_ORDER = ["草稿", "开发中", "已发布", "已下线"]
ACTION_RULES = {"发布产品": "草稿", "下线产品": "已发布", "删除产品": "已下线"}
NEGATIVE_ACTIONS = ["下线产品"]


class ProductService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("产品编号", ""))
                or keyword in str(row.get("产品名称", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._present(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"数据产品 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据产品定义可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        gate = quality_gate.gate_for_product(entry)
        if action == "发布产品" and gate["发布准入"] == quality_gate.GATE_FROZEN:
            return None, gate["冻结原因"]

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._present(entry), f"数据产品已{action}"

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(entry)
        gate = quality_gate.gate_for_product(entry)
        snapshot.update(quality_gate.summarize_gate(gate))
        snapshot["产品准入结果"] = gate["准入结果"]
        return snapshot
