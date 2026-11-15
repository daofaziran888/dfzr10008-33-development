"""数据产品认证业务规则：状态流转、字段校验、筛选口径与质量准入都收在这里。

认证是否可继续由对应产品的质量准入决定：产品存在未解决的高严重度反馈时，
认证入口显示冻结，通过认证的动作会被拦下并说明阻断反馈。
"""
from __future__ import annotations

from typing import Any

from app.services import quality_gate
from app.store import store

MODULE = "badge"
REQUIRED_FIELDS = ["认证编号", "产品名称", "认证类型"]
STATUS_ORDER = ["申请中", "已通过", "已驳回", "已过期"]
ACTION_RULES = {"通过认证": "申请中", "驳回认证": "已通过", "延期认证": "已过期"}
NEGATIVE_ACTIONS = ["驳回认证"]


class BadgeService:
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
                if keyword in str(row.get("认证编号", ""))
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
            return None, f"认证记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据产品认证可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        gate = quality_gate.gate_for_product(str(entry.get("产品名称") or ""))
        if action == "通过认证" and gate["认证准入"] == quality_gate.GATE_FROZEN:
            return None, gate["冻结原因"]

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._present(entry), f"认证记录已{action}"

    def acceptance(self, product: str) -> dict[str, Any]:
        """认证入口的准入检查：冻结时给出阻断反馈与原因。"""
        gate = quality_gate.gate_for_product(product)
        return {
            "产品": product,
            "准入结果": gate["准入结果"],
            "认证入口": gate["认证准入"],
            "冻结原因": gate["冻结原因"],
            "未解决反馈数量": gate["未解决反馈数量"],
            "高严重度未解决数量": gate["高严重度未解决数量"],
            "阻断反馈": gate["阻断反馈"],
        }

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(entry)
        gate = quality_gate.gate_for_product(str(entry.get("产品名称") or ""))
        snapshot.update(quality_gate.summarize_gate(gate))
        snapshot["认证入口"] = gate["认证准入"]
        return snapshot
