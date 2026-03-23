# 💕 小愛 — LINE AI 女友助手

一個部署在 Zeabur 上、使用 Anthropic Claude 打造的 LINE AI 生活助手。
溫柔體貼、聰明能幹，做你最得力的後盾。

## ✨ 功能

- 💬 **智慧聊天**：女友般的溫暖對話，記住你說過的事
- 🖼 **圖片分析**：傳圖片給小愛，自動辨識分析
- 📝 **待辦事項**：新增、完成、刪除，重啟也不遺失
- 🌤 **天氣查詢**：即時查詢全球天氣
- 🌐 **即時翻譯**：中英文自動互譯
- 🍳 **食譜推薦**：根據食材推薦料理
- 💪 **加油打氣**：隨時給你溫暖的鼓勵
- ☀️ **早安推播**：每天早上 8 點甜蜜早安訊息
- 🧠 **對話記憶**：SQLite 持久化，重啟不遺失

---

## 📋 事前準備

### 1️⃣ LINE Developers 設定

1. 前往 https://developers.line.biz/
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

1. 前往 https://console.anthropic.com/
2. 登入 → 點左側「API Keys」
3. 點「Create Key」→ 複製 Key

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

1. 前往 https://zeabur.com/ → 登入
2. 點「New Project」→「Deploy Service」→「Git」
3. 選擇你的 `line-ai-bot` repository
4. Zeabur 會自動偵測 Python 並部署

### Step 3：設定環境變數

在 Zeabur 專案頁面：
1. 點你的服務 → 點「Variables」分頁
2. 逐一新增以下變數：

| 變數名稱 | 值 | 備註 |
|---------|-----|------|
| `LINE_CHANNEL_ACCESS_TOKEN` | 你的 Channel Access Token | 必填 |
| `LINE_CHANNEL_SECRET` | 你的 Channel Secret | 必填 |
| `ANTHROPIC_API_KEY` | 你的 Anthropic API Key | 必填 |
| `LINE_GROUP_ID` | 先留空（Step 5 再填） | 定時推播用 |
| `DATA_DIR` | `/data` | 資料庫路徑（選填，預設 `/data`） |

### Step 4：掛載持久化磁碟

> 這步很重要！確保待辦事項和對話記憶在重新部署後不會消失。

1. 在 Zeabur 點你的服務 → 「Settings」分頁
2. 找到「Volumes」→ 點「Add Volume」
3. Mount Path 填 `/data`
4. 儲存後服務會自動重啟

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

直接傳訊息給小愛就好，她會用溫暖的口吻回應你：

```
你：今天好累喔
小愛：辛苦了呢～今天也努力了一整天，真的很棒喔！要不要先喝杯水休息一下？
```

### 指令一覽

| 指令 | 說明 | 範例 |
|------|------|------|
| `/天氣 <城市>` | 查詢天氣 | `/天氣 台北`、`/weather Tokyo` |
| `/待辦 <內容>` | 新增待辦 | `/待辦 買牛奶` |
| `/待辦` | 查看清單 | |
| `/待辦 完成 1` | 標記完成 | |
| `/待辦 刪除 1` | 刪除項目 | |
| `/待辦 清空` | 清空全部 | |
| `/翻譯 <文字>` | 中英互譯 | `/翻譯 How are you?` |
| `/食譜 <食材>` | 推薦食譜 | `/食譜 雞蛋 番茄` |
| `/加油` | 加油打氣 | |
| `/幫助` | 顯示說明 | |

### 圖片分析

直接傳圖片給小愛（群組或私訊），她會自動用中文分析內容。

---

## 📁 檔案結構

```
line-ai-bot/
├── main.py           # 主程式（LINE webhook、指令、Claude 對話）
├── db.py             # SQLite 資料庫模組（待辦、對話記憶）
├── requirements.txt  # Python 套件
├── Procfile          # Zeabur 啟動指令
├── .env.example      # 環境變數範例
└── README.md         # 說明文件
```

---

## ❓ 常見問題

**Q: Webhook Verify 失敗怎麼辦？**
A: 確認 Zeabur 服務已正常運行（Logs 沒有紅色錯誤），且 URL 末尾有 `/webhook`。

**Q: Bot 在群組不回應？**
A: 確認有開啟「Allow bot to join group chats」且有 @ 到正確的 Bot。

**Q: 待辦事項重啟後消失了？**
A: 確認已在 Zeabur 掛載 Persistent Volume 到 `/data`，參考 Step 4。

**Q: 如何修改每天推播的時間？**
A: 修改 `main.py` 裡的 `CronTrigger(hour=8, minute=0)`，例如改成 `hour=9` 就是早上 9 點。

**Q: 如何修改小愛的個性？**
A: 修改 `main.py` 裡的 `GIRLFRIEND_SYSTEM_PROMPT` 變數內容。
