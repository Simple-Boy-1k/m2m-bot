import os
import logging
import asyncio
import random
import motor.motor_asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import (
    UserDeactivated, 
    SessionRevoked, 
    AuthKeyUnregistered, 
    UserAlreadyParticipant,
    FloodWait,
    UserCreator,
    InviteRequestSent,
    ChannelInvalid,
    UsernameInvalid,
    PeerIdInvalid
)
from pyrogram.raw import functions, types

# Logging setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION ====================
API_ID_RAW = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID_RAW = os.environ.get("OWNER_ID")
MONGO_URL = os.environ.get("MONGO_URL")

# Check exact missing variable
missing_vars = []
if not API_ID_RAW: missing_vars.append("API_ID")
if not API_HASH: missing_vars.append("API_HASH")
if not BOT_TOKEN: missing_vars.append("BOT_TOKEN")
if not OWNER_ID_RAW: missing_vars.append("OWNER_ID")
if not MONGO_URL: missing_vars.append("MONGO_URL")

if missing_vars:
    raise ValueError(f"CRITICAL ERROR: Heroku me ye missing hain -> {', '.join(missing_vars)}")

try:
    API_ID = int(API_ID_RAW.strip())
    OWNER_ID = int(OWNER_ID_RAW.strip())
except ValueError:
    raise ValueError("API_ID aur OWNER_ID me sirf numbers hone chahiye!")
# ========================================================================

# MongoDB Connection Setup
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = mongo_client["p2p_m2m_bot_db"]
sessions_col = db["userbot_sessions"]
admins_col = db["bot_admins"]

# Global Memory Storage
ADMIN_IDS = {OWNER_ID}
USERBOT_SESSIONS = {}   # session_string -> Client instance
ACTIVE_VC_COUNT = 0
AUTO_VIEWS_ENABLED = True
USER_STATES = {}

