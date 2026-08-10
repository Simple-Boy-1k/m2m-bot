from pyrogram import Client, filters

# आपकी कॉन्फ़िगरेशन
API_ID = 31551910
API_HASH = "c2e8e7946d5e4ea947d44b674008f33e"
BOT_TOKEN = "8595762999:AAHmNthQFpGot6_MWtW00lB7xMRztmYHz1I"

# बॉट क्लाइंट बनाएँ
app = Client("test_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply_text("✅ बॉट बिल्कुल ठीक काम कर रहा है!")

print("🤖 Test Bot चालू हो रहा है...")
app.run()
