# 数据产品与API工厂

面向数据产品经理与开发者的数据产品快速构建平台。覆盖数据产品定义、API接口生成、数据模型封装、产品版本管理、调用配额控制、文档自动生成、产品市场分发与使用效果追踪的完整数据产品链路。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 数据产品定义 | `product` | 数据产品 | 产品编号、产品名称、产品类型 |
| API接口生成 | `apigen` | 接口配置 | 接口编号、接口名称、请求方法 |
| 数据模型封装 | `datapack` | 模型封装 | 封装编号、封装名称、原始数据源 |
| 产品版本管理 | `version` | 产品版本 | 版本编号、产品名称、版本号 |
| 调用配额控制 | `quota` | 配额配置 | 配置编号、调用方名称、每秒上限 |
| 文档自动生成 | `docgen` | 文档模板 | 模板编号、文档标题、目标接口 |
| 产品市场分发 | `market` | 市场商品 | 商品编号、商品名称、所属产品 |
| 使用效果追踪 | `usage` | 使用记录 | 记录编号、产品名称、调用方名称 |
| 产品沙箱测试 | `sandbox` | 沙箱实例 | 实例编号、测试产品、测试参数 |
| 数据管线编排 | `pipeline` | 管线节点 | 节点编号、节点名称、上游节点 |
| 数据筛选引擎 | `filter` | 筛选模板 | 模板编号、模板名称、目标数据源 |
| 场景化配置模板 | `scene` | 场景模板 | 模板编号、模板名称、适用场景 |
| 实时数据推送 | `realtime` | 推送通道 | 通道编号、通道名称、数据源名称 |
| 跨源数据关联 | `crossref` | 关联规则 | 规则编号、主数据源、关联数据源 |
| 数据质量反馈 | `feedback` | 反馈记录 | 反馈编号、数据产品、反馈类型 |
| 数据产品认证 | `badge` | 认证记录 | 认证编号、产品名称、认证类型 |

## 质量反馈与产品准入

数据质量反馈按时间维护一条轨迹（`轨迹` / `时间轴`），每个事件都带当时的处理状态与
严重程度快照；`严重度判定历史` 追加记录，不覆盖旧判定。

- 未解决的高严重度反馈会冻结对应产品的认证准入与发布准入：
  产品定义接口返回 `未解决反馈数量`、`准入结果`、`冻结原因`、`阻断反馈`，
  认证接口返回 `认证入口`；`GET /api/badge/acceptance?product=<产品编号或名称>`
  用于认证入口的准入检查。
- 反馈动作为 `开始处理`、`补充解决轨迹`、`标记解决`、`关闭反馈`；
  关闭反馈必须填写 `解决轨迹`，否则动作被拦下并说明原因。
- 同一产品、同一反馈类型、同一反馈内容重复提交时只保留最早一条轨迹，
  登记接口返回 `duplicate: true` 并指向已有记录。
- 轨迹视图：`GET /api/feedback/trajectory?product=&severity=&status=`。

样例：`FB-0002`（产品 `PROD-0007`，字段缺失，严重程度高，反馈人林晓，
2026-11-02 09:18，周宁补充解决轨迹）在处理中期间产品认证入口显示冻结，
产品定义未解决反馈数量为 1；标记解决后数量归零，认证可继续。

测试：`cd backend && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest tests`

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用
