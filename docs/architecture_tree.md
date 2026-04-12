# 架构树（清晰版）

目标：把低延迟对话与重任务执行解耦，保证路径清晰、职责明确、可观测。

## 1) 目标目录树

```text
workspace_ai_assistant/
  api/
    routers/
      chat_router.py
      companion_router.py
      speech_router.py
      health_router.py
  orchestration/
    intent_router.py
    decision_engine.py
  dialogue/
    roleplay_engine.py                  # 预留：轻对话呈现层
  agent_core/
    planner.py                          # 预留：重任务规划
    executor.py                         # 预留：重任务执行
  memory/
    short_term_store.py                 # 预留：短期上下文
    summary_store.py                    # 预留：压缩摘要
    long_term_store.py                  # 预留：长期偏好与进度
  services/
    chat_service.py                     # 当前主入口（待做轻重分流）
    model_service.py
    embedding_service.py
    speech_service.py
  infra/
    repo.py                             # 数据访问
    db.py
    queue.py                            # 预留：后台任务队列
    metrics.py                          # 预留：埋点指标
  config.py
  server.py
  docs/
    architecture_tree.md
    sequence_decision_flow.md
    experience_runbook.md
```

## 2) 每层职责边界

- api.routers: 参数校验、协议转换、响应结构，禁止业务决策。
- orchestration: 意图识别、路由决策、调用轻链路或重链路。
- dialogue: 只处理轻对话输出风格，不做工具调用。
- agent_core: 只处理复杂任务，不承担对话润色。
- memory: 记忆读写策略与分层存储，不直接控制路由。
- services: 业务能力实现，按模块拆分。
- infra: 外部资源访问与通用运行支撑。

## 3) 数据与控制流

- 控制流: Router -> Orchestration -> Dialogue or AgentCore -> Router Response。
- 数据流: User Input -> Session Context -> Decision -> Execution -> Memory Writeback。

## 4) 演进顺序（建议）

- 阶段 A: 完成意图路由与决策引擎接入。
- 阶段 B: 把 chat_service 主链路拆成 light 和 heavy 两个函数。
- 阶段 C: 引入任务队列与任务状态查询。
- 阶段 D: 增加观测指标与误判回放集。

## 5) 关键原则

- 低延迟路径默认无检索、无查库、无工具调用。
- 重任务路径必须可追踪（job_id、阶段、耗时、错误）。
- 记忆写入做节流，避免每轮全量写入。
- 优先保证路径稳定，再做模型细节优化。
