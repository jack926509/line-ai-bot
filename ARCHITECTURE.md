# Lumio 架構文件

本文件描繪模組關係、請求生命週期、Claude tool use 流程、資料庫 schema，與「新增一個功能模組」的標準擴充流程。

---

## 1. 高層分層

```
┌──────────────────────────────────────────────────────────────┐
│  LINE Platform                                                │
│   ↓ webhook                                                   │
├──────────────────────────────────────────────────────────────┤
│  main.py    FastAPI / lifespan / on_text / on_image / on_file │
│             slash 分流  →  features.* 直呼                     │
│             非 slash 文字 →  features.chat.ask_claude          │
├──────────────────────────────────────────────────────────────┤
│  features/  業務模組（一個檔案一個關注點）                     │
│   chat ──┐                                                    │
│          └→ tools.dispatch_tool ──→ 各功能函式                 │
│   todo / note / help / briefing / doc_official / law /        │
│   meeting / trip / search / url_summary / calendar / push     │
│   scheduler / perplexity                                      │
├──────────────────────────────────────────────────────────────┤
│  db/        資料持久層（package，依資源分檔）                  │
│   pool / schema / conversations / todos / notes / ...         │
├──────────────────────────────────────────────────────────────┤
│  config.py  共用實例：logger / line_bot_api / line_bot_blob /  │
│             webhook_handler / ANTHROPIC client                │
└──────────────────────────────────────────────────────────────┘

外部相依：
  LINE Messaging API   Anthropic Claude   Perplexity sonar
  Google Calendar API  PostgreSQL         wttr.in
```

---

## 2. 請求生命週期（文字訊息）

```
1. LINE → POST /webhook
2. main.webhook：簽章存在 → 200 OK + BackgroundTasks.add_task(handler.handle)
3. on_text：
   3.1 db.upsert_subscription(user_id)（自動訂閱）
   3.2 if 文字以 / 開頭 → slash 分流到 features.<feat>.handle_*
   3.3 else → features.chat.ask_claude(user_id, text)
4. ask_claude：
   4.1 載入 history（最後 12 則）→ 加上 cache_control 於最後一則
   4.2 messages.create(model=sonnet-4-6, system=[cached SYSTEM_PROMPT, 動態日期區塊], tools=cached TOOLS)
   4.3 若 stop_reason == "tool_use" → features.tools.dispatch_tool(name, input, user_id)
   4.4 將 tool_result append 進 messages，回到 4.2，最多 3 輪
   4.5 strip_markdown 後回傳
5. _reply：line_bot_api.reply_message(reply_token, TextMessage)
```

關鍵細節：
- Webhook 必須 1 秒內回 200，所以 handler 走 BackgroundTasks
- reply_token 30 秒過期，背景任務內若呼叫 Claude 過久會失敗 → 改 push 補救（push.py 已備好）
- prompt cache：SYSTEM_PROMPT、TOOLS、history 末條皆掛 `cache_control: ephemeral`，命中可省 90% input tokens

---

## 3. 排程（features/scheduler.py）

> **個人版**：所有自動推播通知（早晨簡報、提醒派送）已移除，未來通知系統將重新設計。

| Job | 觸發 | 動作 |
|-----|------|------|
| DB 清理 | CronTrigger(03:30，Asia/Taipei) | `push_log` 90 天 / `processed_messages` 7 天 / `token_usage` 365 天 / `workflows` 30 天 |
| 一次性任務 | `register_one_off(when, callback)` | 預留給未來通知派送 |

`DISABLE_SCHEDULER=1` 可關閉。

---

## 4. Claude tool use 拓樸

```
features/tools.py
├── _WEB_SEARCH ─────────► features.search.web_search
├── _GOOGLE_MAP ────────► features.search.google_map_search
├── _SUMMARIZE_URL ────► features.url_summary.summarize_url
├── _GCAL_*  ──────────► features.calendar.*
├── _TODO_* ───────────► features.todo.*
├── _NOTE_* ───────────► features.note.*
├── _GEN_OFFICIAL_DOC ─► features.doc_official.gen_official_doc
├── _TEMPLATE_* ───────► features.doc_official.template_*
├── _LAW_SEARCH ───────► features.law.law_search
├── _TRIP_*  ──────────► features.trip.*
└── _COMPOSE_WORKFLOW ─► features.workflow.compose_workflow（占位）

dispatch_tool(name, input_dict, user_id) → str
  match name: case 對應呼叫，回字串 → 包成 tool_result block
```

