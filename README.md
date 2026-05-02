# 💕 Lumio — LINE AI 貼心秘書

Lumio 是以 Anthropic Claude 為核心、串接 LINE Messaging API 的個人秘書機器人，部署於 Zeabur。
聰明能幹、溫暖貼心，能管行程、寫公文、查法規、整理會議紀錄、規劃旅遊、**記帳、聽語音、看圖**。

> **個人版**：所有自動排程通知（早晨簡報、提醒派送）已停用；`/簡報` 仍可手動觸發。未來通知系統將重新設計。

---

## ✨ 功能總覽

| 類別 | 自然語言入口 | 對應工具 |
|------|--------------|----------|
| 智慧搜尋 | 「最新台積電股價」 | `web_search`（Perplexity sonar） |
| 網址摘要 | 貼上任何 URL（PDF 自動下載解析） | `summarize_url`（HTML 走 Perplexity、PDF 走 Claude vision） |
| 地圖連結 | 「信義區牛排」 | `google_map_search` |
| Google Calendar | 「排明天3點開會」「把那會議改到5點」 | `gcal_query / gcal_add / gcal_update / gcal_delete / gcal_free_busy / gcal_upcoming` |
| 待辦 / 備忘 | 「幫我記下要買牛奶」 | `todo_add / todo_list / todo_complete / todo_delete / note_add / note_list / note_delete` |
| **記帳** | 「午餐 120」「咖啡 150 刷卡」「薪水 50000」 | `expense_add / expense_query / expense_summary / expense_delete` |
| **長期記憶** | 「記住我太太生日是 5/20」「我喜歡拿鐵不加糖」 | `profile_remember / profile_list / profile_forget` |
| 公文初稿 | 「擬一份公文回環境部，主旨…」 | `gen_official_doc`（台灣公文體：受文者/主旨/說明/擬辦/陳/核） |
| 公文範本庫 | 「存成範本」「套用範本 2」 | `template_add / template_list / template_apply / template_delete` |
| 台灣法規 | 「空污法第 31 條」 | `law_search`（優先 law.moj.gov.tw） |
| 會議紀錄 | 直接上傳 .docx / .pptx | 三段式整理：結論／待辦／簽呈摘要 |
| 旅遊行程 | 「規劃 7/15-19 福岡」 | `trip_create / trip_list / trip_detail / trip_delete`（自動同步 GCal） |
| 圖片分析 | 直接傳圖片 | Claude vision |
| 文件摘要 | 上傳 .pdf / .txt / .md / .csv | `analyze_file`（PDF 雙上限保護：60 頁／200k 字） |
| **語音訊息** | 直接傳語音 | OpenAI Whisper → Claude（需 `OPENAI_API_KEY`） |
| 早晨簡報（手動） | `/簡報` 手動觸發（行程 + 待辦 + 昨日支出 + 天氣） | `briefing.build_morning_briefing` |
| **台灣個人化** | 「今天油價」「最新發票中獎號碼」「報稅還剩幾天」 | `gas_price / invoice_lottery / tax_countdown` |
| **資料匯出** | 一鍵打包待辦／備忘／記帳／對話為純文字 | `/匯出 [天數]` |

> Claude 工具總數：**37**（自動工具呼叫上限 6 輪）

### 快捷指令

