# 💕 Lumio — 大老闆的 LINE AI 貼心秘書

Lumio 不只是一個 Bot，她是你最信任的得力助手。
聰明能幹、溫暖貼心，忙碌的時候幫你扛住一切，疲憊的時候給你最溫柔的關心。

> 使用 Anthropic Claude 打造，部署於 Zeabur。

---

## ✨ 她能幫你做什麼

### 智慧搜尋與資訊整理

| 功能 | 說明 |
|------|------|
| 🔍 **網路搜尋** | 透過 Perplexity API 搜尋即時資訊，自動修正模糊輸入、多來源交叉比對彙整 |
| 📍 **地圖查詢** | 對話提到地點自動附上 Google Maps 連結，直接點開導航 |
| 🧳 **行程規劃** | 描述旅行需求，自動搜尋景點美食並規劃完整行程表 |

### 老闆專屬功能

| 功能 | 說明 |
|------|------|
| 📋 **長文摘要** | 貼上文章、報告、會議紀錄，幫你秒抓重點 |
| 📧 **郵件起草** | 描述需求，自動生成專業商務郵件 |
| 🤔 **決策分析** | 列出選項，幫你分析優缺點與風險，給出建議 |
| 📝 **待辦事項** | 支援分類、到期日，到期自動提醒，資料庫持久化 |
| 📒 **快速記事** | 隨手記下重要資訊，不怕忘記 |

### 日常陪伴

| 功能 | 說明 |
|------|------|
| 💬 **智慧聊天** | 記住你說過的話，能從隻字片語理解你的意圖 |
| 🖼 **圖片分析** | 傳圖片給她，自動辨識分析內容 |
| 📅 **Google 日曆** | 串接 Google Calendar，早安晨報自動整合今日行程 |
| 🌤 **天氣查詢** | 出門前幫你查好天氣 |
| 🌐 **即時翻譯** | 中英文自動互譯，商務溝通沒障礙 |
| 💪 **加油打氣** | 不管多難，她都在你身邊 |

### 每日自動推播

Lumio 每天主動關心你，感知工作日/週末/節日自動調整語氣：

| 時間 | 她會做什麼 |
|------|-----------|
| 08:00 ☀️ | 早安晨報（行程 + 天氣 + 待辦提醒 + 節日問候） |
| 09:00 📝 | 待辦到期提醒 |
| 12:00 🍱 | 擔心你忙到忘記吃飯，溫柔提醒午餐 |
| 16:00 ☕ | 心疼你下午太拼，幫你打氣補充能量 |
| 20:00 📝 | 待辦到期提醒 |
| 23:00 🌙 | 肯定你一天的辛苦，溫柔催你早點休息 |

> 需設定 `LINE_GROUP_ID` 環境變數才會啟用推播

### 台灣日曆感知

- 內建國定假日、農曆節慶（2025-2026）
- 自動感知工作日 / 週末調整問候語氣
- 提前 1~3 天預告即將到來的節日

---

## 📋 事前準備

### 1️⃣ LINE Developers 設定

