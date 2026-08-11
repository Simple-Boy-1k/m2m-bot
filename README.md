# 🚀 𝙎𝘼𝙍𝙆𝘼𝙍 :: メ :: 𝙈𝙊𝘿 𝗠𝟮𝗠

Telegram Voice Chat & Live Stream Joiner Bot with Owner Control System & In-Bot Session Management.

---

### 💜 Deploy to Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Simple-Boy-1k/m2m-bot)

---

### 🛠️ Required Environment Variables

| Variable | Description |
| :--- | :--- |
| `API_ID` | Telegram API ID from https://my.telegram.org |
| `API_HASH` | Telegram API Hash from https://my.telegram.org |
| `BOT_TOKEN` | Bot token from @BotFather |
| `MONGO_DB_URI` | MongoDB Connection URL from MongoDB Atlas |
| `OWNER_ID` | Your Telegram Numeric User ID |

---

### 📌 Features
- 🔒 **Strict Owner Control**: Sirf `OWNER_ID` hi bot aur buttons ko control kar sakta hai.
- 🔑 **In-Bot Session Management**: Pyrogram String Sessions ko seedhe bot ke andar buttons se Add/Remove karein.
- 🌐 **24/7 Active**: Background Flask Keep-Alive server continuous runtime ke liye.
- ⚡ **Multi-Session VC Joiner**: Saved sessions ka use karke Voice Chat join karwane ke liye.
