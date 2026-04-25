# 💕 Lumio — LINE AI 貼心秘書

Lumio 是以 Anthropic Claude 為核心、串接 LINE Messaging API 的個人秘書機器人，部署於 Zeabur。
聰明能幹、溫暖貼心，能管行程、寫公文、查法規、整理會議紀錄、規劃旅遊，並每天主動問早。

---

## ✨ 功能總覽

| 類別 | 自然語言入口 | 對應工具 |
|------|--------------|----------|
| 智慧搜尋 | 「最新台積電股價」 | `web_search`（Perplexity sonar） |
| 網址摘要 | 貼上任何 URL | `summarize_url` |
| 地圖連結 | 「信義區牛排」 | `google_map_search` |
| Google Calendar | 「排明天3點開會」「把那會議改到5點」 | `gcal_query / gcal_add / gcal_update / gcal_delete / gcal_free_busy / gcal_upcoming` |
| 待辦 / 備忘 | 「幫我記下要買牛奶」 | `todo_add / todo_list / todo_complete / todo_delete / note_add / note_list / note_delete` |
| 公文初稿 | 「擬一份公文回環境部，主旨…」 | `gen_official_doc`（台灣公文體：受文者/主旨/說明/擬辦/陳/核） |
| 公文範本庫 | 「存成範本」「套用範本 2」 | `template_add / template_list / template_apply / template_delete` |
| 台灣法規 | 「空污法第 31 條」 | `law_search`（優先 law.moj.gov.tw） |
| 會議紀錄 | 直接上傳 .docx / .pptx | 三段式整理：結論／待辦／簽呈摘要 |
| 旅遊行程 | 「規劃 7/15-19 福岡」 | `trip_create / trip_list / trip_detail / trip_delete`（自動同步 GCal） |
| 圖片分析 | 直接傳圖片 | Claude vision |
| 文件摘要 | 上傳 .pdf / .txt / .md / .csv | `analyze_file` |
| 早晨簡報 | 每日 08:00 自動推播 | `briefing.build_morning_briefing` |

### 快捷指令

| 指令 | 說明 |
|------|------|
| `/簡報` / `/簡報 開` / `/簡報 關` | 立即推播／開關每日推送 |
| `/狀態` | 訂閱與資料統計 |
| `/摘要 <URL>` | 即時摘要 |
| `/範本` / `/範本 套用 N` / `/範本 刪 N` | 範本庫操作 |
| `/法規 <關鍵字>` | 查台灣法規條文正文 |
| `/旅遊` / `/旅遊 查看 N` / `/旅遊 刪 N` | 旅程列表／詳情／刪除（同步 GCal） |
| `/待辦` / `/t` / `/待辦 完成 N` / `/待辦 刪 N` / `/待辦 清空` | 待辦操作 |
| `/記事` / `/記事 <內容>` / `/記事 刪 N` | 備忘錄 |
| `/日曆` / `/cal` / `/日曆 明天\|本週\|即將\|4/30` | 行事曆查詢 |
| `/reset` / `/清除記憶` | 清除對話記憶 |
| `/h` / `/help` | 顯示說明 |

---

## 🚀 部署（Zeabur）

### 1. 建立外部服務

| 服務 | 用途 | 必要 |
|------|------|------|
| LINE Messaging API Channel | Bot 入口 | ✅ |
| Anthropic Console API Key | Claude 模型 | ✅ |
| Zeabur PostgreSQL | 對話/待辦/訂閱/範本/旅程 | ✅ |
| Perplexity API Key | 搜尋／摘要／法規 | 建議 |
| Google Cloud Service Account | Calendar / 旅遊 GCal 同步 | 選用 |

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
| `GOOGLE_CALENDAR_CREDENTIALS` | 選用 | Service Account JSON（單行字串） |
| `GOOGLE_CALENDAR_ID` | 選用 | 預設 `primary` |
| `WEATHER_CITY` | 選用 | wttr.in 城市，預設 `Taipei` |
| `BRIEF_HOUR` / `BRIEF_MINUTE` | 選用 | 早晨簡報時間，預設 8 / 0 |
| `DISABLE_SCHEDULER` | 選用 | `1` 關閉內建排程 |
| `LOG_LEVEL` | 選用 | 預設 `INFO` |