app = Client("account_manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# -------------------- DATABASE LOADER --------------------

async def load_data_from_db():
    global ADMIN_IDS, USERBOT_SESSIONS
    logging.info("MongoDB Database se data load ho raha hai...")

    async for admin_doc in admins_col.find():
        ADMIN_IDS.add(int(admin_doc["user_id"]))

    loaded_count = 0
    async for session_doc in sessions_col.find():
        session_str = session_doc["session"]
        try:
            ubot = Client("ubot_mem", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
            await ubot.start()
            USERBOT_SESSIONS[session_str] = ubot
            loaded_count += 1
        except Exception as e:
            logging.error(f"Saved session invalid: {e}")
            await sessions_col.delete_one({"session": session_str})

    logging.info(f"Database sync complete! Total {loaded_count} accounts aur {len(ADMIN_IDS)} admins restored.")


# -------------------- HELPER FUNCTIONS --------------------

async def join_target_chat(ubot, chat_link: str):
    chat_link = chat_link.strip()
    try:
        chat = await ubot.join_chat(chat_link)
        return True, chat, "Joined Successfully"
    except UserAlreadyParticipant:
        try:
            chat = await ubot.get_chat(chat_link)
            return True, chat, "Already Joined"
        except Exception:
            return True, None, "Already Joined"
    except InviteRequestSent:
        return True, None, "Request Sent (Admin Approval Pending) ⏳"
    except Exception as e:
        err_msg = str(e)
        if "USER_ALREADY_PARTICIPANT" in err_msg:
            return True, None, "Already Joined"
        if "INVITE_REQUEST_SENT" in err_msg:
            return True, None, "Request Sent (Admin Approval Pending) ⏳"
        return False, None, err_msg


async def join_vc_session(ubot, chat_link: str):
    success, chat, msg = await join_target_chat(ubot, chat_link)
    if not success and "Already Joined" not in msg and "Request Sent" not in msg:
        return False, f"Chat Join Error: {msg}"

    try:
        if not chat:
            chat = await ubot.get_chat(chat_link.strip())

        peer = await ubot.resolve_peer(chat.id)
        if chat.type in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            full_chat = await ubot.invoke(functions.channels.GetFullChannel(channel=peer))
        else:
            full_chat = await ubot.invoke(functions.messages.GetFullChat(chat_id=chat.id))

        call = full_chat.full_chat.call
        if not call:
            return False, "Is group/channel me Voice Chat ACTIVE nahi hai!"

        random_ssrc = random.randint(100000, 999999)
        params_data = f'{{"muted": true, "video_stopped": true, "ssrc": {random_ssrc}}}'

        await ubot.invoke(
            functions.phone.JoinGroupCall(
                call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                join_as=await ubot.resolve_peer("me"),
                params=types.DataJSON(data=params_data),
                muted=True
            )
        )
        return True, "VC Connected"
    except Exception as e:
        err_str = str(e)
        if any(x in err_str for x in ["GROUPCALL_SSRC_DUPLICATE", "GROUPCALL_ALREADY_JOINED", "SSRC_DUPLICATE_MUCH"]):
            return True, "Already Connected in VC"
        return False, f"VC Error: {err_str}"


async def leave_all_channels_robust(ubot):
    left_count = 0
    skipped_count = 0

    try:
        async for dialog in ubot.get_dialogs():
            if dialog.chat.type in [ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP]:
                try:
                    await ubot.leave_chat(dialog.chat.id)
                    left_count += 1
                    await asyncio.sleep(0.8)
                except UserCreator:
                    skipped_count += 1
                    continue
                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                    try:
                        await ubot.leave_chat(dialog.chat.id)
                        left_count += 1
                    except Exception:
                        pass
                except Exception:
                    continue
    except Exception as e:
        logging.error(f"Error during channel leave: {e}")

    return left_count, skipped_count


# -------------------- CONTROL PANEL LAYOUTS --------------------

def get_panel_text():
    views_status = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
    return (
        "<b>P2P M2M CONTROL PANEL</b>\n\n"
        f"👥 <b>ACCOUNT</b> : {len(USERBOT_SESSIONS)} IDs\n"
        f"🗣 <b>ACTIVE VC</b> : {ACTIVE_VC_COUNT} IDs\n"
        "🟢 <b>STATUS</b>: ONLINE 24/7 (MongoDB Secured)\n"
        f"👁 <b>AUTO-VIEWS</b>: {views_status}"
    )

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ ADD ACCOUNT", callback_data="add_account"),
            InlineKeyboardButton("🚀 JOIN CHANNEL", callback_data="join_channel")
        ],
        [
            InlineKeyboardButton("🎙 VC JOINER", callback_data="vc_joiner"),
            InlineKeyboardButton("🔴 VC LEAVE", callback_data="vc_leave")
        ],
        [
            InlineKeyboardButton("🚪 LEAVE ALL CHANNEL", callback_data="leave_all_channel"),
            InlineKeyboardButton("🔔 PURGE DEAD", callback_data="purge_dead")
        ],
        [
            InlineKeyboardButton("❤️ REACT + VIEWS", callback_data="react_views"),
            InlineKeyboardButton("👁 VIEWS TOGGLE", callback_data="views_toggle")
        ],
        [
            InlineKeyboardButton("♻️ RECYCLE ACCOUNTS", callback_data="recycle_accounts"),
            InlineKeyboardButton("🔐 ADMIN PANEL", callback_data="admin_panel")
        ],
        [
            InlineKeyboardButton("🔄 REFRESH", callback_data="refresh")
        ]
    ])

def get_admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add New Admin", callback_data="prompt_add_admin")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data="prompt_remove_admin")],
        [InlineKeyboardButton("📜 Admin List", callback_data="list_admins")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ])

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])


# -------------------- COMMAND HANDLERS --------------------

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply_text("⛔ **Access Denied:** Aapke paas access nahi hai.")
        return

    await message.reply_text(
        text=get_panel_text(),
        reply_markup=get_main_keyboard()
    )


