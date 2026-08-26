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

# Global Storage
ADMIN_IDS = {OWNER_ID}
USERBOT_SESSIONS = {}
ACTIVE_VC_COUNT = 0
CURRENT_VC_CHAT = None
AUTO_VIEWS_ENABLED = True
ONLINE_247_ENABLED = True
USER_STATES = {}

app = Client(
    "account_manager_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# -------------------- DATABASE LOADER --------------------

async def load_data_from_db():
    global ADMIN_IDS, USERBOT_SESSIONS
    logging.info("MongoDB se database load ho raha hai...")

    async for admin_doc in admins_col.find():
        ADMIN_IDS.add(int(admin_doc["user_id"]))

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
        "🔔 <b>ADMIN ACTIVITY LOG</b>\n\n"
        f"👤 <b>Admin:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>)\n"
        f"🛠 <b>Action:</b> {action_msg}"
    )
    try:
        await client.send_message(OWNER_ID, log_text)
    except Exception as e:
        logging.error(f"Owner Log Error: {e}")


async def join_target_chat(ubot, chat_link: str):
    chat_link = chat_link.strip()
    try:
        chat = await ubot.join_chat(chat_link)
        return True, chat, "Joined Successfully ✅"
    except UserAlreadyParticipant:
        try:
            chat = await ubot.get_chat(chat_link)
            return True, chat, "Already Participant ✅"
        except Exception:
            return True, None, "Already Participant ✅"
    except InviteRequestSent:
        return True, None, "Request Sent (Admin Approval Pending) ⏳"
    except FloodWait as e:
        return False, None, f"Telegram Wait ({e.value}s Limit)"
    except Exception as e:
        err_msg = str(e)
        if "FLOOD_WAIT" in err_msg:
            match = re.search(r'\d+', err_msg)
            sec = match.group() if match else "120"
            return False, None, f"Telegram Limit ({sec}s Wait)"
        if "USER_ALREADY_PARTICIPANT" in err_msg:
            return True, None, "Already Participant ✅"
        if "INVITE_REQUEST_SENT" in err_msg:
            return True, None, "Request Sent (Approval Pending) ⏳"
        if "INVITE_HASH_EXPIRED" in err_msg:
            return False, None, "Invite Link Expired"
        return False, None, "Network / Invalid Link"


