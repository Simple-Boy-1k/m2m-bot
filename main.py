import asyncio
import logging
import os
import random
import re
import motor.motor_asyncio
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import (
    AuthKeyUnregistered,
    ChannelInvalid,
    FloodWait,
    InviteRequestSent,
    PeerIdInvalid,
    SessionRevoked,
    UserAlreadyParticipant,
    UserCreator,
    UserDeactivated,
    UsernameInvalid,
    RPCError
)
from pyrogram.raw import functions, types
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config_buttons import create_safe_button
from keep_alive import keep_alive

# Start Web Server for keeping alive on VPS/Render
keep_alive()

# Logging Setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION ====================
API_ID_RAW = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID_RAW = os.environ.get("OWNER_ID")
MONGO_URL = os.environ.get("MONGO_URL")

BUTTON_COLOUR = os.environ.get("BUTTON_COLOUR", "True").lower() in ("true", "1", "t")

missing_vars = []
if not API_ID_RAW:
    missing_vars.append("API_ID")
if not API_HASH:
    missing_vars.append("API_HASH")
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not OWNER_ID_RAW:
    missing_vars.append("OWNER_ID")
if not MONGO_URL:
    missing_vars.append("MONGO_URL")

if missing_vars:
    raise ValueError(f"CRITICAL ERROR: Environment variables missing: {', '.join(missing_vars)}")

try:
    API_ID = int(API_ID_RAW.strip())
    OWNER_ID = int(OWNER_ID_RAW.strip())
except ValueError:
    raise ValueError("API_ID aur OWNER_ID me sirf integer numbers hone chahiye!")

# MongoDB Connection
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = mongo_client["p2p_m2m_bot_db"]
sessions_col = db["userbot_sessions"]
admins_col = db["bot_admins"]
pending_req_col = db["pending_admin_requests"]

# Global Storage
ADMIN_IDS = {OWNER_ID}
EXEMPT_ADMINS = {OWNER_ID}  # In admins par anti-cheat check nahi lagega
USERBOT_SESSIONS = {}
ACTIVE_VC_COUNT = 0
CURRENT_VC_CHAT = None
AUTO_VIEWS_ENABLED = True
ONLINE_247_ENABLED = True
USER_STATES = {}
STOP_FLAGS = {"join": False}  # Task control flag

