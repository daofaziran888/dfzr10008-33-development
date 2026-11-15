"""质量反馈轨迹与产品准入的回归用例。

覆盖样例 FB-0002：未解决期间冻结认证入口、产品定义未解决数为 1；解决后归零；
重复提交不新增轨迹；历史严重度判定不被覆盖；关闭必须写解决轨迹。
"""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed import SEED_ROWS
from app.store import store


@pytest.fixture()
def client() -> TestClient:
    store._tables = {name: copy.deepcopy(rows) for name, rows in SEED_ROWS.items()}
    return TestClient(app)


def _feedback(entry_id: int) -> dict:
    return store.find("feedback", entry_id)


def test_fb_0002_gate_blocks_until_resolved(client: TestClient) -> None:
    response = client.get("/api/feedback/trajectory", params={"product": "PROD-0007"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["反馈编号"] == "FB-0002"
    assert item["反馈类型"] == "字段缺失"
    assert item["严重程度"] == "高"
    assert item["处理状态"] == "处理中"
    assert [event["动作"] for event in item["时间轴"]] == ["提交反馈", "开始处理", "补充解决轨迹"]
    assert item["产品准入"]["准入结果"] == "冻结"

    product = client.get("/api/product/4").json()
    assert product["未解决反馈数量"] == 1
    assert product["认证准入"] == "冻结"
    assert product["发布准入"] == "冻结"

    badge = client.get("/api/badge/4").json()
    assert badge["认证入口"] == "冻结"

    acceptance = client.get("/api/badge/acceptance", params={"product": "PROD-0007"}).json()
    assert acceptance["准入结果"] == "冻结"
    assert acceptance["阻断反馈"][0]["反馈编号"] == "FB-0002"

    blocked = client.post("/api/badge/4/actions", json={"action": "通过认证"})
    assert blocked.json()["ok"] is False
    assert "FB-0002" in blocked.json()["message"]

    blocked_publish = client.post("/api/product/4/actions", json={"action": "发布产品"})
    assert blocked_publish.json()["ok"] is False


def test_resolve_then_unfreeze(client: TestClient) -> None:
    resolved = client.post(
        "/api/feedback/4/actions",
        json={"action": "标记解决", "操作人": "周宁", "解决轨迹": "补充字段映射并回归验证通过"},
    )
    assert resolved.json()["ok"] is True

    product = client.get("/api/product/4").json()
    assert product["未解决反馈数量"] == 0
    assert product["准入结果"] == "可准入"

    badge = client.get("/api/badge/4").json()
    assert badge["认证入口"] == "可准入"
    passed = client.post("/api/badge/4/actions", json={"action": "通过认证"})
    assert passed.json()["ok"] is True

    closed = client.post(
        "/api/feedback/4/actions",
        json={"action": "关闭反馈", "解决轨迹": "字段已补齐，下游对账恢复正常"},
    )
    assert closed.json()["ok"] is True
    entry = _feedback(4)
    assert entry["status"] == "已关闭"
    assert entry["解决轨迹"] == "字段已补齐，下游对账恢复正常"


def test_close_requires_resolution(client: TestClient) -> None:
    response = client.post(
        "/api/feedback/4/actions",
        json={"action": "标记解决", "解决轨迹": "补充字段映射"},
    )
    assert response.json()["ok"] is True
    entry = _feedback(4)
    entry["解决轨迹"] = ""
    blocked = client.post("/api/feedback/4/actions", json={"action": "关闭反馈"})
    assert blocked.json()["ok"] is False
    assert "解决轨迹" in blocked.json()["message"]


def test_duplicate_feedback_keeps_single_trajectory(client: TestClient) -> None:
    before = len(store.rows("feedback"))
    duplicate = client.post(
        "/api/feedback",
        json={
            "values": {
                "反馈编号": "FB-0003",
                "数据产品": "客户主数据服务",
                "产品编号": "PROD-0007",
                "反馈类型": "字段缺失",
                "反馈内容": "客户主数据输出缺少“统一社会信用代码”字段，下游对账无法关联",
                "严重程度": "高",
                "反馈人": "林晓",
                "反馈时间": "2026-11-05 09:20",
            }
        },
    )
    payload = duplicate.json()
    assert payload["ok"] is True
    assert payload["duplicate"] is True
    assert payload["entry"]["反馈编号"] == "FB-0002"
    assert len(store.rows("feedback")) == before

    trajectory = client.get("/api/feedback/trajectory", params={"product": "PROD-0007"}).json()
    assert trajectory["total"] == 1
    # 历史严重度判定保持高，条目本身仍为高。
    assert trajectory["items"][0]["严重程度"] == "高"


def test_severity_history_is_not_overwritten(client: TestClient) -> None:
    client.post(
        "/api/feedback/4/actions",
        json={"action": "补充解决轨迹", "严重程度": "低", "操作人": "周宁", "解决轨迹": "补充字段映射"},
    )
    entry = _feedback(4)
    assert entry["严重程度"] == "高"
    history = entry["严重度判定历史"]
    assert history[0]["严重程度"] == "高"
    assert any("低" in item["说明"] for item in history)
    origin = entry["轨迹"][0]
    assert origin["严重程度"] == "高"


def test_product_unresolved_count_reflects_feedback(client: TestClient) -> None:
    listing = client.get("/api/product", params={"keyword": "PROD-0007"}).json()
    assert listing["items"][0]["未解决反馈数量"] == 1
    assert listing["items"][0]["准入结果"] == "冻结"
