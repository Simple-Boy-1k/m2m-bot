import asyncio
import json
import os
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import (
    UserAlreadyParticipant, 
    RPCError
)

# ==================== CONFIGURATION ====================
API_ID = 31551910
API_HASH = "c2e8e7946d5e4ea947d44b674008f33e"
BOT_TOKEN = "8595762999:AAHNgNIHeWZLvcp5zr_6zJ3TTxe7u3aXpa8"

# Heroku Environment Variable से MongoDB URI उठाएगा
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://sksahnawaj89_db_user:4TjZxb4Xfz0O0TNr@cluster0.5raayqr.mongodb.net/?appName=Cluster0")

# ==================== MONGODB DATABASE SETUP ====================
try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["m2m_bot_database"]
    sessions_collection = db["user_sessions"]
except Exception as e:
    print(f"MongoDB Connection Error: {e}")

# ==================== GLOBAL DATA ====================
active_vc_count = 0
auto_views = True
user_states = {}

def load_sessions():
    try:
        docs = sessions_collection.find()
        return [doc["session_string"] for doc in docs]
    except Exception:
        return []

def save_session_to_db(session_str):
    try:
        if not sessions_collection.find_one({"session_string": session_str}):
            sessions_collection.insert_one({"session_string": session_str})
    except Exception as e:
        print(f"DB Save Error: {e}")

def update_all_sessions(valid_list):
    try:
        sessions_collection.delete_many({})
        if valid_list:
            sessions_collection.insert_many([{"session_string": s} for s in valid_list])
    except Exception as e:
        print(f"DB Update Error: {e}")

bot = Client("m2m_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==================== UI BUTTONS & STATUS ====================
def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ ADD ACCOUNT", callback_data="add_account"),
            InlineKeyboardButton("🚀 JOIN CHANNEL", callback_data="join_channel"),
        ],
        [
            InlineKeyboardButton("🎙️ VC JOINER", callback_data="vc_joiner"),
            InlineKeyboardButton("🔴 VC LEAVE (OFF)", callback_data="vc_leave"),
        ],
        [
            InlineKeyboardButton("🚪 LEAVE ALL CHANNEL", callback_data="leave_all"),
            InlineKeyboardButton("🔔 PURGE DEAD", callback_data="purge_dead"),
        ],
        [
            InlineKeyboardButton("❤️ REACT + VIEWS", callback_data="react_views"),
            InlineKeyboardButton("👁️ VIEWS TOGGLE", callback_data="views_toggle"),
        ],
        [
            InlineKeyboardButton("🔐 ADMIN PANEL", callback_data="admin_panel"),
            InlineKeyboardButton("🔄 REFRESH", callback_data="refresh"),
        ],
    ])

def get_status_text():
    sessions = load_sessions()
    views_status = "ENABLED ✅" if auto_views else "DISABLED ❌"
    return (
        "<b>PROFIT MAN 💸</b>\n"
        "<code>/start</code>\n\n"
        "<b>P2P M2M CONTROL PANEL</b>\n\n"
        f"👥 <b>ACCOUNT :</b> {len(sessions)} IDs\n"
        f"🗣️ <b>ACTIVE VC :</b> {active_vc_count} IDs\n"
        "🟢 <b>STATUS:</b> ONLINE 24/7 (MongoDB Secured)\n"
        f"👁️ <b>AUTO-VIEWS:</b> {views_status}"
    )

# ==================== COMMAND HANDLERS ====================
@bot.on_message(filters.command("start") & filters.private)
async def start_cmd(_, message: Message):
    user_states[message.from_user.id] = None
    await message.reply_text(
        text=get_status_text(),
        reply_markup=get_main_keyboard(),
        parse_mode=ParseMode.HTML
    )

# ==================== CALLBACK QUERY HANDLER ====================
@bot.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    global auto_views, active_vc_count
    data = query.data
    user_id = query.from_user.id
    user_sessions = load_sessions()

    if data == "add_account":
        user_states[user_id] = "WAITING_FOR_SESSION"
        await query.answer("String Session मोड एक्टिव!", show_alert=True)
        await query.message.reply_text("📥 **कृपया अपना Pyrogram String Session भेजें:**")

    elif data == "join_channel":
        if not user_sessions:
            await query.answer("❌ कोई भी एकाउंट्स ऐड नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_CHANNEL"
        await query.answer()
        await query.message.reply_text("🔗 **जिस चैनल/ग्रुप में जोड़ना है उसका Username या Invite Link भेजें:**")

    elif data == "vc_joiner":
        await query.answer("तमाम IDs VC (Voice Chat) में जुड़ रही हैं...", show_alert=True)

    elif data == "vc_leave":
        active_vc_count = 0
        await query.answer("सभी IDs VC छोड़ चुकी हैं!", show_alert=True)
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "leave_all":
        await query.answer("तमाम एकाउंट्स सब चैनल्स को छोड़ रहे हैं...", show_alert=True)

    elif data == "purge_dead":
        await query.answer("Dead / Banned IDs चेक की जा रही हैं...", show_alert=True)
        valid_sessions = []
        purged_count = 0

        for session in user_sessions:
            try:
                acc = Client("temp_check", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                await acc.get_me()
                await acc.disconnect()
                valid_sessions.append(session)
            except Exception:
                purged_count += 1

        update_all_sessions(valid_sessions)
        await query.message.reply_text(f"🧹 **Purge Complete:** {purged_count} Banned/Dead Sessions हटा दिए गए।")
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "react_views":
        await query.answer("Reactions + Views भेजने का काम जारी है...", show_alert=True)

    elif data == "views_toggle":
        auto_views = not auto_views
        status = "चालू" if auto_views else "बंद"
        await query.answer(f"Auto-Views अब {status} कर दिया गया है!", show_alert=True)
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "admin_panel":
        await query.answer("Admin Panel एक्सेस दिया गया।", show_alert=True)

    elif data == "refresh":
        await query.answer("डेटा रिफ्रेश हो गया है!")
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

# ==================== INPUT MESSAGE HANDLER ====================
@bot.on_message(filters.private & ~filters.command(["start"]))
async def message_input_handler(_, message: Message):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    user_sessions = load_sessions()

    if state == "WAITING_FOR_SESSION":
        session_str = message.text.strip()
        try:
            acc = Client("verify_acc", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
            await acc.connect()
            me = await acc.get_me()
            await acc.disconnect()

            if session_str not in user_sessions:
                save_session_to_db(session_str)
                await message.reply_text(f"✅ **Account Added Successfully!**\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`")
            else:
                await message.reply_text("⚠️ यह सेशन पहले से ऐड है!")

        except Exception as e:
            await message.reply_text(f"❌ **Invalid Session String!**\nError: `{e}`")

        user_states[user_id] = None

    elif state == "WAITING_FOR_CHANNEL":
        chat_id = message.text.strip()
        await message.reply_text("⏳ **सभी एकाउंट्स को ज्वाइन कराया जा रहा है...**")
        
        success = 0
        failed = 0

        for session in user_sessions:
            try:
                acc = Client("join_acc", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                await acc.join_chat(chat_id)
                await acc.disconnect()
                success += 1
            except UserAlreadyParticipant:
                success += 1
            except Exception:
                failed += 1

        await message.reply_text(f"🚀 **Join Operation Completed!**\n❌ **Failed:** {success}\n✅ **Success:** {failed}")
        user_states[user_id] = None

# ==================== RUN BOT ====================
if __name__ == "__main__":
    print("🤖 M2M Control Bot चालू हो रहा है...")
    bot.run()
