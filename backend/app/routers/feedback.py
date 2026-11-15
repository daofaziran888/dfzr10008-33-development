"""数据质量反馈接口：维护反馈记录，覆盖开始处理、补充解决轨迹、标记解决、关闭反馈等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/api/feedback", tags=["数据质量反馈"])

service = FeedbackService()

LIST_FIELDS = ["反馈编号", "数据产品", "反馈类型", "反馈内容", "严重程度", "处理状态", "反馈人", "反馈时间"]
STATUSES = ["待处理", "处理中", "已解决", "已关闭"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按反馈编号或数据产品检索"),
    status: str | None = Query(default=None, description="待处理、处理中、已解决、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按反馈编号与状态过滤数据质量反馈列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/trajectory", response_model=PageResult[dict])
def list_trajectory(
    product: str | None = Query(default=None, description="按数据产品名称或产品编号检索"),
    severity: str | None = Query(default=None, description="按严重程度过滤：高、中、低"),
    status: str | None = Query(default=None, description="待处理、处理中、已解决、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """质量反馈轨迹视图：按反馈时间排列，串起反馈类型、严重程度、处理过程与产品准入结果。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.trajectory(
        product=product, severity=severity, status=status, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id:int}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条反馈记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"反馈记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条反馈记录；重复提交同一反馈时只保留最早那条轨迹。

    缺字段时说明原因而不是静默丢弃；重复提交返回 duplicate=true 指向已有记录。
    """
    entry, missing, duplicate = service.create_entry(payload.resolved_values())
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if duplicate:
        return ActionResult(
            ok=True,
            message=f"重复提交的反馈已合并到 {entry.get('反馈编号') or '已有反馈'}，未新增轨迹",
            entry=entry,
            duplicate=True,
        )
    return ActionResult(ok=True, message="反馈记录已登记", entry=entry)


@router.post("/{entry_id:int}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条反馈记录执行开始处理、补充解决轨迹、标记解决、关闭反馈。

    关闭反馈必须带解决轨迹；不允许的动作会被拦下并说明原因。
    """
    values = payload.resolved_values()
    action = str(values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出数据质量反馈清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "feedback", "total": total, "items": items}
