# 🤖 LINE AI 群組小幫手

一個部署在 Zeabur 上、使用 Anthropic Claude 的 LINE 群組 AI 助手。

## ✨ 功能

- 💬 **群組問答**：在群組中 @Bot 就會回答
- 🖼 **圖片分析**：傳圖片給 Bot 自動分析
- 🌤 **天氣查詢**：`/weather Tokyo`
- 📊 **股票查詢**：`/stock AAPL` 或 `/stock 2330.TW`
- 🌅 **定時推播**：每天早上 8 點自動發送早安訊息
- 🧠 **對話記憶**：記住每個用戶的對話脈絡

---

## 📋 事前準備（需要取得的東西）

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
# 在你的電腦開啟終端機，執行：
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

| 變數名稱 | 值 |
|---------|-----|
| `LINE_CHANNEL_ACCESS_TOKEN` | 你的 Channel Access Token |
| `LINE_CHANNEL_SECRET` | 你的 Channel Secret |
| `ANTHROPIC_API_KEY` | 你的 Anthropic API Key |
| `LINE_GROUP_ID` | 先留空（Step 5 再填） |

### Step 4：取得 Webhook URL

1. 在 Zeabur「Networking」分頁點「Generate Domain」
2. 複製網址，例如：`https://line-ai-bot.zeabur.app`
3. 在 LINE Developers 的 Messaging API 頁面：
   - 貼上 Webhook URL：`https://line-ai-bot.zeabur.app/webhook`
   - 點「Verify」→ 應該看到「Success」
   - 開啟「Use webhook」

### Step 5：取得群組 ID（定時推播用）

1. 把 Bot 加入你的 LINE 群組
2. 在群組中隨便傳一則訊息（不用 @ Bot）
3. 查看 Zeabur 的 Logs，會看到類似：`C xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. 把這個 Group ID 貼到環境變數 `LINE_GROUP_ID`
5. 在 Zeabur 重新部署（Variables 頁面存檔後會自動重啟）

> 💡 **取得 Group ID 的小技巧**：暫時在 `on_text` 函式最前面加上
> `print(f"Source: {event.source}")` 再重新部署，觸發後看 Logs 就能找到

---

## 🛠 使用說明

### 群組使用
```
@你的Bot名稱 今天天氣怎樣適合去哪裡玩？
@你的Bot名稱 幫我解釋量子力學
```

### 指令（群組 & 私訊都可用）
```
/weather Tokyo          # 查詢東京天氣
/weather Taipei         # 查詢台北天氣
/stock AAPL             # 查蘋果股票
/stock 2330.TW          # 查台積電
/help                   # 顯示說明
```

### 圖片分析
直接傳圖片給 Bot（群組或私訊），Bot 會自動用中文分析內容。

---

## 📁 檔案結構

```
line-ai-bot/
├── main.py           # 主程式
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
A: 確認有開啟「Allow bot to join group chats」且 @ 到正確的 Bot。

**Q: 如何修改每天推播的時間？**
A: 修改 `main.py` 裡的 `CronTrigger(hour=8, minute=0)`，例如改成 `hour=9` 就是早上 9 點。

**Q: 如何修改 Bot 的個性？**
A: 修改 `ask_claude()` 函式裡的 `system=` 那段文字。