### 4. Webhook 與首次互動

1. Zeabur Networking 取得 Domain
2. LINE Developers → Messaging API → Webhook URL 填 `https://<domain>/webhook` → Verify
3. 加 Bot 為好友傳一則訊息：系統會自動 `upsert_subscription`，預設開啟早晨簡報

---

## 🔧 技術架構

| 元件 | 技術 |
|------|------|
| Web | FastAPI（Lifespan + BackgroundTasks） |
| LINE | line-bot-sdk v3（Reply + Push） |
| LLM | Anthropic Claude `claude-sonnet-4-6`（含 prompt cache） + `claude-haiku-4-5-20251001`（短任務） |
| 搜尋 | Perplexity sonar（統一封裝於 `features/perplexity.py`） |
| 地圖 | Google Maps URL（免 API Key） |
| 行事曆 | Google Calendar API + Service Account |
| 文件解析 | python-docx、python-pptx、pypdf |
| 資料庫 | PostgreSQL（psycopg2 SimpleConnectionPool） |
| 排程 | APScheduler（Asia/Taipei） |
| 部署 | Zeabur |

完整模組關係圖、資料流、擴充指南請見 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 📁 專案結構

```
line-ai-bot/
├── main.py              # FastAPI 入口、LINE webhook、slash dispatcher
├── config.py            # 環境變數、共用 logger 與 LINE/Anthropic 客戶端
├── prompts.py           # System prompt（命名常數組裝） + 動態日期區塊
├── calendar_tw.py       # 台灣國定假日、農曆節慶
├── Procfile / requirements.txt
├── db/                  # 依關注點分檔的 db package
│   ├── __init__.py      # re-export 公開 API（`import db; db.add_todo(...)` 仍可用）
│   ├── pool.py          # 連線池 + transaction context manager
│   ├── schema.py        # 建表 / 索引 / 補欄位
│   ├── conversations.py # 對話記憶（保留 12 則）
│   ├── todos.py / notes.py
│   ├── subscriptions.py / push_log.py
│   ├── templates.py     # 公文範本
│   └── trips.py         # 旅遊（含 places / gcal_ids JSONB）
└── features/
    ├── chat.py          # Claude 主迴圈、tool use、prompt cache、檔案摘要
    ├── tools.py         # 27 個工具定義 + match/case dispatch
    ├── perplexity.py    # Perplexity 統一介面
    ├── search.py        # web_search / google_map_search
    ├── url_summary.py   # 網址摘要
    ├── calendar.py      # Google Calendar CRUD（含時區補正）
    ├── briefing.py      # 早晨簡報
    ├── doc_official.py  # 公文初稿 + 範本庫
    ├── law.py           # 法規查詢
    ├── meeting.py       # .docx / .pptx 三段式整理
    ├── trip.py          # 旅遊容器（同步 GCal）
    ├── todo.py / note.py / help.py
    ├── push.py          # LINE Push API
    ├── scheduler.py     # APScheduler 啟停 + 早晨簡報 cron
    └── workflow.py      # 多步驟工作流（placeholder）
```

---

## ❓ 常見問題

**Webhook Verify 失敗** — 確認 Domain 已開、`/webhook` 路徑正確，Logs 無 startup 例外。

**Bot 不回應** — 首次需發訊息觸發 `upsert_subscription`；圖片/檔案需檢查 LINE Channel 權限與檔案大小（< 20MB）。

**行事曆相關工具失效** — 檢查 `GOOGLE_CALENDAR_CREDENTIALS` JSON 是否完整且日曆已共用給 Service Account email。

**簡報沒推送** — 檢查 `DISABLE_SCHEDULER` 是否設成 1、`subscriptions.briefing` 是否為 TRUE、`push_log` 當日是否已記錄。

**修改個性** — 編輯 `prompts.py` 對應命名常數（`_PERSONA` / `_IDENTITY` 等），不必動 `SYSTEM_PROMPT` 主體。

**對話記憶長度** — `db/conversations.py` 的 `MAX_HISTORY`（預設 12）。
