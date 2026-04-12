# 决策流程与第2项改造指南

目标：先意图分析，再分离轻度对话和重度需求，且不破坏当前可用功能。

## 1) 目标流程

```text
Request
  -> Build TurnContext
  -> DecisionEngine.decide(context)
    -> route=light_chat: fast path
    -> route=heavy_pipeline: full path
  -> Persist minimal session history
  -> Return response
```

## 2) 轻重路径定义

- light_chat:
  - 注入 persona + 近期短上下文。
  - 禁止检索、禁止联网搜索、禁止偏好/进度查库。
  - 直接调用 smart_model_dispatch。
- heavy_pipeline:
  - 允许偏好和进度查询。
  - 允许检索与联网搜索。
  - 可执行记忆信号提取与持久化。

## 3) 你执行第2项的具体步骤（手改）

目标文件: server/services/chat_service.py

步骤 1: 在 imports 区新增

```python
from server.orchestration.decision_engine import DecisionEngine, RouteMode, TurnContext
```

步骤 2: 在模块级新增单例

```python
DECISION_ENGINE = DecisionEngine()
```

步骤 3: 在 handle_chat 开头构建上下文并决策

```python
query = get_latest_user_query(merged_messages)
has_attachments = bool(payload.image_url or payload.audio_url or payload.files)
turn_ctx = TurnContext(
    user_text=query,
    route_mode=RouteMode.AUTO,
    use_retrieval=bool(payload.use_retrieval),
    use_web_search=bool(payload.use_web_search),
    has_attachments=has_attachments,
)
turn_decision = DECISION_ENGINE.decide(turn_ctx)
```

步骤 4: 按决策分支

- if turn_decision.go_light:
  - 跳过 list_user_preferences、list_learning_progress、list_user_reminders。
  - 跳过 extract_memory_signals 和 persist_memory_signals。
  - 跳过 retrieve_chunks 和 web_search。
  - 仅保留 inject_system_prompt + optional short memory。
- else:
  - 维持当前完整逻辑。

步骤 5: 在日志中打印决策结果

```python
logging.info(
    "decision route=%s intent=%s reason=%s confidence=%.2f rule=%s",
    turn_decision.route,
    turn_decision.intent,
    turn_decision.reason,
    turn_decision.confidence,
    turn_decision.matched_rule,
)
```

步骤 6: 为流式入口 create_chat_stream_response 同步接入

- 复用同一套 TurnContext。
- light_chat 走现有流式快速路径。
- heavy_pipeline 允许 fallback 到非流式，但要标记 route=heavy_pipeline。

## 4) 最小回归清单

- Case A: 纯闲聊（你好，今天怎么样）
  - 预期: route=light_chat，延迟下降。
- Case B: 检索问答（基于资料回答）
  - 预期: route=heavy_pipeline，引用仍可用。
- Case C: 明确任务（帮我改代码并运行测试）
  - 预期: route=heavy_pipeline。
- Case D: 带图片/音频输入
  - 预期: route=heavy_pipeline。

## 5) 风险与兜底

- 若误判导致结果过浅:
  - 临时策略: 对低置信度 light_chat（confidence < 0.75）直接升级 heavy_pipeline。
- 若 heavy 路径过慢:
  - 先返回一句短 ack，再异步执行。
- 若线上出现抖动:
  - 增加 route 命中统计与失败率监控，按规则热修复。
