# 🚀 M2M VC Joiner Bot

Telegram Voice Chat & Live Stream Joiner Bot with Owner Control System & In-Bot Session Management.

---

### 💜 Deploy to Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://dashboard.heroku.com/new?template=https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME)

> ⚠️ **Note:** Deployment error se bachne ke liye link me `YOUR_GITHUB_USERNAME` aur `YOUR_REPO_NAME` ko apne GitHub details se zaroor replace karein.

---

### 🛠️ Environment Variables Setup

| Variable | Description |
| :--- | :--- |
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API Hash from my.telegram.org |
| `BOT_TOKEN` | Bot token from @BotFather |
| `MONGO_DB_URI` | MongoDB Connection URL from MongoDB Atlas |
| `OWNER_ID` | Your Telegram Numeric User ID |

---

### 📌 Features
- 🔒 **Strict Owner Control**: Sirf `OWNER_ID` hi bot aur buttons ko control kar sakta hai.
- 🔑 **In-Bot Session Management**: Pyrogram String Sessions ko seedhe bot ke andar buttons se Add/Remove karein.
- 🌐 **24/7 Active**: Background Flask Keep-Alive server continuous runtime ke liye.
- ⚡ **Multi-Session VC Joiner**: Saved sessions ka use karke Voice Chat join karwane ke liye.