新增工具的標準步驟見第 7 節。

---

## 5. 資料庫 schema（PostgreSQL）

| 表 | 用途 | 主要欄位 |
|----|------|----------|
| `conversations` | 對話記憶（保留 12） | user_id, role, content(JSON), created_at |
| `todos` | 待辦 | user_id, content, done, category, due_date |
| `notes` | 備忘錄 | user_id, content, created_at |
| `subscriptions` | 推播訂閱 | user_id, briefing, brief_time, tz |
| `push_log` | 當日推送去重 | (user_id, kind, ref_date) UNIQUE |
| `doc_templates` | 公文範本 | user_id, name, category, body |
| `trips` | 旅遊行程 | user_id, name, dates, places(JSONB), gcal_ids(JSONB) |
| `workflows` | 多步驟工作流（預留） | name, steps(JSONB), state, next_run_at |

連線：`db.pool.SimpleConnectionPool(1, 5)` → `with get_db() as conn` 自動 commit / rollback / putconn。

---

## 6. 模組命名與責任原則

- **db/**：純 DB 操作，回傳基礎型別（dict / tuple / int / str）。不認識業務概念（不格式化、不 emoji）。
- **features/**：每檔聚焦單一關注點。對外暴露：
  - `<verb>_<noun>(...)` 純資料／業務函式（供 Claude tool 與其他模組呼叫）
  - `handle_<feat>(text, user_id) -> str` slash command 入口（若有）
- **features/tools.py**：唯一的 Claude tool schema 與 dispatcher，避免散佈。
- **main.py**：薄殼。只做 webhook、slash 分流、回覆 LINE，不寫業務邏輯。
- **config.py**：所有環境變數、共用實例的單一出口。其他檔案不直接 `os.getenv`。
- **prompts.py**：純文字常數，不引業務模組（除 `calendar_tw` 提供假日語境）。

---

## 7. 擴充：新增一個功能模組

以「新增空氣品質查詢」為例：

1. **建檔** `features/aqi.py`
   ```python
   def aqi_query(city: str) -> str: ...
   ```
2. **若要 Claude 主動呼叫**，到 `features/tools.py`：
   - 在工具定義區加 `_AQI_QUERY = {"name": "aqi_query", "input_schema": {...}}`
   - 加進 `TOOLS` 列表
   - 在 `dispatch_tool` 的 `match` 加 `case "aqi_query": return aqi.aqi_query(d["city"])`
3. **若要 slash 入口**，在 `main.py` 的 `on_text` 加：
   ```python
   elif t.startswith("/aqi "):
       _reply(event.reply_token, aqi.aqi_query(t[5:].strip()))
   ```
4. **若需資料持久化**，到 `db/` 新增 `aqi_history.py`，並在 `db/__init__.py` re-export，`db/schema.py` 加 `CREATE TABLE`。
5. **若需 Lumio 認識它**，到 `prompts.py` 新增命名常數（如 `_AQI`）並加進 `SYSTEM_PROMPT` 拼接列表。
6. **若需排程**，在 `features/scheduler.py` 加 cron job。

> 原則：每個變更只動 1~3 個檔案；改動超過 3 個 → 重新檢視責任邊界是否切錯。

---

## 8. 已知 trade-off

- **單副本假設**：APScheduler 為 in-process，多副本會重複推送。多副本時應改外部排程或 advisory lock。
- **prompt cache 失效**：每改一次 SYSTEM_PROMPT，前 ~5 分鐘無法享受 cache hit。
- **reply_token vs push**：超過 30 秒（如 Claude 長思考）需走 push（額外計入 LINE 月推播額度）。
- **Perplexity 與 Claude 雙模型**：搜尋結果不會進 Claude 對話歷史 cache，每次重抓。
- **Google Calendar 必須 Service Account**：個人帳號 OAuth 會在 7 天 refresh token 過期，故統一用 Service Account。