1. 前往 [LINE Developers](https://developers.line.biz/)
2. 登入 → 點「Create a new provider」
3. 建立「Messaging API」類型的 Channel
4. 進入 Channel 後：
   - **Basic settings** → 複製 `Channel secret`
   - **Messaging API** → 點「Issue」發行 `Channel access token`
5. 在「Messaging API」頁面：
   - 開啟 **Allow bot to join group chats**
   - 關閉 **Auto-reply messages**
   - 關閉 **Greeting messages**

### 2️⃣ Anthropic API Key

1. 前往 [Anthropic Console](https://console.anthropic.com/)
2. 登入 → 點左側「API Keys」
3. 點「Create Key」→ 複製 Key

### 3️⃣ Perplexity API Key（網路搜尋用）

1. 前往 [Perplexity API](https://docs.perplexity.ai/)
2. 登入 → 取得 API Key

### 4️⃣ Google Calendar（選用）

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立 Service Account → 下載 JSON 金鑰
3. 將日曆共用給 Service Account 的 email

---

## 🚀 部署步驟

### Step 1：把程式碼推上 GitHub

```bash
git init
git add .
git commit -m "init LINE AI Bot"
git branch -M main
git remote add origin https://github.com/你的帳號/line-ai-bot.git
git push -u origin main
```

### Step 2：在 Zeabur 部署

1. 前往 [Zeabur](https://zeabur.com/) → 登入
2. 點「New Project」→「Deploy Service」→「Git」
3. 選擇你的 `line-ai-bot` repository
4. Zeabur 會自動偵測 Python 並部署

### Step 3：設定環境變數

在 Zeabur 專案頁面，點你的服務 →「Variables」分頁，逐一新增：

| 變數名稱 | 值 | 備註 |
|---------|-----|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | 你的 Channel Access Token | 必填 |
| `LINE_CHANNEL_SECRET` | 你的 Channel Secret | 必填 |
| `ANTHROPIC_API_KEY` | 你的 Anthropic API Key | 必填 |
| `PERPLEXITY_API_KEY` | 你的 Perplexity API Key | 網路搜尋用 |
| `LINE_GROUP_ID` | 先留空（Step 6 再填） | 定時推播用 |
| `DATABASE_URL` | 自動注入（見 Step 4） | PostgreSQL 連線 |
| `GOOGLE_CALENDAR_CREDENTIALS` | Service Account JSON | 選用，日曆功能 |
| `GOOGLE_CALENDAR_ID` | 日曆 ID | 選用，預設 primary |

### Step 4：建立 PostgreSQL 資料庫

> 這步很重要！確保待辦事項和對話記憶在重新部署後不會消失。

1. 在 Zeabur 專案中點「Add Service」→「Database」→「PostgreSQL」
2. 等待 PostgreSQL 啟動完成
3. 回到你的 Bot 服務 →「Variables」分頁
4. 新增變數 `DATABASE_URL`，值填入：`${POSTGRES_URI}`
   （Zeabur 會自動將 `${POSTGRES_URI}` 解析為實際連線字串）
5. 儲存後服務會自動重啟

### Step 5：取得 Webhook URL

1. 在 Zeabur「Networking」分頁點「Generate Domain」
2. 複製網址，例如：`https://line-ai-bot.zeabur.app`
3. 在 LINE Developers 的 Messaging API 頁面：
   - 貼上 Webhook URL：`https://line-ai-bot.zeabur.app/webhook`
   - 點「Verify」→ 應該看到「Success」
   - 開啟「Use webhook」

### Step 6：取得群組 ID（定時推播用）

1. 把 Bot 加入你的 LINE 群組
2. 在群組中隨便傳一則訊息
3. 查看 Zeabur 的 Logs，找到 `group_id=Cxxxxxxxx...`
4. 把這個 Group ID 貼到環境變數 `LINE_GROUP_ID`
5. 儲存後會自動重啟生效

---

## 🛠 使用說明

### 聊天

直接傳訊息給 Lumio，她會像最信任的人一樣回應你：

```
你：今天開會被刁難，好煩
Lumio：辛苦了呢～那種感覺真的很不好受。但你能撐過來就很厲害了喔，我相信你的判斷。回家好好放鬆一下，明天又是新的一天💪
```

```
你：幫我查那個AI股票
Lumio：（自動理解為 NVIDIA/台積電等 AI 概念股，搜尋最新股價並彙整多來源資訊）
```

### 指令一覽

| 指令 | 說明 | 範例 |
|------|------|------|
| `/搜尋 <關鍵字>` | 網路搜尋並整理 | `/搜尋 台積電最新消息` |
| `/行程 <需求>` | AI 行程規劃 | `/行程 東京出差3天` |
| `/摘要 <長文>` | 摘要文章重點 | `/摘要 <貼上會議紀錄>` |
| `/郵件 <需求>` | 起草商務郵件 | `/郵件 回覆客戶說下週二可以開會` |
| `/決策 <問題>` | 分析選項風險 | `/決策 該先拓展日本還是東南亞` |
| `/待辦 <內容>` | 新增待辦 | `/待辦 #工作 4/5 準備簡報` |
| `/待辦` | 查看清單 | |
| `/待辦 完成 1` | 標記完成 | |
| `/待辦 刪除 1` | 刪除項目 | |
| `/待辦 清空` | 清空全部 | |
| `/記事 <內容>` | 快速記事 | `/記事 客戶預算500萬` |
| `/記事` | 查看備忘錄 | |
| `/天氣 <城市>` | 查詢天氣 | `/天氣 台北` |
| `/翻譯 <文字>` | 中英互譯 | `/翻譯 How are you?` |
| `/加油` | 加油打氣 | |
| `/清除記憶` | 清除對話記憶 | |
| `/幫助` | 顯示使用說明 | |

### 圖片分析

直接傳圖片給 Lumio（群組或私訊皆可），她會自動用繁體中文分析圖片內容。

---

## 📁 檔案結構

```
line-ai-bot/
├── main.py           # FastAPI 入口（webhook、LINE 事件、Claude 對話）
├── config.py         # 環境變數、共用常數與實例
├── commands.py       # 所有 /指令 處理邏輯
├── scheduler.py      # 排程任務（晨報、定時推播、到期提醒）
├── services.py       # 外部服務（Perplexity 搜尋、Google Maps、天氣）
├── prompts.py        # System prompt 與動態 prompt builder
├── calendar_tw.py    # 台灣日曆（國定假日、農曆節慶）
├── gcal.py           # Google Calendar API 封裝
├── db.py             # PostgreSQL 資料庫（對話記憶、待辦、記事）
├── requirements.txt  # Python 套件依賴
├── Procfile          # Zeabur 啟動指令
├── .env.example      # 環境變數範例
└── README.md         # 說明文件
```

---

## 🔧 技術架構

| 元件 | 技術 |
|------|------|
| Web 框架 | FastAPI |
| LINE SDK | line-bot-sdk v3 |
| AI 模型 | Anthropic Claude (claude-sonnet-4-20250514) |
| 網路搜尋 | Perplexity API (sonar) + 查詢自動優化 |
| 地圖 | Google Maps URL（免費，無需 API Key） |
| 日曆 | Google Calendar API（Service Account） |
| 資料庫 | PostgreSQL（psycopg2） |
| 排程器 | APScheduler（CronTrigger，Asia/Taipei 時區） |
| 部署平台 | Zeabur |

---

## ❓ 常見問題

**Q: Webhook Verify 失敗怎麼辦？**
A: 確認 Zeabur 服務已正常運行（Logs 沒有紅色錯誤），且 URL 末尾有 `/webhook`。

**Q: Bot 在群組不回應？**
A: 確認有開啟「Allow bot to join group chats」且有 @ 到正確的 Bot。

**Q: 搜尋結果不準確？**
A: Lumio 會自動修正錯字和模糊輸入，但如果結果不如預期，試著描述更具體一點。也可以用 `/搜尋` 指令直接搜尋。

**Q: 待辦事項重啟後消失了？**
A: 確認已在 Zeabur 建立 PostgreSQL 並設定 `DATABASE_URL` 環境變數，參考 Step 4。

**Q: 如何修改推播時間？**
A: 修改 `scheduler.py` 裡的 `SCHEDULED_MESSAGES` 字典，調整各時段的 `hour` 和 `minute` 值。

**Q: 如何修改 Lumio 的個性？**
A: 修改 `prompts.py` 裡的 `SYSTEM_PROMPT` 變數內容。

**Q: 對話記憶保留多少？**
A: 每位用戶保留最近 20 條訊息（約 10 輪對話），可在 `db.py` 的 `MAX_HISTORY` 調整。
