# 化工工艺计算 Agent（Plan & Execute）

一个可演示、可检查、可扩展的化工工艺计算 Agent Demo：

**LLM 制定计划 → 人工审批 → 确定性工具逐步执行 → 失败自动重规划 → 生成带步骤引用的报告**

- 后端：Python 3.13 + FastAPI + LangGraph（`interrupt` 人工审批）+ SQLite
- 前端：Streamlit（计划卡片、步骤时间线、事件流、历史记录）
- LLM：可切换 Mock（离线）/ DeepSeek / Claude
- 计算：全部由本地纯函数工具完成，不依赖模型"心算"

---

## 1. 快速开始

```bash
# 1) 安装依赖（项目根目录）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt

# PowerShell / cmd 请改用：
# .venv\Scripts\python.exe -m pip install -r requirements.txt

# 2) 一键启动（后端 8000 + 前端 8501，并自动打开浏览器）
.venv/Scripts/python.exe run_demo.py
```

也可以分别启动：

```bash
# 后端
PYTHONPATH=backend .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（另开一个终端）
.venv/Scripts/python.exe -m streamlit run frontend/app.py --server.port 8501
```

打开 <http://127.0.0.1:8501>，从左侧选择示例问题即可体验完整流程。
后端 API 文档：<http://127.0.0.1:8000/docs>。

默认 `LLM_PROVIDER=mock`，**无需任何 API Key**，可离线跑通 6 个内置示例。

---

## 2. 配置真实 LLM

复制 `.env.example` 为 `.env`（项目已自带一份 `.env`，直接编辑即可）。

### DeepSeek

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### Claude

```dotenv
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5
# 使用中转网关时填写，留空走官方地址
ANTHROPIC_BASE_URL=
```

修改 `.env` 后重启后端。Mock 模式只识别内置示例问题；真实 LLM 可自由理解新的化工计算问题。

### 代理设置

```dotenv
# false：LLM 请求直连，忽略操作系统代理（默认）
# true ：走操作系统代理，适合需要代理访问 Anthropic 的网络环境
LLM_USE_SYSTEM_PROXY=false
```

Windows 上如果系统代理（如 `127.0.0.1:7890`）没有运行，Python 的 `requests/httpx` 会继承系统代理并报 `SSL: UNEXPECTED_EOF_WHILE_READING`。DeepSeek 国内可直连，保持 `false` 即可；访问 Claude 且代理正常时改为 `true`。

---

## 3. 演示流程

1. 输入问题，例如：`将 50 m³/h 的水从 20°C 加热到 80°C，热源为 120°C 饱和蒸汽，K=800 W/(m²·K)，求换热面积。`
2. **Planner** 输出结构化计划，界面展示每一步的工具、参数和预期产出。
3. 页面停在 `WAITING_APPROVAL`，由你点击 **批准并执行**，或填写意见 **驳回并重新规划**。
4. **Executor** 按步骤调用确定性工具；步骤之间可用 `${s1.density_kg_m3}` 引用前序结果。
5. 某一步失败时，**Replanner** 只替换剩余步骤，已成功的结果保留；最多重规划 2 次。
6. **Finalizer** 汇总结果，生成带步骤引用的 Markdown 报告。

内置示例：

| 示例 | 涉及工具 |
|---|---|
| 水加热换热面积 | 物性查询、显热负荷、LMTD 换热面积 |
| 苯加氢物料衡算 | 反应进度、出口组成、产物物性 |
| 泵功率估算 | 物性查询、泵功率 |
| 理想气体体积流量 | PV=nRT |
| 管径流速校核 | 管径/流速 |
| 压力单位换算 | 单位换算 |

---

## 4. 架构

```text
Streamlit UI
  │ POST /api/runs、/approve；GET /api/runs/{id} 轮询
  ▼
FastAPI
  │ 后台任务
  ▼
LangGraph 状态机
  planner ──► approval（interrupt，等待人工审批）
                 │ 批准                      │ 驳回
                 ▼                           ▼
              executor ──失败──► replanner ──► executor
                 │ 全部成功
                 ▼
              finalizer ──► COMPLETED / FAILED

SQLite：runs / steps / events + LangGraph checkpoints
工具层：物性、衡算、传热、流体、理想气体、单位换算
```

关键设计：

- **审批通过 LangGraph `interrupt()` + SQLite checkpointer 实现**，`thread_id = run_id`，页面刷新或进程重启后仍可恢复运行状态。
- **执行器是纯确定性代码**：Planner 只能从工具注册表选工具，参数先做 Pydantic 校验再执行；LLM 不参与单步数值计算。
- **步骤间引用**：`${s1.density_kg_m3}` 在 executor 中解析为前序步骤结果，未解析则步骤失败并触发重规划。
- **UI 轮询而非 SSE**：Streamlit 每 0.8 秒调用 `GET /api/runs/{id}?after_event_id=N` 增量拉取，避免 Streamlit 与 SSE 的兼容问题。
- **所有状态落库**：`runs/steps/events` 是 UI 的事实来源，刷新页面可从左侧历史记录完整恢复。

### 目录

```text
backend/app/
  agent/        LangGraph 图、planner/executor/replanner/finalizer、refs
  api/          FastAPI 路由
  db/           SQLite 建表与仓储
  llm/          Mock / DeepSeek / Claude 适配层
  tools/        化工计算工具与物性数据
  schemas/      Pydantic 计划与请求模型
frontend/
  app.py        Streamlit 页面
  api_client.py 后端调用封装
  components/   计划卡片、步骤时间线、事件流
backend/tests/  27 个测试（工具、引用、状态机、API）
```

---

## 5. API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/runs` | 创建运行并后台生成计划 |
| POST | `/api/runs/{id}/approve` | `{"action":"approve"}` 或 `{"action":"reject","feedback":"..."}` |
| GET | `/api/runs/{id}?after_event_id=N` | 运行状态、步骤、增量事件（UI 轮询） |
| GET | `/api/runs?limit=20` | 历史运行 |
| GET | `/api/tools` | 工具目录与参数 Schema |
| GET | `/api/examples` | 内置示例问题 |
| GET | `/api/health` | 健康检查与当前 LLM |

---

## 6. 测试

```bash
.venv/Scripts/python.exe -m pytest
```

当前：**27 passed**。覆盖：

- 全部化工工具的正常与异常输入
- `${step.path}` 引用解析
- 完整状态机：规划 → 审批中断 → 执行 → 报告
- 驳回重规划
- 步骤失败 → 重规划放弃 → FAILED
- FastAPI 创建、审批、幂等冲突、404

---

## 7. 已知限制（Demo 边界）

- 物性为常用物质的简化常数（25°C/1 atm 附近），未覆盖非理想体系、温度依赖、污垢热阻、压降与设备选型校核。
- 计划为线性步骤，暂不支持并行分支与 DAG 依赖。
- 运行时对 LangGraph 调用加进程内锁，SQLite checkpointer 适合单机演示，不适合高并发生产。
- 无登录、权限与多租户隔离，仅用于本地 Demo。
- Mock 模式只是离线演示与测试替身，不具备通用问题理解能力。