async def join_vc_session(ubot, chat_link: str):
    success, chat, msg = await join_target_chat(ubot, chat_link)
    if not success and "Already Participant" not in msg and "Request Sent" not in msg:
        return False, f"Chat Join Fail: {msg}"

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
            return False, "Voice Chat ACTIVE nahi hai!"

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
        return True, "VC Connected ✅"
    except Exception as e:
        err_str = str(e)
        if any(x in err_str for x in ["GROUPCALL_SSRC_DUPLICATE", "GROUPCALL_ALREADY_JOINED", "SSRC_DUPLICATE_MUCH"]):
            return True, "Already In VC ✅"
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
        row.append(InlineKeyboardButton(f"{i} Rq", callback_data=f"selrq_{i}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)


def build_delay_buttons(rq_count):
    delays = [
        ("⚡ 2 Sec", 2),
        ("⚡ 5 Sec", 5),
        ("⚡ 10 Sec", 10),
        ("⚡ 15 Sec", 15),
        ("⚡ 30 Sec", 30),
        ("⚡ 45 Sec", 45),
        ("⏱ 1 Min", 60),
        ("⏱ 2 Min", 120),
        ("⏱ 5 Min", 300),
        ("⏱ 10 Min", 600),
        ("⏱ 15 Min", 900),
        ("⏱ 30 Min", 1800),
        ("⏱ 45 Min", 2700),
        ("⏱ 1 Hour", 3600),
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
        
    keyboard.append([InlineKeyboardButton("🔙 Back to Request Selection", callback_data="menu_join")])
    return InlineKeyboardMarkup(keyboard)

# -------------------- DASHBOARD & TEXT FORMATTERS --------------------

def get_panel_text():
    views_st = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
    presence_st = "ONLINE 24/7 🟢" if ONLINE_247_ENABLED else "OFF 🔴"

    return (
        "╔═════════════════════════╗\n"
        "║  <b>👑 WINEX P2P / M2M MANAGER</b>\n"
        "╚═════════════════════════╝\n\n"
        "┌  <b>SYSTEM STATUS OVERVIEW</b>\n"
        f"├ 👥 <b>Total Userbots :</b> <code>{len(USERBOT_SESSIONS)}</code>\n"
        f"├ 🎙 <b>Active VC IDs :</b> <code>{ACTIVE_VC_COUNT}</code>\n"
        f"├ 🛡 <b>System Admins :</b> <code>{len(ADMIN_IDS)}</code>\n"
        f"├ 👁 <b>Auto-Views :</b> {views_st}\n"
        f"└ 🌐 <b>Presence :</b> {presence_st}\n\n"
        "✨ <b>Neeche Menu se Category choose karein:</b>"
    )


def get_main_keyboard(user_id=None):
    enabled = BUTTON_COLOUR

    keyboard = [
        [
            create_safe_button("📁 Account Hub", "menu_accounts", enabled),
            create_safe_button("⚡ Join & Requests", "menu_join", enabled),
        ],
        [
            create_safe_button("🎙 Voice Chat Hub", "menu_vc", enabled),
            create_safe_button("❤️ React & Views", "menu_engagement", enabled),
        ],
        [
            create_safe_button("🤖 Profile Auto", "menu_automation", enabled),
            create_safe_button("🧹 Mass Cleaning", "menu_mass", enabled),
        ],
        [
            create_safe_button("🔐 Admin Security", "menu_admin", enabled),
            create_safe_button("🔄 Refresh Panel", "action_refresh", enabled),
        ],
        [
            # Owner contact username updated here
            InlineKeyboardButton("👑 Owner Contact", url="https://t.me/Simple_Boy_1k")
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


def get_back_button(target_menu="main"):
    cb_data = "back_to_main" if target_menu == "main" else f"menu_{target_menu}"
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Menu", callback_data=cb_data)
    ]])

# -------------------- COMMAND HANDLER --------------------

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply_text("⛔ **Access Denied:** Aap Authorized Admin Nahi Hain!")
        return

    await message.reply_text(
        text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
    )

# -------------------- CALLBACK QUERY HANDLER --------------------

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    global AUTO_VIEWS_ENABLED, ONLINE_247_ENABLED, ACTIVE_VC_COUNT
    user_id = callback_query.from_user.id

    if user_id not in ADMIN_IDS:
        await callback_query.answer("⛔ Access Denied!", show_alert=True)
        return

    data = callback_query.data

    if data == "back_to_main":
        USER_STATES.pop(user_id, None)
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    elif data == "action_refresh":
        await callback_query.answer("Dashboard Refreshed! 🔄")
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    # 1. ACCOUNT HUB MENU
    elif data == "menu_accounts":
        await callback_query.answer()
        kb = [
            [
                InlineKeyboardButton("➕ Add Account", callback_data="act_add_acc"),
                InlineKeyboardButton("🔔 Purge Dead", callback_data="act_purge_dead")
            ]
        ]
        
        if USERBOT_SESSIONS:
            for s_str, info in list(USERBOT_SESSIONS.items()):
                phone_lbl = info["phone"]
                kb.append([
                    InlineKeyboardButton(f"❌ Remove {phone_lbl}", callback_data=f"delacc_{hash(s_str)}")
                ])
                
        kb.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")])

        await callback_query.edit_message_text(
            text=(
                "📁 <b>ACCOUNT HUB MANAGEMENT</b>\n\n"
                f"📊 Total Active Connected IDs: <code>{len(USERBOT_SESSIONS)}</code>\n\n"
                "📌 Kisi specific account ko remove karne ke liye ❌ par click karein:"
            ),
            reply_markup=InlineKeyboardMarkup(kb)
        )

    elif data.startswith("delacc_"):
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
            await callback_query.answer(f"Account {removed_phone} Removed!", show_alert=True)
        else:
            await callback_query.answer("Account Nahi Mila!", show_alert=True)

        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_accounts"
        ))

    elif data == "act_add_acc":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await callback_query.answer()
        add_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ String Generator Bot", url="https://t.me/String_Seasone_robot?start=promoted")],
            [InlineKeyboardButton("🔙 Back to Accounts Hub", callback_data="menu_accounts")]
        ])
        await callback_query.edit_message_text(
            text=(
                "<b>➕ ADD NEW ACCOUNT</b>\n\n"
                "1️⃣ Pyrogram V2 String Session nikalein.\n"
                "2️⃣ String Session code ko chat me send karein.\n\n"
                "👉 Direct Text String Bhejein:"
            ),
            reply_markup=add_kb
        )

    elif data == "act_purge_dead":
        await send_log_to_owner(client, callback_query.from_user, "Dead Accounts Clean Up Kiya")
        await callback_query.answer("Testing all sessions...", show_alert=True)
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
            text=f"<b>🔔 Purge Complete</b>\n\nTotal <b>{dead_count}</b> dead accounts Database se clean ho gaye.",
            reply_markup=get_back_button("accounts")
        )

    # 2. JOIN & REQUESTS MENU
    elif data == "menu_join":
        await callback_query.answer()
        total_acc = len(USERBOT_SESSIONS)
        
        if total_acc == 0:
            await callback_query.edit_message_text(
                text="❌ <b>Koi bhi active account nahi hai!</b> Pehle Account Hub se accounts add karein.",
                reply_markup=get_back_button("main")
            )
            return

        await callback_query.edit_message_text(
            text=(
                "⚡ <b>JOIN & REQUESTS HUB</b>\n\n"
                f"👥 Total Available Userbots: <code>{total_acc}</code>\n\n"
                "👉 Kitni Requests (Accounts) join karwani hain select karein:"
            ),
            reply_markup=build_rq_buttons(total_acc)
        )

    elif data.startswith("selrq_"):
        rq_count = int(data.split("_")[1])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                f"📌 Selected Requests: <code>{rq_count} Rq</code>\n\n"
                "⏱ <b>Per Member Gap/Delay Select Karein:</b>\n"
                "(2 Seconds se lekar 1 Hour tak delay ka option neeche diya gaya hai)"
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
                f"✅ <b>Configuration Saved!</b>\n\n"
                f"• Requests Count: <code>{rq_count} Rq</code>\n"
                f"• Delay Gap: <code>{delay_str}</code>\n\n"
                "👉 Target Chat Link (Public / Private Invite) Send Karein:"
            ),
            reply_markup=get_back_button("join")
        )

    # 3. VOICE CHAT HUB
    elif data == "menu_vc":
        await callback_query.answer()
        vc_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎙 Join VC", callback_data="vchub_join"),
                InlineKeyboardButton("🔴 Leave VC", callback_data="vchub_leave")
            ],
            [InlineKeyboardButton(f"📊 VC Active Status: {ACTIVE_VC_COUNT} IDs", callback_data="action_refresh")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="🎙 <b>VOICE CHAT HUB</b>\n\nSelect Voice Chat Action:",
            reply_markup=vc_kb
        )

    elif data == "vchub_join":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_VC_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="🎙 <b>JOIN VC</b>\n\nGroup Link send karein jahan Voice Chat Active hai:",
            reply_markup=get_back_button("vc")
        )

    elif data == "vchub_leave":
        await send_log_to_owner(client, callback_query.from_user, "VC Leave Task Activated")
        left_total = await leave_vc_all()
        await callback_query.answer(f"{left_total} IDs Disconnected!", show_alert=True)
        await callback_query.edit_message_text(
            text=f"🔴 <b>VC DISCONNECTED</b>\n\nTotal <b>{left_total}</b> accounts Voice Chat se leave ho chuke hain.",
            reply_markup=get_back_button("vc")
        )

    # 4. REACT & VIEWS HUB
    elif data == "menu_engagement":
        await callback_query.answer()
        eng_st = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
        eng_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("❤️ Send Post React + Views", callback_data="eng_send_react")],
            [InlineKeyboardButton(f"👁 Auto-Views Status: {eng_st}", callback_data="eng_toggle_views")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="❤️ <b>ENGAGEMENT & VIEWS HUB</b>\n\nSelect Post Engagement Tool:",
            reply_markup=eng_kb
        )

    elif data == "eng_send_react":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Pehle Accounts Add Karein!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_POST_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="❤️ <b>React + Views</b>\n\nTelegram Channel / Group Post Link Send Karein:",
            reply_markup=get_back_button("engagement")
        )

    elif data == "eng_toggle_views":
        AUTO_VIEWS_ENABLED = not AUTO_VIEWS_ENABLED
        st = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
        await send_log_to_owner(client, callback_query.from_user, f"Auto Views Toggle -> {st}")
        await callback_query.answer(f"Auto Views: {st}", show_alert=True)
        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_engagement"
        ))

    # 5. AUTOMATION MENU
    elif data == "menu_automation":
        await callback_query.answer()
        p_st = "24/7 ONLINE ✅" if ONLINE_247_ENABLED else "OFF 🔴"

        auto_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🟢 24/7 Presence: {p_st}", callback_data="auto_toggle_presence")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="🤖 <b>PROFILE AUTOMATION HUB</b>\n\nAutomation Features Toggle Karein:",
            reply_markup=auto_kb
        )

    elif data == "auto_toggle_presence":
        ONLINE_247_ENABLED = not ONLINE_247_ENABLED
        await callback_query.answer(f"24/7 Presence: {'ONLINE' if ONLINE_247_ENABLED else 'OFFLINE'}", show_alert=True)
        await callback_handler(client, CallbackQuery(
            id=callback_query.id, from_user=callback_query.from_user,
            chat_instance=callback_query.chat_instance, message=callback_query.message,
            data="menu_automation"
        ))

    # 6. MASS CLEANING MENU
    elif data == "menu_mass":
        await callback_query.answer()
        mass_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚪 Leave All Channels / Groups", callback_data="mass_leave_channels")],
            [InlineKeyboardButton("♻️ Recycle / Restart Sessions", callback_data="mass_recycle_accounts")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
        ])
        await callback_query.edit_message_text(
            text="🧹 <b>MASS CLEANING & RESTART TOOLS</b>\n\nMass Action Select Karein:",
            reply_markup=mass_kb
        )

    elif data == "mass_leave_channels":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Sirf Main Owner leave karwa sakta hai!", show_alert=True)
            return
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return

        await callback_query.answer("Mass Leave Process Active...", show_alert=True)
        await callback_query.edit_message_text("⏳ <b>Mass Leave Active:</b> Channels se accounts silently leave kar rahe hain...")

        total_l, total_s = 0, 0
        for s_str, data_acc in list(USERBOT_SESSIONS.items()):
            l, s = await leave_all_channels_robust(data_acc["client"])
            total_l += l
            total_s += s

        await callback_query.edit_message_text(
            text=f"<b>🚪 MASS LEAVE COMPLETE</b>\n\n✅ Successfully Left: <b>{total_l}</b>\n⚠️ Skipped (Owner): <b>{total_s}</b>",
            reply_markup=get_back_button("mass")
        )

    elif data == "mass_recycle_accounts":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Sirf Main Owner kar sakta hai!", show_alert=True)
            return
        await callback_query.answer("Recycling sessions...", show_alert=True)
        recycled = 0
        for s_str, data_acc in list(USERBOT_SESSIONS.items()):
            try:
                await data_acc["client"].stop()
                await data_acc["client"].start()
                recycled += 1
            except Exception:
                pass
        await callback_query.edit_message_text(
            text=f"✅ Total <b>{recycled}</b> sessions successfully restarted.",
            reply_markup=get_back_button("mass")
        )

    # 7. ADMIN SECURITY PANEL
    elif data == "menu_admin":
        await callback_query.answer()
        
        adm_buttons = [
            [InlineKeyboardButton("➕ Add Admin", callback_data="adm_add_prompt")]
        ]
        
        if user_id == OWNER_ID:
            adm_buttons[0].append(InlineKeyboardButton("➖ Remove Admin", callback_data="adm_rem_prompt"))

        adm_buttons.append([InlineKeyboardButton("📜 Active Admin List", callback_data="adm_list")])
        adm_buttons.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")])

        await callback_query.edit_message_text(
            text="🔐 <b>ADMIN SECURITY CONTROL</b>\n\nManage Bot Access & System Admins:",
            reply_markup=InlineKeyboardMarkup(adm_buttons)
        )

    elif data == "adm_add_prompt":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Sirf Main Owner Add kar sakta hai!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add New Admin</b>\n\nTelegram User ID Send Karein:",
            reply_markup=get_back_button("admin")
        )

    elif data == "adm_rem_prompt":
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Sirf Main Owner Remove kar sakta hai!", show_alert=True)
            return
        
        rem_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                rem_buttons.append([InlineKeyboardButton(f"❌ Remove: {aid}", callback_data=f"removeadm_{aid}")])

        if not rem_buttons:
            await callback_query.answer("Koi extra Admin nahi hai!", show_alert=True)
            return
        rem_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="menu_admin")])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➖ Remove Admin Panel</b>\n\nRemove karne ke liye Admin ID click karein:",
            reply_markup=InlineKeyboardMarkup(rem_buttons)
        )

    elif data.startswith("removeadm_"):
        if user_id != OWNER_ID:
            await callback_query.answer("⛔ Sirf Main Owner hi Admin remove kar sakta hai!", show_alert=True)
            return
        target_id = int(data.split("_")[1])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)
            await admins_col.delete_one({"user_id": target_id})
            await callback_query.answer("Admin Removed!", show_alert=True)
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN SECURITY CONTROL</b>\n\nAdmin Access Revoked.",
            reply_markup=get_back_button("admin")
        )

    elif data == "adm_list":
        admin_text = "<b>📜 SYSTEM ADMINS LIST:</b>\n\n"
        for aid in ADMIN_IDS:
            role = " (Main Owner)" if aid == OWNER_ID else " (Bot Admin)"
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
    state = USER_STATES.get(user_id)

    if not state or user_id not in ADMIN_IDS:
        return

    text = message.text.strip()
    state_type = state.get("type") if isinstance(state, dict) else state

    if state_type == "WAITING_FOR_SESSION":
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
            phone_num = f"+{me.phone_number}" if me.phone_number else f"ID: {me.id}"

            USERBOT_SESSIONS[text] = {
                "client": temp_client,
                "phone": phone_num,
                "name": me.first_name or "User",
                "user_id": me.id
            }

            await sessions_col.update_one(
                {"session": text},
                {"$set": {"session": text, "user_id": me.id}},
                upsert=True,
            )

            USER_STATES.pop(user_id, None)
            await send_log_to_owner(client, message.from_user, f"Naya Account Add Kiya:\nName: {me.first_name}\nPhone: {phone_num}")

            await message.reply_text(
                f"✅ <b>Account Saved to MongoDB!</b>\n\n• Name: <b>{me.first_name}</b>\n• Phone: <code>{phone_num}</code>",
                reply_markup=get_main_keyboard(user_id),
            )
        except Exception as e:
            await message.reply_text(f"❌ <b>Invalid Session String:</b>\n`{str(e)}`\n\nDobara sahi string session send karein.")

    elif state_type == "WAITING_FOR_JOIN_LINK":
        rq_count = int(state.get("rq_count", 1))
        delay_sec = float(state.get("delay_sec", 1.0))
        delay_str = state.get("delay_str", f"{delay_sec} Sec")

        USER_STATES.pop(user_id, None)
        total_available = len(USERBOT_SESSIONS)

        if rq_count > total_available:
            await message.reply_text(
                f"❌ <b>Order Cancelled:</b>\n\nAvailable Accounts: <b>{total_available}</b>\nSelected Rq: <b>{rq_count}</b>",
                reply_markup=get_main_keyboard(user_id),
            )
            return

        msg = await message.reply_text(
            f"⚡ <b>Join Request Active</b>\n\nTarget Rq: <code>{rq_count}</code>\nDelay: <code>{delay_str}</code>\n\nRequests start ho rahi hain..."
        )

        await send_log_to_owner(client, message.from_user, f"🚀 Join Order Lagaya:\n🔗 Link: {text}\n🎯 Total Rq: {rq_count}\n⏳ Delay: {delay_str}")

        target_sessions = list(USERBOT_SESSIONS.items())[:rq_count]
        joined, failed, error_logs = 0, 0, []

        for idx, (s_str, data_acc) in enumerate(target_sessions, 1):
            ok, _, err_msg = await join_target_chat(data_acc["client"], text)
            if ok:
                joined += 1
            else:
                failed += 1
                if err_msg not in error_logs:
                    error_logs.append(err_msg)

            if idx < rq_count:
                await asyncio.sleep(delay_sec)

        res_text = (
            f"✅ <b>Join Operation Finished</b>\n\n"
            f"• Total Rq Sent: <b>{rq_count}</b>\n"
            f"• Delay Gap: <b>{delay_str}</b>\n"
            f"• Successful Joins: <b>{joined}</b>\n"
            f"• Failed: <b>{failed}</b>"
        )
        if error_logs:
            res_text += f"\n\n❌ <b>Reason:</b> {error_logs[0]}"
        await msg.edit_text(res_text, reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_VC_LINK":
        global ACTIVE_VC_COUNT, CURRENT_VC_CHAT
        USER_STATES.pop(user_id, None)
        CURRENT_VC_CHAT = text

        await send_log_to_owner(client, message.from_user, f"🎙 VC Join Order: {text}")

        msg = await message.reply_text("⏳ Connecting Voice Chat across all userbots...")
        connected, failed, vc_errs = 0, 0, []

        for s_str, data_acc in USERBOT_SESSIONS.items():
            ok, err_msg = await join_vc_session(data_acc["client"], text)
            if ok:
                connected += 1
            else:
                failed += 1
                vc_errs.append(err_msg)

        ACTIVE_VC_COUNT = connected
        resp_t = f"🎙 <b>VC Join Complete</b>\n\n• Connected: <b>{connected}</b>\n• Failed: <b>{failed}</b>"
        if vc_errs:
            resp_t += f"\n\n⚠️ <b>Detail:</b> {vc_errs[0]}"
        await msg.edit_text(resp_t, reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_POST_LINK":
        USER_STATES.pop(user_id, None)
        await send_log_to_owner(client, message.from_user, f"❤️ React + Views Order: {text}")

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
                await message.reply_text("⚠️ <b>0 Reactions Delivered!</b>\nPrivate Channel me accounts joined rehne chahiye.", reply_markup=get_main_keyboard(user_id))
            else:
                await message.reply_text(f"✅ Post par <b>{success}</b> Views + Reactions bhej diye gaye!", reply_markup=get_main_keyboard(user_id))
        except Exception as e:
            await message.reply_text(f"❌ <b>Post Link Format Error:</b> `{e}`", reply_markup=get_main_keyboard(user_id))

    elif state_type == "WAITING_FOR_ADMIN_ID":
        if user_id == OWNER_ID and text.isdigit():
            new_id = int(text)
            ADMIN_IDS.add(new_id)
            await admins_col.update_one({"user_id": new_id}, {"$set": {"user_id": new_id}}, upsert=True)
            USER_STATES.pop(user_id, None)
            await message.reply_text(f"✅ User ID <code>{new_id}</code> Saved as Admin.", reply_markup=get_main_keyboard(user_id))
        else:
            await message.reply_text("❌ Valid Numeric Telegram User ID Bhejein.")

# -------------------- BOT RUNNER --------------------

async def main():
    await app.start()
    await load_data_from_db()
    
    print("WINEX Control Panel Bot Fully Started ✅")
    await asyncio.Event().wait()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