| 指令 | 說明 |
|------|------|
| `/簡報` | 手動產生早晨簡報 |
| `/狀態` | 待辦／備忘統計、本月支出、Token 用量 |
| `/摘要 <URL>` | 即時摘要（PDF URL 自動下載解析） |
| `/油價` | 中油 92／95／98／柴油牌價 |
| `/發票 [號碼]` | 最新一期統一發票中獎號碼／對獎 |
| `/報稅` | 綜所稅倒數與提醒 |
| `/匯出 [天數]` | 打包匯出待辦／備忘／記帳／對話（預設 7 天） |
| `/範本` / `/範本 套用 N` / `/範本 刪 N` | 範本庫操作 |
| `/法規 <關鍵字>` | 查台灣法規條文正文 |
| `/旅遊` / `/旅遊 查看 N` / `/旅遊 刪 N` | 旅程列表／詳情／刪除（同步 GCal） |
| `/待辦` / `/t` / `/待辦 完成 N` / `/待辦 刪 N` / `/待辦 清空` | 待辦操作（列表為 **Flex 卡片含完成/刪除按鈕**） |
| `/記事` / `/記事 <內容>` / `/記事 刪 N` | 備忘錄（Flex 卡片含刪除按鈕） |
| `/記帳` | 今日支出 Flex carousel（含刪除按鈕） |
| `/記帳 月` / `週` / `上月` / `年` / `今日` / `昨日` | 期間統計 Flex（分類占比橫條圖） |
| `/記帳 查 <分類>` / `/記帳 刪 N` | 篩選查詢／刪除 |
| `/日曆` / `/cal` / `/日曆 明天\|本週\|即將\|4/30` | 行事曆查詢 |
| `/reset` / `/清除記憶` | 清除對話記憶（不影響待辦/備忘/記帳/長期記憶） |
| `/h` / `/help` | 顯示說明 |

### 互動 UX 亮點

- **Flex Message**：`/待辦`、`/記事`、`/記帳` 列表都是可點按的 carousel，按按鈕直接完成或刪除
- **Webhook idempotency**：LINE 重送訊息自動去重，不重覆扣 token
- **Reply / Push 自動切換**：reply token 逼近 25 秒自動 fallback push，避免 Claude 思考時間長造成回覆失敗
- **Prompt caching**：System prompt 拆 CORE / TOOLS_GUIDE 雙層 cache，常駐情境省 ~90% input tokens
- **多副本部署就緒**：APScheduler + PG advisory lock 確保 DB 清理任務只執行一次

---

## 🚀 部署（Zeabur）

### 1. 建立外部服務

| 服務 | 用途 | 必要 |
|------|------|------|
| LINE Messaging API Channel | Bot 入口 | ✅ |
| Anthropic Console API Key | Claude 模型 | ✅ |
| Zeabur PostgreSQL | 對話/待辦/範本/旅程/記帳/長期記憶/Token 用量 | ✅ |
| Perplexity API Key | 搜尋／摘要／法規 | 建議 |
| Google Cloud Service Account | Calendar / 旅遊 GCal 同步 | 選用 |
| OpenAI API Key | Whisper 語音轉文字 | 選用 |

### 2. 推上 GitHub 後在 Zeabur 部署

Zeabur 偵測 Python 自動部署。Procfile 已設定 `web: uvicorn main:app --host 0.0.0.0 --port $PORT`。

### 3. 環境變數

| 變數 | 必填 | 說明 |
|------|------|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Channel Access Token |
| `LINE_CHANNEL_SECRET` | ✅ | LINE Channel Secret |
| `ANTHROPIC_API_KEY` | ✅ | Claude API Key |
| `DATABASE_URL` | ✅ | 設為 `${POSTGRES_URI}` 由 Zeabur 注入 |
| `PERPLEXITY_API_KEY` | 建議 | 網路搜尋／URL 摘要／法規查詢 |
| `OPENAI_API_KEY` | 選用 | 語音訊息 → Whisper 轉文字（未設定時語音訊息會回提示） |
| `GOOGLE_CALENDAR_CREDENTIALS` | 選用 | Service Account JSON（單行字串） |
| `GOOGLE_CALENDAR_ID` | 選用 | 預設 `primary` |
| `WEATHER_CITY` | 選用 | wttr.in 城市，預設 `Taipei`（給 `/簡報` 用） |
| `DISABLE_SCHEDULER` | 選用 | `1` 完全關閉排程器（連 DB 清理也不跑） |
| `LOG_LEVEL` | 選用 | 預設 `INFO` |