# -------------------- CALLBACK QUERY HANDLER --------------------

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    global AUTO_VIEWS_ENABLED, ACTIVE_VC_COUNT
    user_id = callback_query.from_user.id
    
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⛔ Access Denied!", show_alert=True)
        return

    data = callback_query.data

    if data == "add_account":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add Account</b>\n\nApna Pyrogram String Session yahan send karein:",
            reply_markup=get_back_button()
        )

    elif data == "join_channel":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Pehle kam se kam ek account add karein!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_JOIN_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🚀 Join Channel / Group</b>\n\nPublic link (`https://t.me/name`) ya Private Invite Link (`https://t.me/+xxx`) send karein:",
            reply_markup=get_back_button()
        )

    elif data == "vc_joiner":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_VC_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🎙 VC Joiner</b>\n\nJis Group me VC chal rahi hai uska Link ya Username send karein:",
            reply_markup=get_back_button()
        )

    elif data == "vc_leave":
        ACTIVE_VC_COUNT = 0
        await callback_query.answer("VC status reseted!", show_alert=True)
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    elif data == "leave_all_channel":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return
        
        await callback_query.answer("Mass channel cleanup start ho raha hai...", show_alert=True)
        await callback_query.edit_message_text("⏳ **Cleaning Process Active:** Sabhi accounts se channels/groups leave kiye ja rahe hain...")

        total_left, total_skipped = 0, 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            left, skipped = await leave_all_channels_robust(ubot)
            total_left += left
            total_skipped += skipped

        await callback_query.edit_message_text(
            text=(
                "<b>🚪 LEAVE ALL CHANNELS COMPLETE</b>\n\n"
                f"✅ <b>Successfully Left:</b> {total_left} Channels/Groups\n"
                f"⚠️ <b>Skipped (Owned/Created):</b> {total_skipped} Channels"
            ),
            reply_markup=get_back_button()
        )

    elif data == "purge_dead":
        await callback_query.answer("Testing accounts...", show_alert=True)
        dead_count = 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            try:
                await ubot.get_me()
            except (UserDeactivated, SessionRevoked, AuthKeyUnregistered, Exception):
                del USERBOT_SESSIONS[session_str]
                await sessions_col.delete_one({"session": session_str})
                dead_count += 1
        
        await callback_query.edit_message_text(
            text=f"<b>🔔 Purge Complete</b>\n\n{dead_count} dead accounts MongoDB aur Bot se remove kar diye gaye.",
            reply_markup=get_back_button()
        )

    elif data == "react_views":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Pehle account add karein!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_POST_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>❤️ React + Views</b>\n\nTelegram Post ka Link send karein (`https://t.me/channel/123`):",
            reply_markup=get_back_button()
        )

    elif data == "views_toggle":
        AUTO_VIEWS_ENABLED = not AUTO_VIEWS_ENABLED
        status_msg = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
        await callback_query.answer(f"Auto-Views: {status_msg}", show_alert=True)
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    elif data == "recycle_accounts":
        await callback_query.answer("Recycling all accounts...", show_alert=True)
        recycled = 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            try:
                await ubot.stop()
                await ubot.start()
                recycled += 1
            except Exception:
                pass
        await callback_query.edit_message_text(
            text=f"✅ Total {recycled} accounts successfully recycle/restart hue.",
            reply_markup=get_back_button()
        )

    elif data == "refresh":
        await callback_query.answer("Refreshed! 🔄")
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    elif data == "admin_panel":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Only Main Owner can manage Admin Panel!", show_alert=True)
            return
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nYahan se aap naye Admin add ya remove kar sakte hain:",
            reply_markup=get_admin_menu_keyboard()
        )

    elif data == "prompt_add_admin":
        if user_id != OWNER_ID:
            return
        USER_STATES[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add New Admin</b>\n\nTelegram User ID send karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]])
        )

    elif data == "prompt_remove_admin":
        if user_id != OWNER_ID:
            return
        remove_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                remove_buttons.append([InlineKeyboardButton(f"❌ Remove: {aid}", callback_data=f"rem_adm_{aid}")])

        if not remove_buttons:
            await callback_query.answer("Koi extra Admin nahi hai!", show_alert=True)
            return

        remove_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➖ Remove Admin Panel</b>\n\nJis Admin ko hatana hai click karein:",
            reply_markup=InlineKeyboardMarkup(remove_buttons)
        )

    elif data.startswith("rem_adm_"):
        if user_id != OWNER_ID:
            return
        target_id = int(data.split("_")[2])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)
            await admins_col.delete_one({"user_id": target_id})
            await callback_query.answer("Admin removed from MongoDB!", show_alert=True)
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nAdmin remove ho gaya.",
            reply_markup=get_admin_menu_keyboard()
        )

    elif data == "list_admins":
        admin_text = "<b>📜 Current Admins List:</b>\n\n"
        for aid in ADMIN_IDS:
            role = " (Main Owner)" if aid == OWNER_ID else " (Admin)"
            admin_text += f"• <code>{aid}</code>{role}\n"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=admin_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]])
        )

    elif data == "back_to_main":
        USER_STATES.pop(user_id, None)
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())