app = Client(
    "account_manager_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# -------------------- DATABASE LOADER --------------------

async def load_data_from_db():
    global ADMIN_IDS, EXEMPT_ADMINS, USERBOT_SESSIONS
    logging.info("MongoDB se database load ho raha hai...")

    ADMIN_IDS = {OWNER_ID}
    EXEMPT_ADMINS = {OWNER_ID}

    async for admin_doc in admins_col.find():
        aid = int(admin_doc["user_id"])
        ADMIN_IDS.add(aid)
        if admin_doc.get("exempt", False):
            EXEMPT_ADMINS.add(aid)

    loaded_count = 0
    async for session_doc in sessions_col.find():
        session_str = session_doc.get("session")
        if not session_str:
            continue
        try:
            ubot = Client(
                f"ubot_{loaded_count}_{random.randint(1000,9999)}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_str,
                in_memory=True,
            )
            await ubot.start()
            me = await ubot.get_me()
            phone_num = f"+{me.phone_number}" if me.phone_number else f"ID: {me.id}"
            
            USERBOT_SESSIONS[session_str] = {
                "client": ubot,
                "phone": phone_num,
                "name": me.first_name or "User",
                "user_id": me.id
            }
            loaded_count += 1
        except Exception as e:
            logging.error(f"Saved session error: {e}")
            await sessions_col.delete_one({"session": session_str})

    logging.info(f"Database Sync Complete! Restored {loaded_count} accounts & {len(ADMIN_IDS)} admins.")

# -------------------- HELPER FUNCTIONS --------------------

async def send_log_to_owner(client, user, action_msg):
    if user.id == OWNER_ID:
        return
    log_text = (
        "🩸 <b>[WARFARE LOG] OVERLORD EXECUTION</b> 🩸\n\n"
        f"👤 <b>Executor:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>)\n"
        f"⚔️ <b>Strike Target:</b> {action_msg}"
    )
    try:
        await client.send_message(OWNER_ID, log_text)
    except Exception as e:
        logging.error(f"Owner Log Error: {e}")

async def join_target_chat(ubot, chat_link: str):
    chat_link = chat_link.strip()
    try:
        chat = await ubot.join_chat(chat_link)
        return True, chat, "Infiltrated Base ⚔️"
    except UserAlreadyParticipant:
        try:
            chat = await ubot.get_chat(chat_link)
            return True, chat, "Inside Fortress 🩸"
        except Exception:
            return True, None, "Inside Fortress 🩸"
    except InviteRequestSent:
        return True, None, "Pending Breach ⏳"
    except FloodWait as e:
        return False, None, f"Cooldown Lock ({e.value}s Wait)"
    except Exception as e:
        err_msg = str(e)
        if "FLOOD_WAIT" in err_msg:
            match = re.search(r'\d+', err_msg)
            sec = match.group() if match else "120"
            return False, None, f"Cooldown Lock ({sec}s Wait)"
        if "USER_ALREADY_PARTICIPANT" in err_msg:
            return True, None, "Inside Fortress 🩸"
        if "INVITE_REQUEST_SENT" in err_msg:
            return True, None, "Pending Breach ⏳"
        if "INVITE_HASH_EXPIRED" in err_msg:
            return False, None, "Target Link Expired ❌"
        return False, None, "Target Shield Active / Invalid"

async def join_vc_session(ubot, chat_link: str):
    success, chat, msg = await join_target_chat(ubot, chat_link)
    if not success and "Inside Fortress" not in msg and "Pending Breach" not in msg:
        return False, f"Breach Failed: {msg}"

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
            return False, "Target VC Offline/Destroyed! 💀"

        random_ssrc = random.randint(100000, 999999)
        params_data = f'{{"muted": true, "video_stopped": true, "ssrc": {random_ssrc}}}'

        await ubot.invoke(
            functions.phone.JoinGroupCall(
                call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                join_as=await ubot.resolve_peer("me"),
                params=types.DataJSON(data=params_data),
                muted=True,
            )
        )
        return True, "VC Invaded 🎙⚔️"
    except Exception as e:
        err_str = str(e)
        if any(x in err_str for x in ["GROUPCALL_SSRC_DUPLICATE", "GROUPCALL_ALREADY_JOINED", "SSRC_DUPLICATE_MUCH"]):
            return True, "Already In VC 💀"
        return False, f"VC Error: {err_str}"

async def leave_vc_all():
    global ACTIVE_VC_COUNT, CURRENT_VC_CHAT
    if not CURRENT_VC_CHAT:
        return 0

    left_count = 0
    target = CURRENT_VC_CHAT
    CURRENT_VC_CHAT = None

    for session_str, data in list(USERBOT_SESSIONS.items()):
        ubot = data["client"]
        try:
            chat = await ubot.get_chat(target)
            peer = await ubot.resolve_peer(chat.id)
            if chat.type in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
                full_chat = await ubot.invoke(functions.channels.GetFullChannel(channel=peer))
            else:
                full_chat = await ubot.invoke(functions.messages.GetFullChat(chat_id=chat.id))

            call = full_chat.full_chat.call
            if call:
                await ubot.invoke(
                    functions.phone.LeaveGroupCall(
                        call=types.InputGroupCall(id=call.id, access_hash=call.access_hash),
                        source=0,
                    )
                )
                left_count += 1
        except Exception as e:
            logging.error(f"VC Leave Error: {e}")

    ACTIVE_VC_COUNT = 0
    return left_count

async def leave_all_channels_robust(ubot):
    left_count, skipped_count = 0, 0
    try:
        async for dialog in ubot.get_dialogs():
            if dialog.chat.type in [ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP]:
                try:
                    await ubot.leave_chat(dialog.chat.id)
                    left_count += 1
                    await asyncio.sleep(0.3)
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
        logging.error(f"Leave Channels Error: {e}")
    return left_count, skipped_count

# -------------------- KEYBOARD GENERATORS --------------------

def build_rq_buttons(total_acc):
    keyboard = []
    row = []
    for i in range(1, total_acc + 1):
        row.append(InlineKeyboardButton(f"🩸 {i} Bots", callback_data=f"selrq_{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def build_delay_buttons(rq_count):
    delays = [
        ("⚡ 2 Sec", 2), ("⚡ 5 Sec", 5), ("⚡ 10 Sec", 10), ("⚡ 15 Sec", 15),
        ("⚡ 30 Sec", 30), ("⚡ 45 Sec", 45), ("⏱ 1 Min", 60), ("⏱ 2 Min", 120),
        ("⏱ 5 Min", 300), ("⏱ 10 Min", 600), ("⏱ 15 Min", 900), ("⏱ 30 Min", 1800),
        ("⏱ 45 Min", 2700), ("⏱ 1 Hour", 3600),
    ]
    keyboard = []
    row = []
    for label, sec in delays:
        row.append(InlineKeyboardButton(label, callback_data=f"delsel_{rq_count}_{sec}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("🔙 BACK TO ARMY SELECTION", callback_data="menu_join")])
    return InlineKeyboardMarkup(keyboard)

# -------------------- DASHBOARD & TEXT FORMATTERS --------------------

def get_panel_text():
    views_st = "🩸 [SPYING ACTIVE]" if AUTO_VIEWS_ENABLED else "💀 [SYSTEM OFF]"
    presence_st = "🔴 [GOD MODE ONLINE]" if ONLINE_247_ENABLED else "🖤 [GHOST MODE OFF]"

    return (
        "<b>☠️ ━━━━━━━━━━━━━━━━━━━━━ ☠️</b>\n"
        "<b>⚡ 𝕾.𝕶 𝕭𝕺𝕾𝕾 𝕯𝕰𝖁𝕴𝕷 𝕺𝖁𝕄𝕽𝕷𝕺𝕽𝕯 ⚡</b>\n"
        "<b>☠️ ━━━━━━━━━━━━━━━━━━━━━ ☠️</b>\n\n"
        "<b>░▒▓█ 𝕯𝕰𝕬𝕭𝕳 𝕮𝕺𝕸𝕸𝕬𝕹𝕯 𝕮𝕰𝕹𝕭𝕰𝖄 █▓▒░</b>\n\n"
        f"<b>🩸 [⚔️] WARFARE ARMY   :</b> <code>{len(USERBOT_SESSIONS)} WARRIORS</code>\n"
        f"<b>🩸 [🎙] VOICE INVASION  :</b> <code>{ACTIVE_VC_COUNT} ACTIVE</code>\n"
        f"<b>🩸 [👑] OVERLORD CLAN   :</b> <code>{len(ADMIN_IDS)} LORDS</code>\n"
        f"<b>🩸 [👁] AUTO SPY ENGINE :</b> {views_st}\n"
        f"<b>🩸 [🌐] SYSTEM PRESENCE  :</b> {presence_st}\n\n"
        "<b>💀 WARNING: HIGH-VOLTAGE CYBER MATRIX - UNTOUCHABLE ZONE! 💀</b>\n"
        "<b>⚔️ Strike Command Select Karein:</b>"
    )

def get_main_keyboard(user_id=None):
    enabled = BUTTON_COLOUR
    keyboard = [
        [
            create_safe_button("🩸 [ WAR ARMY ]", "menu_accounts", enabled),
            create_safe_button("⚔️ [ RAID INFILTRATE ]", "menu_join", enabled),
        ],
        [
            create_safe_button("🎙 [ VC INVASION ]", "menu_vc", enabled),
            create_safe_button("💣 [ BOMBARDMENT ]", "menu_engagement", enabled),
        ],
        [
            create_safe_button("☣️ [ BIO AUTOMATION ]", "menu_automation", enabled),
            create_safe_button("💀 [ MASS SLAUGHTER ]", "menu_mass", enabled),
        ],
        [
            create_safe_button("🛡 [ WAR LORDS ]", "menu_admin", enabled),
            create_safe_button("⚡ [ REBOOT MATRIX ]", "action_refresh", enabled),
        ],
        [
            InlineKeyboardButton("👑 OVERLORD KING S.K", url="https://t.me/Simple_Boy_1k")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button(target_menu="main"):
    cb_data = "back_to_main" if target_menu == "main" else f"menu_{target_menu}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("☠️ RETREAT TO MATRIX", callback_data=cb_data)
    ]])

# -------------------- COMMAND HANDLER --------------------

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # 🔥 ANTI-CHEAT: Check Sub-Admin Account Count (Excluding Owner-Added Admins)
    if user_id in ADMIN_IDS and user_id not in EXEMPT_ADMINS:
        user_accounts_count = await sessions_col.count_documents({"added_by": user_id})
        if user_accounts_count < 3:
            ADMIN_IDS.remove(user_id)
            await admins_col.delete_one({"user_id": user_id})
            await pending_req_col.delete_one({"user_id": user_id})
            await message.reply_text(
                "🚨 <b>SYSTEM ACCESS ANNIHILATED!</b> 🚨\n\n"
                "Aapke active accounts 3 se kam hain! System ne aapka Access destroy kar diya. Entry ke liye kam se kam 3 accounts poore karein!"
            )
            return

    # SYSTEM 1: If User is not Admin (Request System)
    if user_id not in ADMIN_IDS:
        user_accounts_count = await sessions_col.count_documents({"added_by": user_id})
        
        req_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ADD WARRIOR BOT", callback_data="user_add_acc")],
            [InlineKeyboardButton("📤 REQUEST CLAN ENTRY", callback_data="user_send_req")],
            [InlineKeyboardButton("👑 DIRECT OVERLORD CONTACT", url="https://t.me/contect1234")]
        ])
        
        await message.reply_text(
            text=(
                "☠️ <b>WELCOME TO S.K DEVIL OVERLORD MATRIX!</b> ☠️\n\n"
                "🔒 <b>CLAN ACCESS RULES:</b>\n"
                "1️⃣ Minimum <b>3 Warrior Accounts</b> add karke army built karein.\n"
                "2️⃣ Uske baad <b>'Request Clan Entry'</b> dabayein.\n"
                "3️⃣ Main Overlord verified karke access unlock karega! 🔥\n\n"
                f"⚔️ Active Army Contribution: <b>{user_accounts_count} / 3</b>"
            ),
            reply_markup=req_kb
        )
        return

    # SYSTEM 2: If User IS Admin (Show Panel)
    await message.reply_text(
        text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
    )

# -------------------- CALLBACK QUERY HANDLER --------------------

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    global AUTO_VIEWS_ENABLED, ONLINE_247_ENABLED, ACTIVE_VC_COUNT, STOP_FLAGS
    user_id = callback_query.from_user.id
    data = callback_query.data

    # 🛑 STOP TASK BUTTON HANDLER
    if data == "stop_join_task":
        STOP_FLAGS["join"] = True
        await callback_query.answer("🛑 ATTACK ABORTED BY OVERLORD COMMAND!", show_alert=True)
        return

    # 🔥 ANTI-CHEAT: Button action par sub-admin count check (Excluding Owner-Added Admins)
    if user_id in ADMIN_IDS and user_id not in EXEMPT_ADMINS:
        user_accounts_count = await sessions_col.count_documents({"added_by": user_id})
        if user_accounts_count < 3:
            ADMIN_IDS.remove(user_id)
            await admins_col.delete_one({"user_id": user_id})
            await pending_req_col.delete_one({"user_id": user_id})
            USER_STATES.pop(user_id, None)

            await callback_query.answer("🚨 Clan Access Destroyed! Minimum 3 Accounts Required.", show_alert=True)

            req_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD WARRIOR BOT", callback_data="user_add_acc")],
                [InlineKeyboardButton("📤 REQUEST CLAN ENTRY", callback_data="user_send_req")],
                [InlineKeyboardButton("👑 DIRECT OVERLORD CONTACT", url="https://t.me/contect1234")]
            ])

            await callback_query.edit_message_text(
                text=(
                    "🚨 <b>SYSTEM ACCESS TERMINATED!</b> 🚨\n\n"
                    "Active army accounts 3 se kam ho gaye hain. Access Blocked!\n\n"
                    f"⚔️ Active Army: <b>{user_accounts_count} / 3</b>"
                ),
                reply_markup=req_kb
            )
            return

    # ---------------- NON-ADMIN & REQUEST HANDLERS ----------------
    if user_id not in ADMIN_IDS:
        if data == "user_add_acc":
            USER_STATES[user_id] = "WAITING_FOR_USER_SESSION"
            await callback_query.answer()
            add_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⚡ GENERATE STRING SESSION", url="https://t.me/String_Seasone_robot?start=promoted")],
                [InlineKeyboardButton("🔙 RETREAT", callback_data="user_back_start")]
            ])
            await callback_query.edit_message_text(
                text=(
                    "<b>➕ ADD WARRIOR ACCOUNT TO ARMY</b>\n\n"
                    "1️⃣ Pyrogram V2 String Session Code nikalein.\n"
                    "2️⃣ Chat me paste karke send karein.\n\n"
                    "👉 Send String Session Code:"
                ),
                reply_markup=add_kb
            )
            return

        elif data == "user_back_start":
            USER_STATES.pop(user_id, None)
            await callback_query.answer()
            user_accounts_count = await sessions_col.count_documents({"added_by": user_id})
            req_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD WARRIOR BOT", callback_data="user_add_acc")],
                [InlineKeyboardButton("📤 REQUEST CLAN ENTRY", callback_data="user_send_req")],
                [InlineKeyboardButton("👑 DIRECT OVERLORD CONTACT", url="https://t.me/contect1234")]
            ])
            await callback_query.edit_message_text(
                text=(
                    "☠️ <b>WELCOME TO S.K DEVIL OVERLORD MATRIX!</b> ☠️\n\n"
                    "🔒 <b>CLAN ACCESS RULES:</b>\n"
                    "1️⃣ Minimum <b>3 Warrior Accounts</b> add karke army built karein.\n"
                    "2️⃣ Uske baad <b>'Request Clan Entry'</b> dabayein.\n"
                    "3️⃣ Main Overlord verified karke access unlock karega! 🔥\n\n"
                    f"⚔️ Active Army Contribution: <b>{user_accounts_count} / 3</b>"
                ),
                reply_markup=req_kb
            )
            return

        elif data == "user_send_req":
            user_accounts_count = await sessions_col.count_documents({"added_by": user_id})
            if user_accounts_count < 3:
                await callback_query.answer(f"❌ Access Denied! Need minimum 3 accounts (Current: {user_accounts_count}).", show_alert=True)
                return
            
            existing_req = await pending_req_col.find_one({"user_id": user_id, "status": "pending"})
            if existing_req:
                await callback_query.answer("⏳ Request already dispatched to Overlord!", show_alert=True)
                return

            await pending_req_col.insert_one({"user_id": user_id, "status": "pending"})
            
            owner_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚔️ GRANT CLAN ACCESS", callback_data=f"accept_adm_{user_id}"),
                    InlineKeyboardButton("☠️ REJECT & DESTROY", callback_data=f"reject_adm_{user_id}")
                ]
            ])
            try:
                await client.send_message(
                    OWNER_ID,
                    f"🔔 <b>NEW WARRIOR CLAN ENTRY REQUEST!</b>\n\n"
                    f"👤 User: <a href='tg://user?id={user_id}'>{callback_query.from_user.first_name}</a> (<code>{user_id}</code>)\n"
                    f"📱 Total Accounts Added: <b>{user_accounts_count}</b>\n\n"
                    "Is user ko Clan Access dena hai?",
                    reply_markup=owner_kb
                )
            except Exception as e:
                logging.error(f"Owner notification error: {e}")

            await callback_query.answer("⚔️ Request Sent To King Overlord S.K!", show_alert=True)
            return

        await callback_query.answer("⛔ ACCESS DENIED! You are not in the Clan.", show_alert=True)
        return

    # ---------------- OWNER ACCEPT/REJECT REQUESTS ----------------
    if data.startswith("accept_adm_") or data.startswith("reject_adm_"):
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied! Only Main King Overlord can decide.", show_alert=True)
            return
        
        parts = data.split("_")
        action = parts[0]
        target_user_id = int(parts[2])

        if action == "accept":
            ADMIN_IDS.add(target_user_id)
            await admins_col.update_one({"user_id": target_user_id}, {"$set": {"user_id": target_user_id, "exempt": False}}, upsert=True)
            await pending_req_col.update_one({"user_id": target_user_id}, {"$set": {"status": "accepted"}})
            
            await callback_query.answer("Access Granted! ⚔️", show_alert=True)
            await callback_query.edit_message_text(f"✅ User <code>{target_user_id}</code> is now added to CLAN ROSTER!")
            
            try:
                await client.send_message(
                    target_user_id,
                    "🎉 <b>CLAN ACCESS UNLOCKED BY OVERLORD!</b>\n\nMain Overlord ne access grant kar diya hai! Send `/start` to launch Devil Matrix!"
                )
            except Exception:
                pass
        else:
            await pending_req_col.update_one({"user_id": target_user_id}, {"$set": {"status": "rejected"}})
            await callback_query.answer("Request Destroyed ☠️", show_alert=True)
            await callback_query.edit_message_text(f"❌ Request for User <code>{target_user_id}</code> REJECTED.")
            try:
                await client.send_message(target_user_id, "❌ Clan Access Request Rejected by Overlord.")
            except Exception:
                pass
        return

    # ---------- REGULAR ADMIN ACTIONS BELOW THIS LINE ----------

    if data == "back_to_main":
        USER_STATES.pop(user_id, None)
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    elif data == "action_refresh":
        await callback_query.answer("⚡ MATRIX REBOOTED & REFRESHED!")
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    elif data == "menu_accounts":
        await callback_query.answer()
        kb = []
        add_purge_row = [InlineKeyboardButton("➕ ADD WARRIOR BOT", callback_data="act_add_acc")]
        if user_id == OWNER_ID:
            add_purge_row.append(InlineKeyboardButton("🩸 PURGE DEAD BOTS", callback_data="act_purge_dead"))
        kb.append(add_purge_row)

        if USERBOT_SESSIONS:
            for s_str, info in list(USERBOT_SESSIONS.items()):
                phone_lbl = info["phone"]
                if user_id == OWNER_ID:
                    kb.append([InlineKeyboardButton(f"💀 DESTROY {phone_lbl}", callback_data=f"delacc_{hash(s_str)}")])
                else:
                    kb.append([InlineKeyboardButton(f"⚔️ {phone_lbl} (ARMED)", callback_data="none_action")])
                
        kb.append([InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")])

        panel_title = "🩸 <b>WARFARE ARMY HUB (OVERLORD VIEW)</b>" if user_id == OWNER_ID else "🩸 <b>WARFARE ARMY HUB (CLAN VIEW)</b>"
        sub_text = "📌 Terminate karne ke liye 💀 button dabayein:" if user_id == OWNER_ID else "📋 Active armed warriors list:"

        await callback_query.edit_message_text(
            text=(
                f"{panel_title}\n\n"
                f"⚔️ Total Armed Warriors: <code>{len(USERBOT_SESSIONS)}</code>\n\n"
                f"{sub_text}"
            ),
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data == "none_action":
        await callback_query.answer("Account terminate karne ka access sirf Main Overlord ke paas hai!", show_alert=True)

    elif data.startswith("delacc_"):
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied!", show_alert=True)
            return

        target_hash = data.split("_")[1]
        removed_phone = None
        for s_str, info in list(USERBOT_SESSIONS.items()):
            if str(hash(s_str)) == target_hash:
                try:
                    await info["client"].stop()
                except Exception:
                    pass
                removed_phone = info["phone"]
                del USERBOT_SESSIONS[s_str]
                await sessions_col.delete_one({"session": s_str})
                break

        if removed_phone:
            await callback_query.answer(f"Warrior {removed_phone} Terminated!", show_alert=True)
        else:
            await callback_query.answer("Account Not Found!", show_alert=True)

        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_accounts"
        ))

    elif data == "act_add_acc":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await callback_query.answer()
        add_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ GENERATE STRING CODE", url="https://t.me/String_Seasone_robot?start=promoted")],
            [InlineKeyboardButton("🔙 RETREAT TO ARMY HUB", callback_data="menu_accounts")]
        ])
        await callback_query.edit_message_text(
            text=(
                "<b>➕ ADD WARRIOR BOT TO ARMY</b>\n\n"
                "1️⃣ Pyrogram V2 String Session code nikalein.\n"
                "2️⃣ Direct send karein.\n\n"
                "👉 Send String Code:"
            ),
            reply_markup=add_kb
        )

    elif data == "act_purge_dead":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied!", show_alert=True)
            return

        await send_log_to_owner(client, callback_query.from_user, "Dead Accounts Purged")
        await callback_query.answer("Scanning and purging dead warrior bots...", show_alert=True)
        dead_count = 0
        for session_str, data_acc in list(USERBOT_SESSIONS.items()):
            ubot = data_acc["client"]
            try:
                await ubot.get_me()
            except Exception:
                try:
                    await ubot.stop()
                except Exception:
                    pass
                del USERBOT_SESSIONS[session_str]
                await sessions_col.delete_one({"session": session_str})
                dead_count += 1

        await callback_query.edit_message_text(
            text=f"<b>💀 PURGE COMPLETE</b>\n\nTotal <b>{dead_count}</b> dead bots destroyed from DB.",
            reply_markup=get_back_button("accounts")
        )

    elif data == "menu_join":
        await callback_query.answer()
        total_acc = len(USERBOT_SESSIONS)
        
        if total_acc == 0:
            await callback_query.edit_message_text(
                text="💀 <b>NO WARRIOR BOTS AVAILABLE!</b> Pehle Army add karein.",
                reply_markup=get_back_button("main")
            )
            return

        await callback_query.edit_message_text(
            text=(
                "⚔️ <b>RAID & INFILTRATION HUB</b>\n\n"
                f"👥 Total Armed Bots: <code>{total_acc}</code>\n\n"
                "👉 Kitni Army se Infiltration karwani hai:"
            ),
            reply_markup=build_rq_buttons(total_acc)
        )

    elif data.startswith("selrq_"):
        rq_count = int(data.split("_")[1])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                f"📌 Target Attack Force: <code>{rq_count} Bots</code>\n\n"
                "⏱ <b>Select Attack Cooldown Delay:</b>"
            ),
            reply_markup=build_delay_buttons(rq_count)
        )

    elif data.startswith("delsel_"):
        parts = data.split("_")
        rq_count = int(parts[1])
        delay_sec = float(parts[2])

        if delay_sec >= 3600:
            delay_str = f"{int(delay_sec / 3600)} Hour"
        elif delay_sec >= 60:
            delay_str = f"{int(delay_sec / 60)} Min"
        else:
            delay_str = f"{int(delay_sec)} Sec"

        USER_STATES[user_id] = {
            "type": "WAITING_FOR_JOIN_LINK",
            "rq_count": rq_count,
            "delay_sec": delay_sec,
            "delay_str": delay_str
        }
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                f"⚔️ <b>ATTACK CONFIGURATION SAVED!</b>\n\n"
                f"• Attack Force: <code>{rq_count} Bots</code>\n"
                f"• Cooldown Delay: <code>{delay_str}</code>\n\n"
                "👉 Target Group / Channel Link Send Karein:"
            ),
            reply_markup=get_back_button("join")
        )

    elif data == "menu_vc":
        await callback_query.answer()
        vc_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎙 INFILTRATE VC", callback_data="vchub_join"),
                InlineKeyboardButton("🔴 RETREAT VC", callback_data="vchub_leave")
            ],
            [InlineKeyboardButton(f"⚡ Active VC Force: {ACTIVE_VC_COUNT} Bots", callback_data="action_refresh")],
            [InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="🎙 <b>VOICE CHAT INVASION HUB</b>\n\nSelect VC Strike Command:",
            reply_markup=vc_kb
        )

    elif data == "vchub_join":
        if not USERBOT_SESSIONS:
            await callback_query.answer("No Active Userbots!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_VC_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="🎙 <b>VC RAID COMMAND</b>\n\nVoice Chat Link Send Karein:",
            reply_markup=get_back_button("vc")
        )

    elif data == "vchub_leave":
        await send_log_to_owner(client, callback_query.from_user, "VC Disconnect Triggered")
        left_total = await leave_vc_all()
        await callback_query.answer(f"{left_total} Bots Disconnected!", show_alert=True)
        await callback_query.edit_message_text(
            text=f"🔴 <b>VC RETREAT FINISHED</b>\n\nTotal <b>{left_total}</b> warrior bots disconnected from VC.",
            reply_markup=get_back_button("vc")
        )

    elif data == "menu_engagement":
        await callback_query.answer()
        eng_st = "🩸 [SPYING ACTIVE]" if AUTO_VIEWS_ENABLED else "💀 [OFF]"
        eng_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💣 BOMBARDMENT ATTACK", callback_data="eng_send_react")],
            [InlineKeyboardButton(f"👁 Auto-Views Mode: {eng_st}", callback_data="eng_toggle_views")],
            [InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="💣 <b>POST BOMBARDMENT & VIEWS HUB</b>\n\nSelect Post Attack Command:",
            reply_markup=eng_kb
        )

    elif data == "eng_send_react":
        if not USERBOT_SESSIONS:
            await callback_query.answer("No Armed Bots!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_POST_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="💣 <b>React + Views Bombardment</b>\n\nTarget Post Link Send Karein:",
            reply_markup=get_back_button("engagement")
        )

    elif data == "eng_toggle_views":
        AUTO_VIEWS_ENABLED = not AUTO_VIEWS_ENABLED
        st = "ACTIVE 🩸" if AUTO_VIEWS_ENABLED else "OFF 💀"
        await send_log_to_owner(client, callback_query.from_user, f"Auto Views Toggle -> {st}")
        await callback_query.answer(f"Auto Views: {st}", show_alert=True)
        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_engagement"
        ))

    elif data == "menu_automation":
        await callback_query.answer()
        p_st = "🔴 [GOD MODE ONLINE]" if ONLINE_247_ENABLED else "🖤 [GHOST MODE OFF]"

        auto_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"☣️ Presence Status: {p_st}", callback_data="auto_toggle_presence")],
            [InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="☣️ <b>BIO-AUTOMATION MATRIX</b>\n\nToggle Online Ghost Status:",
            reply_markup=auto_kb
        )

    elif data == "auto_toggle_presence":
        ONLINE_247_ENABLED = not ONLINE_247_ENABLED
        await callback_query.answer(f"Status: {'GOD MODE ONLINE' if ONLINE_247_ENABLED else 'GHOST MODE OFF'}", show_alert=True)
        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_automation"
        ))

    elif data == "menu_mass":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied! Main King Overlord Only.", show_alert=True)
            return

        await callback_query.answer()
        mass_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("💀 MASS SLAUGHTER (LEAVE ALL)", callback_data="mass_leave_channels")],
            [InlineKeyboardButton("♻️ RECYCLE / FORCE RESTART ARMY", callback_data="mass_recycle_accounts")],
            [InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="💀 <b>MASS SLAUGHTER MATRIX (OVERLORD EXCLUSIVE)</b>\n\nSelect Mass Action:",
            reply_markup=mass_kb
        )

    elif data == "mass_leave_channels":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied!", show_alert=True)
            return
        if not USERBOT_SESSIONS:
            await callback_query.answer("No Armed Bots!", show_alert=True)
            return

        await callback_query.answer("Mass Leave Initiated...", show_alert=True)
        await callback_query.edit_message_text("💀 <b>MASS SLAUGHTER ACTIVE:</b> Purging channels across all sessions...")

        total_l, total_s = 0, 0
        for s_str, data_acc in list(USERBOT_SESSIONS.items()):
            l, s = await leave_all_channels_robust(data_acc["client"])
            total_l += l
            total_s += s

        await callback_query.edit_message_text(
            text=f"<b>💀 MASS PURGE FINISHED</b>\n\n✅ Left Channels/Groups: <b>{total_l}</b>\n⚠️ Skipped (Owner Chat): <b>{total_s}</b>",
            reply_markup=get_back_button("mass")
        )

    elif data == "mass_recycle_accounts":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied!", show_alert=True)
            return
        await callback_query.answer("Recycling Army...", show_alert=True)
        recycled = 0
        for s_str, data_acc in list(USERBOT_SESSIONS.items()):
            try:
                await data_acc["client"].stop()
                await data_acc["client"].start()
                recycled += 1
            except Exception:
                pass
        await callback_query.edit_message_text(
            text=f"✅ Total <b>{recycled}</b> sessions recycled & back online.",
            reply_markup=get_back_button("mass")
        )

    elif data == "menu_admin":
        await callback_query.answer()
        
        adm_buttons = [
            [InlineKeyboardButton("⚔️ RECRUIT LORD", callback_data="adm_add_prompt")]
        ]
        
        if user_id == OWNER_ID:
            adm_buttons[0].append(InlineKeyboardButton("🩸 ELIMINATE LORD", callback_data="adm_rem_prompt"))

        adm_buttons.append([InlineKeyboardButton("🛡 CLAN ROSTER LIST", callback_data="adm_list")])
        adm_buttons.append([InlineKeyboardButton("☠️ RETREAT TO MAIN MATRIX", callback_data="back_to_main")])

        await callback_query.edit_message_text(
            text="🛡 <b>WAR LORDS CLAN MATRIX</b>\n\nManage Overlord Access:",
            reply_markup=InlineKeyboardMarkup(adm_buttons)
        )

    elif data == "adm_add_prompt":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ King Overlord Only!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>⚔️ Recruit New War Lord</b>\n\nTarget Telegram User ID Send Karein:",
            reply_markup=get_back_button("admin")
        )

    elif data == "adm_rem_prompt":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ King Overlord Only!", show_alert=True)
            return
        
        rem_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                rem_buttons.append([InlineKeyboardButton(f"🩸 Eliminate: {aid}", callback_data=f"removeadm_{aid}")])

        if not rem_buttons:
            await callback_query.answer("No Sub-Lords in Clan!", show_alert=True)
            return
        rem_buttons.append([InlineKeyboardButton("🔙 RETREAT", callback_data="menu_admin")])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🩸 Eliminate Clan Access</b>\n\nSelect User ID to Revoke Access:",
            reply_markup=InlineKeyboardMarkup(rem_buttons)
        )

    elif data.startswith("removeadm_"):
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Access Denied!", show_alert=True)
            return
        target_id = int(data.split("_")[1])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)
            EXEMPT_ADMINS.discard(target_id)
            await admins_col.delete_one({"user_id": target_id})
            await pending_req_col.delete_one({"user_id": target_id})
            await callback_query.answer("Lord Access Terminated!", show_alert=True)
        await callback_query.edit_message_text(
            text="<b>🛡 CLAN ROSTER</b>\n\nTarget Lord Access Revoked.",
            reply_markup=get_back_button("admin")
        )

    elif data == "adm_list":
        admin_text = "<b>🛡 WAR LORDS CLAN ROSTER:</b>\n\n"
        for aid in ADMIN_IDS:
            role = " (👑 OVERLORD KING S.K)" if aid == OWNER_ID else (" (🔥 EXEMPT LORD)" if aid in EXEMPT_ADMINS else " (⚔️ CLAN LORD)")
            admin_text += f"• <code>{aid}</code>{role}\n"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=admin_text,
            reply_markup=get_back_button("admin")
        )