### 4. Webhook 與首次互動

1. Zeabur Networking 取得 Domain
2. LINE Developers → Messaging API → Webhook URL 填 `https://<domain>/webhook` → Verify
3. 加 Bot 為好友直接開始對話（個人版無自動推播；早晨簡報需手動 `/簡報`）

### 5. 健康檢查

- `GET /` — Liveness
- `GET /healthz` — Readiness（檢查 DB 連線、Bot userId、scheduler 狀態，回 JSON `{"status": "ok"|"degraded", "checks": {...}}`）

---

## 🔧 技術架構

| 元件 | 技術 |
|------|------|
| Web | FastAPI（Lifespan + BackgroundTasks） |
| LINE | line-bot-sdk v3（Reply + Push + **Flex Message + Postback**） |
| LLM | Anthropic Claude `claude-sonnet-4-6`（含雙層 prompt cache） + `claude-haiku-4-5-20251001`（短任務） |
| 搜尋 | Perplexity sonar（統一封裝於 `features/perplexity.py`） |
| 語音 | OpenAI Whisper（`whisper-1`） |
| 地圖 | Google Maps URL（免 API Key） |
| 行事曆 | Google Calendar API + Service Account |
| 文件解析 | python-docx、python-pptx、pypdf（雙上限保護） |
| 資料庫 | PostgreSQL（psycopg2 SimpleConnectionPool） |
| 排程 | APScheduler（Asia/Taipei） + PG advisory lock |
| 部署 | Zeabur |

完整模組關係圖、資料流、擴充指南請見 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 📁 專案結構

```
line-ai-bot/
├── main.py              # FastAPI 入口、LINE webhook、slash dispatcher、postback handler
├── config.py            # 環境變數、共用 logger 與 LINE/Anthropic 客戶端
├── prompts.py           # System prompt（CORE + TOOLS_GUIDE 雙層）+ 動態日期區塊 + 長期記憶區塊
├── calendar_tw.py       # 台灣國定假日、農曆節慶
├── Procfile / requirements.txt
├── db/                  # 依關注點分檔的 db package
│   ├── __init__.py            # re-export 公開 API（`import db; db.add_todo(...)` 仍可用）
│   ├── pool.py                # 連線池 + transaction context manager
│   ├── schema.py              # 建表 / 索引 / 補欄位
│   ├── conversations.py       # 對話記憶（保留 12 則）
│   ├── todos.py / notes.py
│   ├── subscriptions.py / push_log.py
│   ├── templates.py           # 公文範本
│   ├── trips.py               # 旅遊（含 places / gcal_ids JSONB）
│   ├── processed_messages.py  # Webhook idempotency（messageId 去重）
│   ├── token_usage.py         # 每日 Claude API 用量彙總
│   ├── user_profile.py        # 長期記憶（KV）
│   ├── workflows.py           # 工作流／提醒資料表（個人版尚未啟用通知派送）
│   └── expenses.py            # 記帳
├── features/
│   ├── chat.py          # Claude 主迴圈、tool use（最多 6 輪）、雙層 prompt cache、檔案摘要（含 analyze_pdf_bytes 共用）
│   ├── tools.py         # 37 個工具定義 + match/case dispatch
│   ├── perplexity.py    # Perplexity 統一介面
│   ├── search.py        # web_search / google_map_search
│   ├── url_summary.py   # 網址摘要（HTML→Perplexity；PDF URL→下載 + Claude）
│   ├── calendar.py      # Google Calendar CRUD（含時區補正）
│   ├── briefing.py      # 早晨簡報內容組裝（手動 /簡報 觸發）
│   ├── doc_official.py  # 公文初稿 + 範本庫
│   ├── law.py           # 法規查詢
│   ├── meeting.py       # .docx / .pptx 三段式整理
│   ├── trip.py          # 旅遊容器（同步 GCal）
│   ├── todo.py / note.py / help.py
│   ├── push.py          # LINE Push API（給 _send TTL fallback 使用）
│   ├── scheduler.py     # APScheduler：個人版僅每日 03:30 DB 清理
│   ├── workflow.py      # compose_workflow placeholder（reminder 派送已停用）
│   ├── profile.py       # 長期記憶入口
│   ├── expense.py       # 記帳業務邏輯（11 分類、6 付款方式）
│   ├── flex.py          # Flex Message 卡片 + postback 協定（todo/note/expense）
│   ├── audio.py         # OpenAI Whisper 整合
│   ├── taiwan.py        # 油價 / 統一發票 / 報稅倒數（前兩者走 Perplexity）
│   └── export.py        # 一鍵打包待辦/備忘/記帳/對話為純文字
└── tests/               # pytest 單元測試（84 個，純函式覆蓋）
```