# -------------------- INPUT PROCESSING HANDLER --------------------

@app.on_message(filters.private & ~filters.command(["start"]))
async def message_input_handler(client, message):
    user_id = message.from_user.id
    state = USER_STATES.get(user_id)

    if not state or user_id not in ADMIN_IDS:
        return

    text = message.text.strip()

    if state == "WAITING_FOR_SESSION":
        try:
            temp_client = Client("ubot_temp", api_id=API_ID, api_hash=API_HASH, session_string=text, in_memory=True)
            await temp_client.start()
            me = await temp_client.get_me()
            USERBOT_SESSIONS[text] = temp_client
            
            await sessions_col.update_one({"session": text}, {"$set": {"session": text, "user_id": me.id}}, upsert=True)
            
            USER_STATES.pop(user_id, None)
            await message.reply_text(
                f"✅ **Account Saved to MongoDB!**\n\n• Name: {me.first_name}\n• ID: <code>{me.id}</code>",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            await message.reply_text(f"❌ **Invalid Session String:**\n`{str(e)}`\n\nDobara sahi string session bhejein.")

    elif state == "WAITING_FOR_JOIN_LINK":
        USER_STATES.pop(user_id, None)
        msg = await message.reply_text("⏳ Processing accounts join...")
        joined, failed, reasons = 0, 0, []

        for session_str, ubot in USERBOT_SESSIONS.items():
            ok, chat_obj, err_msg = await join_target_chat(ubot, text)
            if ok:
                joined += 1
            else:
                failed += 1
                reasons.append(err_msg)

        detail_text = f"✅ **Join Operation Complete**\n\n• Joined/Already in Chat: {joined}\n• Failed: {failed}"
        if reasons:
            detail_text += f"\n\n❌ **Error Detail:** {reasons[0]}"
        await msg.edit_text(detail_text)

    elif state == "WAITING_FOR_VC_LINK":
        global ACTIVE_VC_COUNT
        USER_STATES.pop(user_id, None)
        msg = await message.reply_text("⏳ Connecting Voice Chat...")
        connected, failed, vc_errors = 0, 0, []

        for session_str, ubot in USERBOT_SESSIONS.items():
            ok, err_msg = await join_vc_session(ubot, text)
            if ok:
                connected += 1
            else:
                failed += 1
                vc_errors.append(err_msg)

        ACTIVE_VC_COUNT = connected
        resp_text = f"🎙 **VC Join Status**\n\n• Connected: {connected}\n• Failed: {failed}"
        if vc_errors:
            resp_text += f"\n\n⚠️ **Reason:** {vc_errors[0]}"
        await msg.edit_text(resp_text)

    elif state == "WAITING_FOR_POST_LINK":
        USER_STATES.pop(user_id, None)
        try:
            parts = text.split("/")
            channel = parts[-2]
            msg_id = int(parts[-1])
            success = 0
            for session_str, ubot in USERBOT_SESSIONS.items():
                try:
                    await ubot.get_messages(channel, msg_id)
                    await ubot.send_reaction(channel, msg_id, "❤️")
                    success += 1
                except (ChannelInvalid, UsernameInvalid, PeerIdInvalid):
                    continue
                except Exception:
                    continue
            await message.reply_text(f"✅ Post par {success} Views + Reactions bhej diye gaye!", reply_markup=get_main_keyboard())
        except Exception:
            await message.reply_text("❌ Post Link Format galat hai! Clean link bhejein (Example: `https://t.me/channel_name/123`).", reply_markup=get_main_keyboard())

    elif state == "WAITING_FOR_ADMIN_ID":
        if user_id == OWNER_ID and text.isdigit():
            new_id = int(text)
            ADMIN_IDS.add(new_id)
            await admins_col.update_one({"user_id": new_id}, {"$set": {"user_id": new_id}}, upsert=True)
            
            USER_STATES.pop(user_id, None)
            await message.reply_text(f"✅ User ID <code>{new_id}</code> MongoDB me Admin save ho gaya.", reply_markup=get_admin_menu_keyboard())
        else:
            await message.reply_text("❌ Sahi numeric Telegram User ID bhejein.")


# -------------------- BOT RUNNER WITH DB LOADER --------------------

async def main():
    await app.start()
    await load_data_from_db()
    print("Bot is fully active and MongoDB secured!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