# -------------------- MESSAGE INPUT HANDLER --------------------

@app.on_message(filters.private & ~filters.command(["start"]))
async def message_input_handler(client, message):
    user_id = message.from_user.id
    text = message.text.strip()
    state = USER_STATES.get(user_id)

    # ---------------- ADD ACCOUNT FOR NON-ADMINS ----------------
    if state == "WAITING_FOR_USER_SESSION":
        if text in USERBOT_SESSIONS or await sessions_col.find_one({"session": text}):
            await message.reply_text("❌ <b>DUPLICATE SESSION CODE!</b>\n\nYe session pehle se army me registered hai!")
            return

        try:
            temp_client = Client(
                f"ubot_user_{user_id}_{random.randint(1000,9999)}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=text,
                in_memory=True,
            )
            await temp_client.start()
            me = await temp_client.get_me()

            is_already_added = any(info.get("user_id") == me.id for info in USERBOT_SESSIONS.values())
            if is_already_added or await sessions_col.find_one({"user_id": me.id}):
                await temp_client.stop()
                await message.reply_text("❌ <b>DUPLICATE ACCOUNT DETECTED!</b>\n\nYe account pehle se army me active hai!")
                return

            phone_num = f"+{me.phone_number}" if me.phone_number else f"ID: {me.id}"

            USERBOT_SESSIONS[text] = {
                "client": temp_client,
                "phone": phone_num,
                "name": me.first_name or "User",
                "user_id": me.id
            }

            await sessions_col.update_one(
                {"session": text},
                {"$set": {"session": text, "user_id": me.id, "added_by": user_id}},
                upsert=True,
            )

            USER_STATES.pop(user_id, None)
            user_accounts_count = await sessions_col.count_documents({"added_by": user_id})

            req_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD MORE WARRIORS", callback_data="user_add_acc")],
                [InlineKeyboardButton("📤 REQUEST CLAN ENTRY", callback_data="user_send_req")],
                [InlineKeyboardButton("🔙 RETREAT", callback_data="user_back_start")]
            ])

            await message.reply_text(
                f"⚔️ <b>Warrior Bot Successfully Armed!</b>\n\n"
                f"• Target ID/Phone: <code>{phone_num}</code>\n"
                f"• Total Contribution: <b>{user_accounts_count} / 3</b>\n\n"
                "3 accounts hone ke baad <b>'Request Clan Entry'</b> button dabayein.",
                reply_markup=req_kb,
            )
        except Exception as e:
            await message.reply_text(f"❌ <b>Invalid String Session:</b>\n`{str(e)}`\n\nDobara sahi string code Send karein.")
        return

    # Normal check for Admins
    if not state or user_id not in ADMIN_IDS:
        return

    state_type = state.get("type") if isinstance(state, dict) else state

    if state_type == "WAITING_FOR_SESSION":
        if text in USERBOT_SESSIONS or await sessions_col.find_one({"session": text}):
            await message.reply_text("❌ <b>DUPLICATE SESSION!</b>\n\nYe code active hai.")
            return

        try:
            temp_client = Client(
                f"ubot_{random.randint(1000,9999)}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=text,
                in_memory=True,
            )
            await temp_client.start()
            me = await temp_client.get_me()

            is_already_added = any(info.get("user_id") == me.id for info in USERBOT_SESSIONS.values())
            if is_already_added or await sessions_col.find_one({"user_id": me.id}):
                await temp_client.stop()
                await message.reply_text("❌ <b>DUPLICATE ACCOUNT!</b>\n\nYe account pehle se registered hai.")
                return

            phone_num = f"+{me.phone_number}" if me.phone_number else f"ID: {me.id}"

            USERBOT_SESSIONS[text] = {
                "client": temp_client,
                "phone": phone_num,
                "name": me.first_name or "User",
                "user_id": me.id
            }

            await sessions_col.update_one(
                {"session": text},
                {"$set": {"session": text, "user_id": me.id, "added_by": user_id}},
                upsert=True,
            )

            USER_STATES.pop(user_id, None)
            await send_log_to_owner(client, message.from_user, f"New Warrior Armed:\nName: {me.first_name}\nPhone: {phone_num}")

            await message.reply_text(
                f"⚔️ <b>Warrior Bot Armed & Saved!</b>\n\n• Name: <b>{me.first_name}</b>\n• Phone: <code>{phone_num}</code>",
                reply_markup=get_main_keyboard(user_id),
            )
        except Exception as e:
            await message.reply_text(f"❌ <b>Invalid String Session:</b>\n`{str(e)}`\n\nDobara sahi code Send karein.")

    elif state_type == "WAITING_FOR_JOIN_LINK":
        rq_count = int(state.get("rq_count", 1))
        delay_sec = float(state.get("delay_sec", 1.0))
        delay_str = state.get("delay_str", f"{delay_sec} Sec")

        USER_STATES.pop(user_id, None)
        total_available = len(USERBOT_SESSIONS)

        if rq_count > total_available:
            await message.reply_text(
                f"❌ <b>ATTACK CANCELLED:</b>\n\nAvailable Army: <b>{total_available}</b>\nRequested Force: <b>{rq_count}</b>",
                reply_markup=get_main_keyboard(user_id),
            )
            return

        # Reset Stop Flag for new task
        STOP_FLAGS["join"] = False

        stop_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 ABORT STRIKE COMMAND", callback_data="stop_join_task")]
        ])

        msg = await message.reply_text(
            f"⚡ <b>RAID INVASION LAUNCHED!</b>\n\n"
            f"🎯 Attack Force: <code>{rq_count} Bots</code>\n"
            f"⏳ Cooldown Delay: <code>{delay_str}</code>\n\n"
            f"⚙️ Infiltrating Target Base...",
            reply_markup=stop_kb
        )

        await send_log_to_owner(client, message.from_user, f"🚀 Raid Order Initiated:\n🔗 Link: {text}\n🎯 Force: {rq_count} Bots\n⏳ Delay: {delay_str}")

        target_sessions = list(USERBOT_SESSIONS.items())[:rq_count]
        joined, failed, error_logs = 0, 0, []
        was_stopped = False

        for idx, (s_str, data_acc) in enumerate(target_sessions, 1):
            if STOP_FLAGS["join"]:
                was_stopped = True
                break

            ok, _, err_msg = await join_target_chat(data_acc["client"], text)
            if ok:
                joined += 1
            else:
                failed += 1
                if err_msg not in error_logs:
                    error_logs.append(err_msg)

            # Live Status Update
            try:
                await msg.edit_text(
                    f"⚡ <b>RAID PROGRESS ({idx}/{rq_count})</b>\n\n"
                    f"⚔️ Infiltrated: <b>{joined}</b> | ❌ Blocked: <b>{failed}</b>\n"
                    f"⏳ Cooldown Delay: <code>{delay_str}</code>\n\n"
                    f"🛑 Click below to emergency abort:",
                    reply_markup=stop_kb
                )
            except Exception:
                pass

            if idx < rq_count:
                slept = 0.0
                while slept < delay_sec:
                    if STOP_FLAGS["join"]:
                        was_stopped = True
                        break
                    await asyncio.sleep(0.5)
                    slept += 0.5
                if was_stopped:
                    break

        STOP_FLAGS["join"] = False

        status_header = "🛑 <b>RAID STRIKE ABORTED BY COMMANDER</b>" if was_stopped else "⚔️ <b>RAID INVASION COMPLETED</b>"
        res_text = (
            f"{status_header}\n\n"
            f"• Target Force: <b>{rq_count}</b>\n"
            f"• Processed: <b>{joined + failed}</b> / <b>{rq_count}</b>\n"
            f"• Infiltrated: <b>{joined}</b>\n"
            f"• Blocked/Failed: <b>{failed}</b>"
        )
        if error_logs:
            res_text += f"\n\n❌ <b>Reason:</b> {error_logs[0]}"
        await msg.edit_text(res_text, reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_VC_LINK":
        global ACTIVE_VC_COUNT, CURRENT_VC_CHAT
        USER_STATES.pop(user_id, None)
        CURRENT_VC_CHAT = text

        await send_log_to_owner(client, message.from_user, f"🎙 VC Raid Order: {text}")

        msg = await message.reply_text("⏳ Launching VC Invasion across warrior bots...")
        connected, failed, vc_errs = 0, 0, []

        for s_str, data_acc in USERBOT_SESSIONS.items():
            ok, err_msg = await join_vc_session(data_acc["client"], text)
            if ok:
                connected += 1
            else:
                failed += 1
                vc_errs.append(err_msg)

        ACTIVE_VC_COUNT = connected
        resp_t = f"🎙 <b>VC INVASION COMPLETED</b>\n\n• Infiltrated VC: <b>{connected} Bots</b>\n• Failed: <b>{failed}</b>"
        if vc_errs:
            resp_t += f"\n\n⚠️ <b>Detail:</b> {vc_errs[0]}"
        await msg.edit_text(resp_t, reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_POST_LINK":
        USER_STATES.pop(user_id, None)
        await send_log_to_owner(client, message.from_user, f"💣 Bombardment Order: {text}")

        try:
            parts = [p for p in text.split("/") if p]
            msg_id = int(parts[-1])
            channel = int(f"-100{parts[-2]}") if (len(parts) >= 4 and parts[-3] == "c") else parts[-2]

            success = 0
            for s_str, data_acc in USERBOT_SESSIONS.items():
                try:
                    ubot = data_acc["client"]
                    await ubot.get_messages(channel, msg_id)
                    await ubot.send_reaction(chat_id=channel, message_id=msg_id, emoji="❤️")
                    success += 1
                except Exception:
                    continue

            if success == 0:
                await message.reply_text("⚠️ <b>0 Reactions Delivered!</b> Bots private target me joined hone chahiye.", reply_markup=get_main_keyboard(user_id))
            else:
                await message.reply_text(f"💣 Target Post par <b>{success}</b> Views + Reactions hit kar diye gaye!", reply_markup=get_main_keyboard(user_id))
        except Exception as e:
            await message.reply_text(f"❌ <b>Post Link Format Error:</b> `{e}`", reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_ADMIN_ID":
        if user_id == OWNER_ID and text.isdigit():
            new_id = int(text)
            ADMIN_IDS.add(new_id)
            EXEMPT_ADMINS.add(new_id)
            
            await admins_col.update_one(
                {"user_id": new_id}, 
                {"$set": {"user_id": new_id, "exempt": True}}, 
                upsert=True
            )
            USER_STATES.pop(user_id, None)
            await message.reply_text(f"⚔️ User ID <code>{new_id}</code> Added to Clan (EXEMPT LORD STATUS).", reply_markup=get_main_keyboard(user_id))
        else:
            await message.reply_text("❌ Send a valid numeric Telegram User ID!")

# -------------------- BOT RUNNER --------------------

async def main():
    await app.start()
    await load_data_from_db()
    
    print("DEVIL OVERLORD MATRIX FULLY ONLINE ✅")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot Stopped Successfully.")
