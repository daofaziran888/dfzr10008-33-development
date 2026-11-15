"""数据质量反馈业务规则：轨迹记录、状态流转、字段校验与筛选口径都收在这里。

两类规则在这里落地：
1. 每条反馈维护一条按时间排序的轨迹，状态与严重程度在事件发生时各留一份快照，
   后续修改不会覆盖历史判定；
2. 未解决的高严重度反馈会冻结对应产品的认证准入与发布准入，判定口径统一走
   ``app.services.quality_gate``。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import quality_gate
from app.store import store

MODULE = "feedback"
REQUIRED_FIELDS = ["反馈编号", "数据产品", "反馈类型"]
STATUS_ORDER = ["待处理", "处理中", "已解决", "已关闭"]

# 动作 -> (目标状态, 允许的来源状态)
ACTION_RULES: dict[str, tuple[str, set[str]]] = {
    "开始处理": ("处理中", {"待处理"}),
    "补充解决轨迹": ("处理中", {"待处理", "处理中"}),
    "标记解决": ("已解决", {"待处理", "处理中"}),
    "关闭反馈": ("已关闭", {"已解决"}),
}
NEGATIVE_ACTIONS = ["驳回反馈", "重新打开"]

RESOLUTION_FIELDS = ("解决轨迹", "解决结论")
RESOLUTION_REQUIRED_MESSAGE = "关闭反馈前必须填写解决轨迹，说明问题定位、修复动作与验证结果"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _dedupe_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    """同一产品、同一类型、同一内容的反馈视为重复提交。

    产品统一折算成产品编号，避免同一产品用名称提交时被当成另一条反馈。
    """
    product = _text(entry.get("产品编号")) or _text(entry.get("数据产品"))
    resolved = quality_gate.resolve_product(product)
    if resolved is not None:
        product = _text(resolved.get("产品编号")) or product
    return (
        product,
        _text(entry.get("反馈类型")),
        " ".join(_text(entry.get("反馈内容")).split()),
    )


class FeedbackService:
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
                if keyword in _text(row.get("反馈编号"))
                or keyword in _text(row.get("数据产品"))
                or keyword in _text(row.get("产品编号"))
            ]
        if status:
            rows = [row for row in rows if quality_gate.entry_status(row) == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._present(entry) if entry is not None else None

    def find_by_feedback_no(self, feedback_no: str) -> dict[str, Any] | None:
        for row in store.rows(MODULE):
            if _text(row.get("反馈编号")) == _text(feedback_no):
                return row
        return None

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], bool]:
        """登记反馈。重复提交同一反馈时只保留最早那条轨迹。"""
        missing = [field for field in REQUIRED_FIELDS if not _text(values.get(field))]
        if missing:
            return None, missing, False

        candidate = {
            "产品编号": _text(values.get("产品编号")) or _text(values.get("数据产品")),
            "数据产品": _text(values.get("数据产品")),
            "反馈类型": _text(values.get("反馈类型")),
            "反馈内容": _text(values.get("反馈内容")),
        }
        key = _dedupe_key(candidate)
        for row in store.rows(MODULE):
            if _dedupe_key(row) == key:
                return self._present(row), [], True

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "反馈编号": _text(values.get("反馈编号")),
            "产品编号": candidate["产品编号"],
            "数据产品": candidate["数据产品"],
            "反馈类型": candidate["反馈类型"],
            "反馈内容": candidate["反馈内容"],
            "严重程度": _text(values.get("严重程度")) or "中",
            "处理状态": STATUS_ORDER[0],
            "反馈人": _text(values.get("反馈人")) or "匿名反馈",
            "反馈时间": _text(values.get("反馈时间")) or _now(),
            "状态": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
            "解决轨迹": "",
            "解决人": "",
            "解决时间": "",
            "关闭时间": "",
            "轨迹": [],
            "严重度判定历史": [],
        }
        entry["严重度判定历史"].append({
            "时间": entry["反馈时间"],
            "严重程度": entry["严重程度"],
            "判定人": entry["反馈人"],
            "说明": "提交反馈时判定",
        })
        self._append_event(
            entry,
            action="提交反馈",
            operator=entry["反馈人"],
            at=entry["反馈时间"],
            note=entry["反馈内容"] or "反馈已登记",
            status=STATUS_ORDER[0],
        )
        self._sync_flags(entry)
        rows.append(entry)
        return self._present(entry), [], False

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"反馈记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据质量反馈可执行范围"

        target, sources = ACTION_RULES[action]
        current = quality_gate.entry_status(entry)
        if current not in sources:
            return None, f"反馈记录当前为「{current}」，不能执行「{action}」"

        operator = (
            _text(values.get("操作人"))
            or _text(values.get("处理人"))
            or _text(values.get("反馈人"))
            or "值班管理员"
        )
        resolution = ""
        for field in RESOLUTION_FIELDS:
            resolution = _text(values.get(field))
            if resolution:
                break

        if action == "关闭反馈" and not (resolution or _text(entry.get("解决轨迹"))):
            return None, RESOLUTION_REQUIRED_MESSAGE

        # 严重程度不允许被后续修改覆盖：保留原判定，追加一次判定历史说明。
        requested_severity = _text(values.get("严重程度"))
        if requested_severity and requested_severity != quality_gate.entry_severity(entry):
            history = entry.setdefault("严重度判定历史", [])
            history.append({
                "时间": _now(),
                "严重程度": quality_gate.entry_severity(entry),
                "判定人": operator,
                "说明": f"拒绝将严重程度由「{quality_gate.entry_severity(entry)}」改为"
                        f"「{requested_severity}」，历史判定保持不变",
            })

        note = _text(values.get("说明")) or _text(values.get("remark")) or resolution
        if action == "补充解决轨迹" and not resolution:
            return None, "补充解决轨迹需要填写解决轨迹内容"

        if resolution:
            entry["解决轨迹"] = resolution
            entry["解决人"] = operator
            entry["解决时间"] = _now()

        if action == "关闭反馈":
            entry["关闭时间"] = _now()

        entry["处理状态"] = target
        entry["status"] = target
        self._append_event(
            entry,
            action=action,
            operator=operator,
            note=note or f"反馈记录已{action}",
            status=target,
        )
        self._sync_flags(entry)

        message = f"反馈记录已{action}"
        if action == "关闭反馈":
            message = "反馈记录已关闭，解决轨迹已归档"
        return self._present(entry), message

    def trajectory(
        self,
        *,
        product: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """质量反馈轨迹视图：按反馈时间串起处理过程，并带出产品准入结果。"""
        rows = store.rows(MODULE)
        if product:
            rows = [
                row
                for row in rows
                if product in _text(row.get("数据产品"))
                or product in _text(row.get("产品编号"))
            ]
        if severity:
            rows = [row for row in rows if quality_gate.entry_severity(row) == severity]
        if status:
            rows = [row for row in rows if quality_gate.entry_status(row) == status]
        rows = sorted(rows, key=lambda row: _text(row.get("反馈时间")))
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._present(row) for row in rows[start:start + size]], total

    # -- 内部工具 ---------------------------------------------------------
    def _append_event(
        self,
        entry: dict[str, Any],
        *,
        action: str,
        operator: str,
        note: str,
        status: str,
        at: str | None = None,
    ) -> None:
        """追加时间轴事件，严重程度取事件发生当时的值，形成不可覆盖的快照。"""
        events = entry.setdefault("轨迹", [])
        events.append({
            "时间": at or _now(),
            "动作": action,
            "处理状态": status,
            "严重程度": quality_gate.entry_severity(entry),
            "操作人": operator,
            "说明": note,
        })

    def _sync_flags(self, entry: dict[str, Any]) -> None:
        """把当前状态同步到列表用的 pending/abnormal 标记。"""
        status = quality_gate.entry_status(entry)
        entry["status"] = status
        entry["pending"] = quality_gate.is_unresolved(entry)
        entry["abnormal"] = quality_gate.is_unresolved(entry) and quality_gate.is_high_severity(entry)

    def _present(self, entry: dict[str, Any]) -> dict[str, Any]:
        """输出给接口的反馈记录：补齐处理状态口径、时间轴与产品准入结果。"""
        snapshot = dict(entry)
        events = [dict(event) for event in entry.get("轨迹", [])]
        if not events:
            events = [{
                "时间": _text(entry.get("反馈时间")) or _now(),
                "动作": "提交反馈",
                "处理状态": quality_gate.entry_status(entry),
                "严重程度": quality_gate.entry_severity(entry),
                "操作人": _text(entry.get("反馈人")) or "匿名反馈",
                "说明": _text(entry.get("反馈内容")) or "反馈已登记",
            }]
        events.sort(key=lambda event: _text(event.get("时间")))
        snapshot["轨迹"] = events
        snapshot["时间轴"] = events
        snapshot["处理状态"] = quality_gate.entry_status(entry)
        snapshot["严重程度"] = quality_gate.entry_severity(entry)
        snapshot["是否未解决"] = quality_gate.is_unresolved(entry)
        snapshot["高严重度未解决"] = (
            quality_gate.is_unresolved(entry) and quality_gate.is_high_severity(entry)
        )
        snapshot["关联产品编号"] = _text(entry.get("产品编号")) or _text(entry.get("数据产品"))
        snapshot["产品准入"] = quality_gate.gate_for_product(
            _text(entry.get("产品编号")) or _text(entry.get("数据产品"))
        )
        snapshot["解决结论"] = _text(entry.get("解决轨迹"))
        return snapshot
