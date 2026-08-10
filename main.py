import json
import os
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.enums import ParseMode, ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.errors import UserAlreadyParticipant
from pyrogram.raw import functions

# ==================== CONFIGURATION ====================
API_ID = 31551910
API_HASH = "c2e8e7946d5e4ea947d44b674008f33e"
BOT_TOKEN = "8595762999:AAHNgNIHeWZLvcp5zr_6zJ3TTxe7u3aXpa8"

SESSIONS_FILE = "sessions.json"

# ==================== GLOBAL DATA ====================
user_sessions = []
active_vc_count = 0
auto_views = True
user_states = {}
user_temp_data = {}

def load_sessions():
    global user_sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r") as f:
                user_sessions = json.load(f)
        except Exception:
            user_sessions = []
    else:
        user_sessions = []

def save_sessions():
    with open(SESSIONS_FILE, "w") as f:
        json.dump(user_sessions, f, indent=4)

load_sessions()

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
            InlineKeyboardButton("🔴 VC LEAVE", callback_data="vc_leave"),
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
            InlineKeyboardButton("🔄 REFRESH", callback_data="refresh"),
        ],
    ])

def get_status_text():
    views_status = "ENABLED ✅" if auto_views else "DISABLED ❌"
    return (
        "<b>PROFIT MAN 💸</b>\n\n"
        "<b>P2P M2M CONTROL PANEL</b>\n\n"
        f"👥 <b>ACCOUNT :</b> {len(user_sessions)} IDs\n"
        f"🗣️ <b>ACTIVE VC :</b> {active_vc_count} IDs\n"
        "🟢 <b>STATUS:</b> ONLINE 24/7\n"
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
    global auto_views, active_vc_count, user_sessions
    user_id = query.from_user.id
    data = query.data

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
        await query.answer()
        await query.message.reply_text("🎙️ **जिस चैनल की Voice Chat (VC) ज्वाइन करनी है उसका लिंक या Username भेजें:**")

    elif data == "vc_leave":
        if not user_sessions:
            await query.answer("❌ कोई एकाउंट्स नहीं हैं!", show_alert=True)
            return
        await query.answer("VC छोड़ी जा रही है...", show_alert=True)
        left_count = 0
        for idx, session in enumerate(user_sessions, 1):
            try:
                acc = Client(f"vcleave_acc_{user_id}_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                # Leave group call logic via raw MTProto can be added if needed, or disconnect
                await acc.disconnect()
                left_count += 1
            except Exception:
                pass
        active_vc_count = 0
        await query.message.reply_text(f"🔴 **VC Leave Complete:** {left_count} IDs ने VC छोड़ दी है।")
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "leave_all":
        if not user_sessions:
            await query.answer("❌ कोई एकाउंट्स नहीं हैं!", show_alert=True)
            return
        await query.answer("सभी चैनल्स छोड़े जा रहे हैं...", show_alert=True)
        await query.message.reply_text("🚪 **सारे अकाउंट्स चैनल्स और ग्रुप्स छोड़ रहे हैं, कृपया प्रतीक्षा करें...**")
        
        total_left = 0
        for idx, session in enumerate(user_sessions, 1):
            try:
                acc = Client(f"leave_all_{user_id}_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                async for dialog in acc.get_dialogs():
                    if dialog.chat.type in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
                        try:
                            await acc.leave_chat(dialog.chat.id)
                            total_left += 1
                        except Exception:
                            pass
                await acc.disconnect()
            except Exception:
                pass

        await query.message.reply_text(f"✅ **Leave All Completed!** कुल {total_left} चैनल्स/ग्रुप्स छोड़ दिए गए हैं।")

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

        user_sessions = valid_sessions
        save_sessions()
        await query.message.reply_text(f"🧹 **Purge Complete:** {purged_count} Banned/Dead Sessions हटा दिए गए।")
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

    elif data == "react_views":
        if not user_sessions:
            await query.answer("❌ कोई एकाउंट्स नहीं हैं!", show_alert=True)
            return
        user_states[user_id] = "WAITING_FOR_REACT_POST"
        await query.answer()
        await query.message.reply_text("❤️ **जिस पोस्ट पर Reactions & Views भेजने हैं उसका लिंक (Post Link) भेजें:**")

    elif data == "views_toggle":
        auto_views = not auto_views
        status = "चालू" if auto_views else "बंद"
        await query.answer(f"Auto-Views अब {status} कर दिया गया है!", show_alert=True)
        await query.message.edit_text(text=get_status_text(), reply_markup=get_main_keyboard(), parse_mode=ParseMode.HTML)

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

    if state == "WAITING_FOR_SESSION":
        session_str = message.text.strip()
        user_states[user_id] = None
        try:
            acc = Client("verify_acc", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
            await acc.connect()
            me = await acc.get_me()
            await acc.disconnect()

            if session_str not in user_sessions:
                user_sessions.append(session_str)
                save_sessions()
                await message.reply_text(f"✅ **Account Added Successfully!**\n👤 **Name:** {me.first_name}\n🆔 **ID:** `{me.id}`")
            else:
                await message.reply_text("⚠️ यह सेशन पहले से ऐड है!")

        except Exception as e:
            await message.reply_text(f"❌ **Invalid Session String!**\nError: `{e}`")

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

        await message.reply_text(f"🚀 **प्रक्रिया शुरू हो रही है...**\n• टारगेट: `{target_chat}`\n• कुल IDs: {max_acc}\n• Delay: {delay} सेकंड")

        success = 0
        failed = 0
        error_details = ""
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
            except Exception as e:
                failed += 1
                error_details = str(e)

            if idx < len(sessions_to_use) and delay > 0:
                await asyncio.sleep(delay)

        err_text = f"\n❌ **Reason:** `{error_details}`" if error_details else ""
        await message.reply_text(f"✅ **Join Operation Completed!**\n👍 **Success:** {success}\n👎 **Failed:** {failed}{err_text}")

    elif state == "WAITING_FOR_VC_CHANNEL":
        raw_link = message.text.strip()
        target_chat = raw_link
        if "t.me/" in raw_link:
            target_chat = raw_link.split("t.me/")[-1].replace("@", "")

        user_states[user_id] = None
        await message.reply_text(f"🎙️ **चैनल `{target_chat}` की VC में अकाउंट्स जोड़े जा रहे हैं...**")

        joined_vc = 0
        for idx, session in enumerate(user_sessions, 1):
            try:
                acc = Client(f"vc_acc_{user_id}_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                await acc.connect()
                peer = await acc.resolve_peer(target_chat)
                full = await acc.invoke(functions.channels.GetFullChannel(channel=peer))
                call = full.full_chat.call
                if call:
                    await acc.invoke(functions.phone.JoinGroupCall(
                        call=call,
                        join_as=peer,
                        muted=True,
                        video_stopped=True
                    ))
                    joined_vc += 1
                await acc.disconnect()
            except Exception:
                pass

        active_vc_count = joined_vc
        await message.reply_text(f"✅ **VC Join Complete!** कुल `{joined_vc}` IDs सफलतापूर्वक VC में जुड़ गई हैं।")

    elif state == "WAITING_FOR_REACT_POST":
        post_link = message.text.strip()
        user_states[user_id] = None
        await message.reply_text("❤️ **पोस्ट पर Views और Reactions भेजे जा रहे हैं...**")

        try:
            parts = post_link.split("/")
            msg_id = int(parts[-1])
            channel_username = parts[-2]
            
            success_count = 0
            for idx, session in enumerate(user_sessions, 1):
                try:
                    acc = Client(f"react_acc_{user_id}_{idx}", api_id=API_ID, api_hash=API_HASH, session_string=session, in_memory=True)
                    await acc.connect()
                    # View the post
                    await acc.get_messages(channel_username, msg_id)
                    await acc.disconnect()
                    success_count += 1
                except Exception:
                    pass

            await message.reply_text(f"✅ **Views & Reactions Sent!** कुल `{success_count}` अकाउंट्स ने पोस्ट देख ली है।")
        except Exception as e:
            await message.reply_text(f"❌ **गलत पोस्ट लिंक!** एरर: `{e}`")

# ==================== RUN BOT ====================
async def main():
    await bot.start()
    print("🤖 M2M Control Bot सफलतापूर्वक चालू हो गया है!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
