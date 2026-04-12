# 体验运行手册（2 小时）

目的：验证记忆注入、偏好持久化、检索与提醒等关键路径的稳定性与体验质量。

## 准备
- 激活虚拟环境并安装依赖（若尚未安装）。
- 启动服务（在项目根）：
```powershell
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
- 打开一个终端用于观察日志输出。

## 体验流程（总时长约 120 分钟）

### 前 5 分钟：环境与账号准备
- 创建或选择测试用户 `test_user`。
- 清理旧会话（若需要），用新的 `session_id`（如 `s_run1`）。

### 任务 A — 偏好与短期记忆测试（20 分）
1. 发送一条偏好声明，触发偏好提取与持久化：
```powershell
curl -X POST "http://127.0.0.1:8000/chat" -H "Content-Type: application/json" -d "{\"user_id\":\"test_user\",\"session_id\":\"s_run1\",\"messages\":[{\"role\":\"user\",\"content\":\"我喜欢用英文回答\"}]}"
```
2. 验证偏好已写入：
```powershell
python -c "from repo import list_user_preferences; print(list_user_preferences('test_user'))"
```
3. 提问并确认助手使用偏好（语言/风格）：
```powershell
curl -X POST "http://127.0.0.1:8000/chat" -H "Content-Type: application/json" -d "{\"user_id\":\"test_user\",\"session_id\":\"s_run1\",\"messages\":[{\"role\":\"user\",\"content\":\"下周我有考试，给我两条复习建议\"}]}"
```

### 任务 B — 记忆检索注入与相关性筛选（30 分）
1. 模拟写入若干记忆（通过对话触发多条记忆或用 DB 写入测试数据）。
2. 发送与某记忆高度相关的问题，观察注入的 system 消息是否仅包含相关片段（查看服务日志或在 `server.py` 临时打印 `final_messages`）。
3. 示例请求：
```powershell
curl -X POST "http://127.0.0.1:8000/chat" -H "Content-Type: application/json" -d "{\"user_id\":\"test_user\",\"session_id\":\"s_run1\",\"messages\":[{\"role\":\"user\",\"content\":\"请用我偏好的语言给我一个复习计划（与上次提到的课程相关）\"}], \"use_retrieval\": false}"
```

### 任务 C — 资料上传与检索（30 分）
1. 上传一份小文本资料（模拟课程资料）：
```powershell
curl -F "course_id=1" -F "title=testdoc" -F "file=@小测验.txt" http://127.0.0.1:8000/materials/upload
```
2. 发起检索型问答（`use_retrieval=true`），确认回复包含“引用”格式：
```powershell
curl -X POST "http://127.0.0.1:8000/chat" -H "Content-Type: application/json" -d "{\"user_id\":\"test_user\",\"session_id\":\"s_run1\",\"use_retrieval\":true,\"document_id\":1,\"messages\":[{\"role\":\"user\",\"content\":\"请基于上传资料解释第3段的要点\"}]}"
```

### 任务 D — 提醒与主动推送（20 分）
1. 在会话中触发一个带日期的进度声明（例如：“5月10日有测验”），使系统写入学习进度并设置 `next_review_at`。
2. 手动运行或等待 `reminder_worker` 触发，验证 `list_due_reminders` 返回并 `mark_reminder_sent` 被调用，查看日志记录。

## 记录问题（随时填写）
- 使用下面表格记录遇到的问题，方便后续修复与验证回归。

### 问题记录模板（CSV/表格列）
- 时间 — 场景 — 操作步骤（可复现） — 期望行为 — 实际行为 — 严重度（低/中/高） — 备注 / 日志片段

示例：
- 2026-03-24 10:12 — 偏好写入 — 发送“我喜欢用英文回答” — 偏好应写入 DB — 未写入 — 高 — repo.list_user_preferences 返回空；错误日志：...

## 调试检查命令（常用）
- 校验服务健康：
```powershell
curl http://127.0.0.1:8000/health
```
- 查看用户偏好：
```powershell
python -c "from repo import list_user_preferences; import json; print(json.dumps(list_user_preferences('test_user'), ensure_ascii=False, indent=2))"
```
- 列出近期提醒：
```powershell
python -c "from repo import list_user_reminders; import json; print(json.dumps(list_user_reminders('test_user'), ensure_ascii=False, indent=2))"
```

## 结束与产出（最后 10 分钟）
- 汇总问题表，标注高优先级项（至少列出 3 个必须修）；
- 如果需要回归测试，记录重现步骤与请求/响应示例。


---

*保存位置： `docs/experience_runbook.md`*
