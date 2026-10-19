# 化工工艺计算 Agent 设计说明

日期：2026-10-19

## 目标

构建一个可演示的化工计算 Agent，核心不是“让 LLM 直接算数”，而是展示一条可控的 Plan & Execute 链路：

1. LLM 只负责把自然语言问题转成结构化计划；
2. 计划必须经人工审批才能执行；
3. 每一步调用确定性工具，参数可校验、结果可追溯；
4. 失败后可自动重规划剩余步骤；
5. 最终报告只能引用实际计算结果。

## 角色划分

| 角色 | 使用 LLM | 职责 |
|---|---|---|
| Planner | 是 | 读取工具目录与问题，生成 1~8 步计划 |
| Approval | 否 | LangGraph `interrupt()` 暂停，等待批准或驳回意见 |
| Executor | 否 | 解析 `${sN.path}` 引用、校验参数、执行工具 |
| Replanner | 是 | 失败后替换剩余步骤，或明确放弃 |
| Finalizer | 是 | 基于已产生的结果写报告 |

## 状态机

```
CREATED → PLANNING → WAITING_APPROVAL → EXECUTING → COMPLETED
                ↑           │ 驳回            │ 失败
                └───────────┘                 ▼
                                         REPLANNING → EXECUTING
                                              │ 放弃/超限
                                              ▼
                                            FAILED
```

- 审批中断与恢复由 LangGraph checkpointer 持久化，`thread_id = run_id`。
- 重规划上限默认 2 次；计划被驳回上限默认 3 次。
- 执行器按线性顺序推进 `cursor`，暂不支持 DAG / 并行。

## 数据模型

- `runs`：问题、状态、计划快照、最终回答、错误、重规划次数。
- `steps`：每一步的工具、参数、状态、结果、耗时。
- `events`：自增 ID 的事件流，UI 用 `after_event_id` 增量轮询。
- LangGraph checkpoint 单独存于 `data/checkpoints.db`。

## 步骤间数据传递

Planner 可在参数中写 `"${s1.density_kg_m3}"`；Executor 在执行前递归解析引用。解析失败会使当前步骤失败，进入重规划。这样既避免 LLM 在计划阶段编造中间数值，也避免执行阶段再调用一次 LLM 填参数。

## 工具边界

工具是纯函数：Pydantic 输入模型 + 确定性计算 + 结构化输出。工具不访问网络、不调用 LLM、不读写数据库。工具异常统一转换为 `ToolError`，由 Executor 记录并触发重规划。

当前工具：物性查询、物质列表、摩尔质量、反应物料衡算、显热负荷、LMTD 换热面积、管径、流速、泵功率、理想气体、单位换算。

## 失败处理

- 规划失败：运行直接进入 FAILED，并返回可读错误。
- 工具参数/引用/计算失败：步骤标记 failed，事件落库，进入 Replanner。
- 重规划失败、放弃或超限：保留已完成结果，Finalizer 输出部分结果并说明原因。
- 后台任务顶层异常：捕获后写回 FAILED，避免 UI 永久停留在“执行中”。

## UI 交互

Streamlit 不使用 SSE，而是轮询 `GET /api/runs/{id}`：

1. 创建运行后轮询到 `WAITING_APPROVAL`；
2. 展示计划卡片与审批按钮；
3. 批准/驳回后继续轮询到下一个审批点或终态；
4. 刷新页面时从左侧历史记录恢复，所有展示数据来自数据库。

## 取舍

选择 LangGraph 而不是自研编排器，是为了获得 `interrupt` + checkpointer 这一套成熟的人工审批基础设施；代价是引入较重的依赖。工具层、LLM 适配层与 UI 均与 LangGraph 解耦，后续替换编排层不需要改动计算逻辑。