---

## 🗄️ 資料庫表

| 表 | 用途 |
|----|------|
| `conversations` | 對話記憶（user_id × role × content，保留 12 則） |
| `todos` | 待辦事項（含分類、到期日） |
| `notes` | 備忘錄 |
| `subscriptions` | 訂閱旗標（個人版排程已停；資料表保留供未來重啟通知） |
| `push_log` | 推播去重（個人版排程已停；資料表保留） |
| `doc_templates` | 公文範本庫 |
| `trips` | 旅遊容器（places / gcal_ids JSONB） |
| `processed_messages` | Webhook 訊息去重（messageId PK，7 天保留） |
| `token_usage` | Claude API 用量彙總（user × date × model） |
| `user_profile` | 長期記憶 KV（每用戶 50 條上限） |
| `workflows` | 工作流／提醒資料表（個人版尚未啟用通知派送） |
| `expenses` | 記帳明細（amount, category, description, payment_method, occurred_at） |

啟動時 `init_db()` 會自動 `CREATE TABLE IF NOT EXISTS` 並補索引。

---

## 🧪 測試

```bash
pip install -r requirements.txt
pip install pytest
python -m pytest tests/ -v
```

84 個純函式測試，涵蓋：時間計算（含期間切片月／年邊界）、Markdown 清理、postback 解析、Flex 卡片組裝、prompt 拆分、todo/expense 解析、金額格式化、報稅倒數、PDF URL 偵測等。

---

## ❓ 常見問題

**Webhook Verify 失敗** — 確認 Domain 已開、`/webhook` 路徑正確，Logs 無 startup 例外。

**Bot 不回應** — 首次需發訊息觸發 `upsert_subscription`；圖片/檔案需檢查 LINE Channel 權限與檔案大小（< 20MB）。

**行事曆相關工具失效** — 檢查 `GOOGLE_CALENDAR_CREDENTIALS` JSON 是否完整且日曆已共用給 Service Account email。

**簡報沒推送** — 檢查 `DISABLE_SCHEDULER` 是否設成 1、`subscriptions.briefing` 是否為 TRUE、`push_log` 當日是否已記錄。

**語音訊息回「尚未設定」** — 設定 `OPENAI_API_KEY` 即可啟用 Whisper 轉文字。

**提醒沒響** — 提醒由排程器每分鐘 tick，檢查 scheduler 是否啟動（`/healthz` 看 `checks.scheduler`）；DISABLE_SCHEDULER=1 會關閉。

**修改個性** — 編輯 `prompts.py` 對應命名常數（`_PERSONA` / `_IDENTITY` 等），不必動 `SYSTEM_PROMPT_CORE` 主體。

**對話記憶長度** — `db/conversations.py` 的 `MAX_HISTORY`（預設 12）；長期記憶由 `db/user_profile.py` 跨對話保留。

**Token 成本** — `/狀態` 顯示今日／本月呼叫次數與成本；明細存於 `token_usage` 表，預設保留 365 天。
