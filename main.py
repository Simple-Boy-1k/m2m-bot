import asyncio
import json
import os
import sys
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import UserAlreadyParticipant, RPCError
from pyrogram.raw.functions.phone import JoinGroupCall, LeaveGroupCall
from pyrogram.raw.functions.channels import GetFullChannel

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
user_temp_data = {}

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
    user_id = message.from_user.id
    user_states[user_id] = None
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
        user_temp_data[user_id] = {}
        await query.answer()
        await query.message.reply_text("🔗 **जिस चैनल/ग्रुप में जोड़ना है उसका Username या Invite Link भेजें:**")

    elif data == "vc_joiner":
        if not user_sessions:
            await query.answer("❌ कोई भी एकाउंट्स ऐड नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_VC_CHANNEL"
        user_temp_data[user_id] = {}
        await query.answer()
        await query.message.reply_text("🎙️ **जिस चैनल/ग्रुप की Voice Chat (VC) में जोड़ना है उसका Username या Link भेजें:**")

    elif data == "vc_leave":
        if not user_sessions:
            await query.answer("❌ कोई भी एकाउंट्स ऐड नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_VC_LEAVE_COUNT"
        user_temp_data[user_id] = {}
        await query.answer()
        await query.message.reply_text(f"🔴 **कितने एकाउंट्स को VC से बाहर निकालना है?**\n(कुल उपलब्ध IDs: {len(user_sessions)} | सभी के लिए `all` लिखें)")

    elif data == "leave_all":
        if not user_sessions:
            await query.answer("❌ कोई भी एकाउंट्स ऐड नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_LEAVE_COUNT"
        user_temp_data[user_id] = {}
        await query.answer()
        await query.message.reply_text(f"🚪 **कितने एकाउंट्स से चैनल्स/ग्रुप्स छोड़ने हैं?**\n(कुल उपलब्ध IDs: {len(user_sessions)} | सभी के लिए `all` लिखें)")

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
        if not user_sessions:
            await query.answer("❌ कोई भी एकाउंट्स ऐड नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_REACT_LINK"
        user_temp_data[user_id] = {}
        await query.answer()
        await query.message.reply_text("❤️ **जिस पोस्ट पर Reaction और Views भेजना है उसका Link भेजें:**")

    elif data == "views_toggle":
        auto_views = not auto_views
        status = "चालू" if auto_views else "बंद"
        await query.answer(f"Auto-Views अब {status} कर दिया गया है!", show_alert=True)
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "admin_panel":
        await query.answer("Admin Panel खुला है!", show_alert=True)
        admin_text = (
            "<b>🔐 ADMIN SYSTEM PANEL (MongoDB)</b>\n\n"
            f"• Python Version: {sys.version.split()[0]}\n"
            f"• Total Stored Sessions: {len(user_sessions)}\n"
            f"• Active VC Count: {active_vc_count}\n"
            f"• Auto Views Status: {'ON' if auto_views else 'OFF'}\n"
            "• Bot Status: Running smoothly 24/7"
        )
        await query.message.reply_text(admin_text, parse_mode=ParseMode.HTML)

    elif data == "refresh":
        await query.answer("डेटा रिफ्रेश हो गया है!")
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

# ==================== INPUT MESSAGE HANDLER ====================
@bot.on_message(filters.private & ~filters.command(["start"]))
async def message_input_handler(_, message: Message):
    global active_vc_count
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not state:
        return

    user_sessions = load_sessions()

    # 1. ADD ACCOUNT
    if state == "WAITING_FOR_SESSION":
        session_str = message.text.strip()
        user_states[user_id] = None
        try:
            acc = Client("verify_acc", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
            await acc.connect()
            me = await acc.get_me()
            await acc.disconnect()

            if session_str not in user_sessions:
                save_session_to_db(session_str)
                await message.reply_text(f"✅ **Account Added & Saved to DB!**\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`")
            else:
                await message.reply_text("⚠️ यह सेशन पहले से ऐड है!")

        except Exception as e:
            await message.reply_text(f"❌ **Invalid Session String!**\nError: `{e}`")

    # 2. JOIN CHANNEL - STEP 1
    elif state == "WAITING_FOR_CHANNEL":
        raw_link = message.text.strip()
        target_chat = raw_link
        if "t.me/" in raw_link:
            target_chat = raw_link.split("t.me/")[-1]
            if not target_chat.startswith("+") and not target_chat.startswith("joinchat/"):
                target_chat = target_chat.replace("@", "")

        if user_id not in user_temp_data:
            user_temp_data[user_id] = {}

        user_temp_data[user_id]["link"] = target_chat
        user_states[user_id] = "WAITING_FOR_COUNT"
        await message.reply_text(f"👥 **कितने एकाउंट्स का इस्तेमाल करना है?**\n(कुल उपलब्ध IDs: {len(user_sessions)} | सभी के लिए `all` लिखें)")

    # JOIN CHANNEL - STEP 2
    elif state == "WAITING_FOR_COUNT":
        text_val = message.text.strip().lower()
        try:
            if text_val == "all":
                count = len(user_sessions)
            else:
                count = int(text_val)
            
            user_temp_data[user_id]["count"] = min(count, len(user_sessions))
            user_states[user_id] = "WAITING_FOR_DELAY"
            await message.reply_text("⏱️ **हर रिक्वेस्ट के बीच कितना Delay रखना है?**\n*(उदाहरण: `5` सेकंड के लिए या `1m` 1 मिनट के लिए)*")
        except ValueError:
            await message.reply_text("❌ कृपया सही संख्या या `all` टाइप करें!")

    # JOIN CHANNEL - STEP 3
    elif state == "WAITING_FOR_DELAY":
        delay_text = message.text.strip().lower()
        try:
            if "m" in delay_text:
                delay = int(delay_text.replace("m", "").strip()) * 60
            elif "s" in delay_text:
                delay = int(delay_text.replace("s", "").strip())
            else:
                delay = int(delay_text)
        except ValueError:
            delay = 2

        target_chat = user_temp_data[user_id].get("link")
        max_acc = user_temp_data[user_id].get("count", len(user_sessions))

        user_states[user_id] = None
        user_temp_data.pop(user_id, None)

        await message.reply_text(f"🚀 **चैनल जॉइनिंग प्रक्रिया शुरू हो रही है...**\n• टारगेट: `{target_chat}`\n• कुल IDs: {max_acc}\n• Delay: {delay} सेकंड")

        success = 0
        failed = 0
        sessions_to_use = user_sessions[:max_acc]

        for idx, session in enumerate(sessions_to_use, 1):
            try:
                acc = Client(f"join_acc_{user_id}_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                await acc.join_chat(target_chat)
                await acc.disconnect()
                success += 1
            except UserAlreadyParticipant:
                success += 1
            except Exception:
                failed += 1

            if idx < len(sessions_to_use) and delay > 0:
                await asyncio.sleep(delay)

        await message.reply_text(f"✅ **Join Operation Completed!**\n👍 **Success:** {success}\n👎 **Failed:** {failed}")

    # 3. VC JOINER
    elif state == "WAITING_FOR_VC_CHANNEL":
        raw_link = message.text.strip()
        if user_id not in user_temp_data: user_temp_data[user_id] = {}
        user_temp_data[user_id]["link"] = raw_link
        user_states[user_id] = "WAITING_FOR_VC_COUNT"
        await message.reply_text(f"👥 **कितने एकाउंट्स को VC में जोड़ना है?**\n(कुल उपलब्ध IDs: {len(user_sessions)} | सभी के लिए `all` लिखें)")

    elif state == "WAITING_FOR_VC_COUNT":
        text_val = message.text.strip().lower()
        try:
            count = len(user_sessions) if text_val == "all" else int(text_val)
            user_temp_data[user_id]["count"] = min(count, len(user_sessions))
            user_states[user_id] = "WAITING_FOR_VC_DELAY"
            await message.reply_text("⏱️ **VC जॉइन करने के बीच कितना Delay रखना है?**")
        except ValueError:
            await message.reply_text("❌ कृपया सही संख्या टाइप करें!")

    elif state == "WAITING_FOR_VC_DELAY":
        delay = int(message.text.strip().replace("s", ""))
        target_chat = user_temp_data[user_id].get("link")
        max_acc = user_temp_data[user_id].get("count")
        
        user_states[user_id] = None
        user_temp_data.pop(user_id, None)

        await message.reply_text("🎙️ **VC जॉइनिंग प्रक्रिया शुरू...**")
        success = 0
        sessions_to_use = user_sessions[:max_acc]

        for idx, session in enumerate(sessions_to_use, 1):
            try:
                acc = Client(f"vc_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                try:
                    await acc.join_chat(target_chat)
                except:
                    pass
                peer = await acc.resolve_peer(target_chat)
                full_chat = await acc.invoke(GetFullChannel(channel=peer))
                if full_chat.full_chat.call:
                    await acc.invoke(JoinGroupCall(call=full_chat.full_chat.call, join_as=peer, muted=True))
                    success += 1
                await acc.disconnect()
            except Exception:
                pass
            await asyncio.sleep(delay)

        active_vc_count = success
        await message.reply_text(f"✅ **VC Join Completed!** Success: {success}")

    elif state == "WAITING_FOR_VC_LEAVE_COUNT":
        text_val = message.text.strip().lower()
        try:
            count = len(user_sessions) if text_val == "all" else int(text_val)
            user_temp_data[user_id] = {"count": min(count, len(user_sessions))}
            user_states[user_id] = "WAITING_FOR_VC_LEAVE_EXEC"
            await message.reply_text("🔗 **जिस चैनल/ग्रुप की VC से बाहर निकलना है उसका लिंक भेजें:**")
        except: await message.reply_text("❌ संख्या डालें!")

    elif state == "WAITING_FOR_VC_LEAVE_EXEC":
        target_chat = message.text.strip()
        max_acc = user_temp_data[user_id].get("count")
        user_states[user_id] = None
        user_temp_data.pop(user_id, None)
        success = 0
        for idx, session in enumerate(user_sessions[:max_acc], 1):
            try:
                acc = Client(f"vcleave_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                peer = await acc.resolve_peer(target_chat)
                full_chat = await acc.invoke(GetFullChannel(channel=peer))
                if full_chat.full_chat.call:
                    await acc.invoke(LeaveGroupCall(call=full_chat.full_chat.call))
                    success += 1
                await acc.disconnect()
            except: pass
        active_vc_count = max(0, active_vc_count - success)
        await message.reply_text(f"✅ **VC Leave Completed!** {success} IDs बाहर हो गईं।")

    elif state == "WAITING_FOR_LEAVE_COUNT":
        text_val = message.text.strip().lower()
        try:
            count = len(user_sessions) if text_val == "all" else int(text_val)
            user_temp_data[user_id] = {"count": min(count, len(user_sessions))}
            user_states[user_id] = "WAITING_FOR_LEAVE_CHAT"
            await message.reply_text("🔗 **किस चैनल को छोड़ना है उसका लिंक भेजें:**")
        except: await message.reply_text("❌ संख्या डालें!")

    elif state == "WAITING_FOR_LEAVE_CHAT":
        target_chat = message.text.strip()
        max_acc = user_temp_data[user_id].get("count")
        user_states[user_id] = None
        user_temp_data.pop(user_id, None)
        success = 0
        for idx, session in enumerate(user_sessions[:max_acc], 1):
            try:
                acc = Client(f"leave_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                await acc.leave_chat(target_chat)
                await acc.disconnect()
                success += 1
            except: pass
        await message.reply_text(f"✅ **Leave Operation Completed!** {success} ने छोड़ दिया।")

    elif state == "WAITING_FOR_REACT_LINK":
        post_link = message.text.strip()
        user_temp_data[user_id] = {"post_link": post_link}
        user_states[user_id] = "WAITING_FOR_EMOJI"
        await message.reply_text("💬 **Reaction Emoji भेजें (जैसे 👍):**")

    elif state == "WAITING_FOR_EMOJI":
        emoji = message.text.strip()
        post_link = user_temp_data[user_id].get("post_link")
        user_states[user_id] = None
        user_temp_data.pop(user_id, None)
        try:
            parts = post_link.split("t.me/")[-1].split("/")
            chat_target, msg_id = parts[0], int(parts[1])
            success = 0
            for session in user_sessions:
                try:
                    acc = Client(f"r_{session[:10]}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await acc.connect()
                    await acc.get_messages(chat_target, msg_id)
                    await acc.send_reaction(chat_target, msg_id, emoji)
                    await acc.disconnect()
                    success += 1
                except: pass
            await message.reply_text(f"✅ **Reaction Complete!** कुल {success} IDs.")
        except: await message.reply_text("❌ लिंक या रिएक्शन गलत है।")

# ==================== RUN BOT ====================
if __name__ == "__main__":
    bot.run()
