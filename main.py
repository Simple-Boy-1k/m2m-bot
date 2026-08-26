import asyncio
import logging
import os
import random
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
)
from pyrogram.raw import functions, types
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from config_buttons import create_safe_button

# Logging setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION ====================
API_ID_RAW = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID_RAW = os.environ.get("OWNER_ID")
MONGO_URL = os.environ.get("MONGO_URL")

BUTTON_COLOUR = os.environ.get("BUTTON_COLOUR", "True").lower() in (
    "true",
    "1",
    "t",
)
STYLES = ["primary", "success", "danger"]

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
    raise ValueError(
        f"CRITICAL ERROR: Heroku me ye missing hain -> {', '.join(missing_vars)}"
    )

try:
    API_ID = int(API_ID_RAW.strip())
    OWNER_ID = int(OWNER_ID_RAW.strip())
except ValueError:
    raise ValueError("API_ID aur OWNER_ID me sirf numbers hone chahiye!")

# MongoDB Connection Setup
mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = mongo_client["p2p_m2m_bot_db"]
sessions_col = db["userbot_sessions"]
admins_col = db["bot_admins"]

# Global Memory Storage
ADMIN_IDS = {OWNER_ID}
USERBOT_SESSIONS = {}
ACTIVE_VC_COUNT = 0
CURRENT_VC_CHAT = None
AUTO_VIEWS_ENABLED = True
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
    logging.info("MongoDB Database se data load ho raha hai...")

    async for admin_doc in admins_col.find():
        ADMIN_IDS.add(int(admin_doc["user_id"]))

    loaded_count = 0
    async for session_doc in sessions_col.find():
        session_str = session_doc["session"]
        try:
            ubot = Client(
                "ubot_mem",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_str,
                in_memory=True,
            )
            await ubot.start()
            USERBOT_SESSIONS[session_str] = ubot
            loaded_count += 1
        except Exception as e:
            logging.error(f"Saved session invalid: {e}")
            await sessions_col.delete_one({"session": session_str})

    logging.info(
        f"Database sync complete! Total {loaded_count} accounts aur"
        f" {len(ADMIN_IDS)} admins restored."
    )


# -------------------- HELPER FUNCTIONS --------------------

async def send_log_to_owner(client, user, action_msg):
    if user.id == OWNER_ID:
        return
        
    log_text = (
        "🔔 <b>ADMIN ACTIVITY ALERT</b>\n\n"
        f"👤 <b>Admin:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a> (<code>{user.id}</code>)\n"
        f"🛠 <b>Action:</b> {action_msg}"
    )
    
    try:
        await client.send_message(OWNER_ID, log_text)
    except Exception as e:
        logging.error(f"Owner ko log bhejne me error: {e}")


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
            full_chat = await ubot.invoke(
                functions.channels.GetFullChannel(channel=peer)
            )
        else:
            full_chat = await ubot.invoke(
                functions.messages.GetFullChat(chat_id=chat.id)
            )

        call = full_chat.full_chat.call
        if not call:
            return False, "Is group/channel me Voice Chat ACTIVE nahi hai!"

        random_ssrc = random.randint(100000, 999999)
        params_data = (
            f'{{"muted": true, "video_stopped": true, "ssrc": {random_ssrc}}}'
        )

        await ubot.invoke(
            functions.phone.JoinGroupCall(
                call=types.InputGroupCall(
                    id=call.id, access_hash=call.access_hash
                ),
                join_as=await ubot.resolve_peer("me"),
                params=types.DataJSON(data=params_data),
                muted=True,
            )
        )
        return True, "VC Connected"
    except Exception as e:
        err_str = str(e)
        if any(
            x in err_str
            for x in [
                "GROUPCALL_SSRC_DUPLICATE",
                "GROUPCALL_ALREADY_JOINED",
                "SSRC_DUPLICATE_MUCH",
            ]
        ):
            return True, "Already Connected in VC"
        return False, f"VC Error: {err_str}"


async def leave_vc_all():
    global ACTIVE_VC_COUNT, CURRENT_VC_CHAT
    if not CURRENT_VC_CHAT:
        return 0

    left_count = 0
    target = CURRENT_VC_CHAT
    CURRENT_VC_CHAT = None

    for session_str, ubot in list(USERBOT_SESSIONS.items()):
        try:
            chat = await ubot.get_chat(target)
            peer = await ubot.resolve_peer(chat.id)
            if chat.type in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
                full_chat = await ubot.invoke(
                    functions.channels.GetFullChannel(channel=peer)
                )
            else:
                full_chat = await ubot.invoke(
                    functions.messages.GetFullChat(chat_id=chat.id)
                )

            call = full_chat.full_chat.call
            if call:
                await ubot.invoke(
                    functions.phone.LeaveGroupCall(
                        call=types.InputGroupCall(
                            id=call.id, access_hash=call.access_hash
                        ),
                        source=0,
                    )
                )
                left_count += 1
        except Exception as e:
            logging.error(f"VC Leave Error: {e}")

    ACTIVE_VC_COUNT = 0
    return left_count


async def vc_keepalive_loop():
    global ACTIVE_VC_COUNT
    while True:
        await asyncio.sleep(15)
        if CURRENT_VC_CHAT and USERBOT_SESSIONS:
            connected = 0
            for session_str, ubot in list(USERBOT_SESSIONS.items()):
                try:
                    ok, _ = await join_vc_session(ubot, CURRENT_VC_CHAT)
                    if ok:
                        connected += 1
                except Exception:
                    pass
            ACTIVE_VC_COUNT = connected


async def leave_all_channels_robust(ubot):
    left_count = 0
    skipped_count = 0

    try:
        async for dialog in ubot.get_dialogs():
            if dialog.chat.type in [
                ChatType.CHANNEL,
                ChatType.GROUP,
                ChatType.SUPERGROUP,
            ]:
                try:
                    await ubot.leave_chat(dialog.chat.id)
                    left_count += 1
                    await asyncio.sleep(0.4)
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
        "🟢 <b>STATUS</b>: ONLINE 24/7 (☆𝙎𝘼𝙍𝙆𝘼𝙍 メ 𝙉𝙊𝙓☆)\n"
        f"👁 <b>AUTO-VIEWS</b>: {views_status}\n"
        "Only use for Admins*✅"
    )


def get_main_keyboard(user_id=None):
    enabled = BUTTON_COLOUR
    is_owner = (user_id == OWNER_ID)

    keyboard = [
        [
            create_safe_button("➕ ADD ACCOUNT", "add_account", enabled),
            create_safe_button("🚀 JOIN CHANNEL", "join_channel", enabled),
        ],
        [
            create_safe_button("🎙 VC JOINER", "vc_joiner", enabled),
            create_safe_button("🔴 VC LEAVE", "vc_leave", enabled),
        ]
    ]

    if is_owner:
        keyboard.append([
            create_safe_button("🚪 LEAVE ALL CHANNEL", "leave_all_channel", enabled),
            create_safe_button("🔔 PURGE DEAD", "purge_dead", enabled),
        ])
    else:
        keyboard.append([
            create_safe_button("🔔 PURGE DEAD", "purge_dead", enabled),
        ])

    keyboard.append([
        create_safe_button("❤️ REACT + VIEWS", "react_views", enabled),
        create_safe_button("👁 VIEWS TOGGLE", "views_toggle", enabled),
    ])

    if is_owner:
        keyboard.append([
            create_safe_button("♻️ RECYCLE ACCOUNTS", "recycle_accounts", enabled),
            create_safe_button("🔐 ADMIN PANEL", "admin_panel", enabled),
        ])
    else:
        keyboard.append([
            create_safe_button("🔐 ADMIN PANEL", "admin_panel", enabled),
        ])

    keyboard.append([
        create_safe_button("🔄 REFRESH", "refresh", enabled)
    ])

    return InlineKeyboardMarkup(keyboard)


def get_admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Add New Admin", callback_data="prompt_add_admin"
            )
        ],
        [
            InlineKeyboardButton(
                "➖ Remove Admin", callback_data="prompt_remove_admin"
            )
        ],
        [InlineKeyboardButton("📜 Admin List", callback_data="list_admins")],
        [
            InlineKeyboardButton(
                "🔙 Back to Main Menu", callback_data="back_to_main"
            )
        ],
    ])


def get_back_button():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🔙 Back to Main Menu", callback_data="back_to_main"
        )
    ]])


# -------------------- COMMAND HANDLERS --------------------


@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.reply_text(
            "⛔ **Access Denied:** \n Kya Yrr😆 Admin Nhi Hai tu😝 ."
        )
        return

    await message.reply_text(
        text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
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
        add_acc_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⚡ String Generator Bot",
                    url="https://t.me/String_Seasone_robot?start=promoted",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back to Main Menu", callback_data="back_to_main"
                )
            ],
        ])
        await callback_query.edit_message_text(
            text=(
                "<b>➕ Add Account</b>\n\n"
                "📌 <b>String Session Kaise Nikalein:</b>\n"
                "1️⃣ Pehle @String_Seasone_robot par jayein.\n"
                "2️⃣ Bot me <code>/start</code> dabayein aur <b>Pyrogram V2</b>"
                " select karein.\n"
                "3️⃣ Apna Number, OTP aur 2FA Password daal kar Session String"
                " nikalein.\n\n"
                "👉 Us <b>Pyrogram String Session Code</b> ko yahan send karein:"
            ),
            reply_markup=add_acc_keyboard,
        )

    elif data == "join_channel":
        if not USERBOT_SESSIONS:
            await callback_query.answer(
                "Pehle kam se kam ek account add karein!", show_alert=True
            )
            return
        await callback_query.answer()

        total_accounts = len(USERBOT_SESSIONS)

        rq_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1 Rq", callback_data="rqsel_1"),
                InlineKeyboardButton("2 Rq", callback_data="rqsel_2"),
                InlineKeyboardButton("3 Rq", callback_data="rqsel_3"),
                InlineKeyboardButton("4 Rq", callback_data="rqsel_4"),
                InlineKeyboardButton("5 Rq", callback_data="rqsel_5"),
            ],
            [
                InlineKeyboardButton("6 Rq", callback_data="rqsel_6"),
                InlineKeyboardButton("7 Rq", callback_data="rqsel_7"),
                InlineKeyboardButton("8 Rq", callback_data="rqsel_8"),
                InlineKeyboardButton("9 Rq", callback_data="rqsel_9"),
                InlineKeyboardButton("10 Rq", callback_data="rqsel_10"),
            ],
            [
                InlineKeyboardButton("12 Rq", callback_data="rqsel_12"),
                InlineKeyboardButton("15 Rq", callback_data="rqsel_15"),
                InlineKeyboardButton("20 Rq", callback_data="rqsel_20"),
                InlineKeyboardButton("25 Rq", callback_data="rqsel_25"),
                InlineKeyboardButton("30 Rq", callback_data="rqsel_30"),
            ],
            [
                InlineKeyboardButton("40 Rq", callback_data="rqsel_40"),
                InlineKeyboardButton("50 Rq", callback_data="rqsel_50"),
                InlineKeyboardButton("75 Rq", callback_data="rqsel_75"),
                InlineKeyboardButton("100 Rq", callback_data="rqsel_100"),
            ],
            [
                InlineKeyboardButton(
                    f"⚡ ALL ACCOUNTS ({total_accounts} Rq)",
                    callback_data=f"rqsel_{total_accounts}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Back to Main Menu", callback_data="back_to_main"
                )
            ],
        ])
        await callback_query.edit_message_text(
            text=(
                "🚀 <b>Join Channel / Group</b>\n\n"
                f"📊 <b>Total Active Accounts:</b> <code>{total_accounts}</code>\n\n"
                "1️⃣ <b>Step 1: Total Kitni Requests Bhejni Hain?</b>\n"
                "Jitne accounts use karne hain select karein:"
            ),
            reply_markup=rq_keyboard,
        )

    elif data.startswith("rqsel_"):
        rq_count = int(data.split("_")[1])
        await callback_query.answer()

        delay_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚡ 1 Sec", callback_data=f"delsel_{rq_count}_1"),
                InlineKeyboardButton("⚡ 2 Sec", callback_data=f"delsel_{rq_count}_2"),
                InlineKeyboardButton("⚡ 3 Sec", callback_data=f"delsel_{rq_count}_3"),
                InlineKeyboardButton("⚡ 5 Sec", callback_data=f"delsel_{rq_count}_5"),
            ],
            [
                InlineKeyboardButton("⚡ 10 Sec", callback_data=f"delsel_{rq_count}_10"),
                InlineKeyboardButton("⚡ 15 Sec", callback_data=f"delsel_{rq_count}_15"),
                InlineKeyboardButton("⚡ 30 Sec", callback_data=f"delsel_{rq_count}_30"),
                InlineKeyboardButton("⚡ 45 Sec", callback_data=f"delsel_{rq_count}_45"),
            ],
            [
                InlineKeyboardButton("⏱️ 1 Min", callback_data=f"delsel_{rq_count}_60"),
                InlineKeyboardButton("⏱️ 2 Min", callback_data=f"delsel_{rq_count}_120"),
                InlineKeyboardButton("⏱️ 5 Min", callback_data=f"delsel_{rq_count}_300"),
            ],
            [
                InlineKeyboardButton("⏱️ 10 Min", callback_data=f"delsel_{rq_count}_600"),
                InlineKeyboardButton("⏱️ 15 Min", callback_data=f"delsel_{rq_count}_900"),
                InlineKeyboardButton("⏱️ 30 Min", callback_data=f"delsel_{rq_count}_1800"),
            ],
            [
                InlineKeyboardButton("⏳ 1 Hour", callback_data=f"delsel_{rq_count}_3600"),
                InlineKeyboardButton("⏳ 2 Hours", callback_data=f"delsel_{rq_count}_7200"),
                InlineKeyboardButton("⏳ 3 Hours", callback_data=f"delsel_{rq_count}_10800"),
            ],
            [InlineKeyboardButton("🔙 Back to Rq Menu", callback_data="join_channel")],
        ])
        await callback_query.edit_message_text(
            text=(
                f"📌 <b>Selected Requests:</b> <code>{rq_count} Rq</code>\n\n"
                "2️⃣ <b>Step 2: Har Member Ke Beech Kitna Delay/Gap Chahiye?</b>\n"
                "Seconds, Minutes ya Hours me se delay select karein:"
            ),
            reply_markup=delay_keyboard,
        )

    elif data.startswith("delsel_"):
        parts = data.split("_")
        rq_count = int(parts[1])
        delay_sec = float(parts[2])

        if delay_sec >= 3600:
            delay_str = f"{int(delay_sec / 3600)} Hour(s)"
        elif delay_sec >= 60:
            delay_str = f"{int(delay_sec / 60)} Min(s)"
        else:
            delay_str = f"{int(delay_sec)} Sec(s)"

        USER_STATES[user_id] = {
            "type": "WAITING_FOR_JOIN_LINK",
            "rq_count": rq_count,
            "delay_sec": delay_sec,
            "delay_str": delay_str,
        }
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                f"✅ <b>Request Setting Saved!</b>\n"
                f"• Total Rq: <code>{rq_count}</code>\n"
                f"• Per Member Delay: <code>{delay_str}</code>\n\n"
                "🚀 <b>Send Link:</b>\n"
                "Public link (<code>https://t.me/name</code>) ya Private Invite Link"
                " (<code>https://t.me/+xxx</code>) send karein:"
            ),
            reply_markup=get_back_button(),
        )

    elif data == "vc_joiner":
        if not USERBOT_SESSIONS:
            await callback_query.answer(
                "Koi active account nahi hai!", show_alert=True
            )
            return
        USER_STATES[user_id] = "WAITING_FOR_VC_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                "<b>🎙 VC Joiner</b>\n\nJis Group me VC chal rahi hai uska Link ya"
                " Username send karein:"
            ),
            reply_markup=get_back_button(),
        )

    elif data == "vc_leave":
        await send_log_to_owner(client, callback_query.from_user, "Sabhi accounts ko VC se Leave karwaya.")
        
        if not CURRENT_VC_CHAT and ACTIVE_VC_COUNT == 0:
            await callback_query.answer(
                "Koi bhi active VC session nahi mila!", show_alert=True
            )
            return

        await callback_query.answer(
            "VC se disconnect ho rahe hain...", show_alert=True
        )
        left_total = await leave_vc_all()
        await callback_query.edit_message_text(
            text=(
                "🔴 <b>VC LEAVE COMPLETE</b>\n\nSuccessfully"
                f" <b>{left_total}</b> accounts VC se leave kar chuke hain."
            ),
            reply_markup=get_back_button(),
        )

    elif data == "leave_all_channel":
        if user_id != OWNER_ID:
            await callback_query.answer(
                "⛔ Sirf Main Owner hi sabhi channels leave karwa sakta hai!",
                show_alert=True,
            )
            return

        if not USERBOT_SESSIONS:
            await callback_query.answer(
                "Koi active account nahi hai!", show_alert=True
            )
            return

        await callback_query.answer(
            "Mass channel cleanup start ho raha hai...", show_alert=True
        )
        await callback_query.edit_message_text(
            "⏳ **Cleaning Process Active:** Sabhi accounts se channels/groups"
            " leave kiye ja rahe hain..."
        )

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
            reply_markup=get_back_button(),
        )

    elif data == "purge_dead":
        await send_log_to_owner(client, callback_query.from_user, "Dead accounts ko Purge (Delete) kiya.")
        
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
            text=(
                f"<b>🔔 Purge Complete</b>\n\n{dead_count} dead accounts MongoDB"
                " aur Bot se remove kar diye gaye."
            ),
            reply_markup=get_back_button(),
        )

    elif data == "react_views":
        if not USERBOT_SESSIONS:
            await callback_query.answer(
                "Pehle account add karein!", show_alert=True
            )
            return
        USER_STATES[user_id] = "WAITING_FOR_POST_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                "<b>❤️ React + Views</b>\n\nTelegram Post ka Link send karein"
                " (<code>https://t.me/channel/123</code> ya"
                " <code>https://t.me/c/123456/789</code>):"
            ),
            reply_markup=get_back_button(),
        )

    elif data == "views_toggle":
        AUTO_VIEWS_ENABLED = not AUTO_VIEWS_ENABLED
        status_msg = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
        
        await send_log_to_owner(client, callback_query.from_user, f"Auto-Views ko {status_msg} kiya.")
        
        await callback_query.answer(f"Auto-Views: {status_msg}", show_alert=True)
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    elif data == "recycle_accounts":
        if user_id != OWNER_ID:
            await callback_query.answer(
                "⛔ Sirf Main Owner hi accounts recycle kar sakta hai!",
                show_alert=True,
            )
            return

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
            reply_markup=get_back_button(),
        )

    elif data == "refresh":
        alive_accounts = 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            if ubot.is_connected:
                alive_accounts += 1

        if not CURRENT_VC_CHAT:
            ACTIVE_VC_COUNT = 0

        await callback_query.answer("Panel Refreshed! 🔄")
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )

    elif data == "admin_panel":
        if user_id != OWNER_ID:
            await callback_query.answer(
                "⛔ Only Main Owner can manage Admin Panel!", show_alert=True
            )
            return
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                "<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nYahan se aap naye Admin add"
                " ya remove kar sakte hain:"
            ),
            reply_markup=get_admin_menu_keyboard(),
        )

    elif data == "prompt_add_admin":
        if user_id != OWNER_ID:
            return
        USER_STATES[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add New Admin</b>\n\nTelegram User ID send karein:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
            ]]),
        )

    elif data == "prompt_remove_admin":
        if user_id != OWNER_ID:
            return
        remove_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                remove_buttons.append([
                    InlineKeyboardButton(
                        f"❌ Remove: {aid}", callback_data=f"rem_adm_{aid}"
                    )
                ])

        if not remove_buttons:
            await callback_query.answer(
                "Koi extra Admin nahi hai!", show_alert=True
            )
            return

        remove_buttons.append(
            [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
        )
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=(
                "<b>➖ Remove Admin Panel</b>\n\nJis Admin ko hatana hai click"
                " karein:"
            ),
            reply_markup=InlineKeyboardMarkup(remove_buttons),
        )

    elif data.startswith("rem_adm_"):
        if user_id != OWNER_ID:
            return
        target_id = int(data.split("_")[2])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)
            await admins_col.delete_one({"user_id": target_id})
            await callback_query.answer(
                "Admin removed from MongoDB!", show_alert=True
            )
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nAdmin remove ho gaya.",
            reply_markup=get_admin_menu_keyboard(),
        )

    elif data == "list_admins":
        admin_text = "<b>📜 Current Admins List:</b>\n\n"
        for aid in ADMIN_IDS:
            role = " (Main Owner)" if aid == OWNER_ID else " (Admin)"
            admin_text += f"• <code>{aid}</code>{role}\n"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=admin_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back", callback_data="admin_panel")
            ]]),
        )

    elif data == "back_to_main":
        USER_STATES.pop(user_id, None)
        await callback_query.edit_message_text(
            text=get_panel_text(), reply_markup=get_main_keyboard(user_id)
        )


# -------------------- INPUT PROCESSING HANDLER --------------------


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
                "ubot_temp",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=text,
                in_memory=True,
            )
            await temp_client.start()
            me = await temp_client.get_me()
            USERBOT_SESSIONS[text] = temp_client

            await sessions_col.update_one(
                {"session": text},
                {"$set": {"session": text, "user_id": me.id}},
                upsert=True,
            )

            USER_STATES.pop(user_id, None)
            
            await send_log_to_owner(client, message.from_user, f"Naya account add kiya:\nName: {me.first_name}\nID: <code>{me.id}</code>")

            await message.reply_text(
                "✅ **Account Saved to MongoDB!**\n\n• Name:"
                f" {me.first_name}\n• ID: <code>{me.id}</code>",
                reply_markup=get_main_keyboard(user_id),
            )
        except Exception as e:
            await message.reply_text(
                f"❌ **Invalid Session String:**\n`{str(e)}`\n\nDobara sahi string"
                " session bhejein."
            )

    elif state_type == "WAITING_FOR_JOIN_LINK":
        rq_count = int(state.get("rq_count", 1))
        delay_sec = float(state.get("delay_sec", 1.0))
        delay_str = state.get("delay_str", f"{delay_sec} Sec")

        USER_STATES.pop(user_id, None)
        total_available = len(USERBOT_SESSIONS)

        if rq_count > total_available:
            await message.reply_text(
                f"❌ **Order Cancelled:**\n\n"
                f"Aapke paas sirf **{total_available}** active accounts hain!\n"
                f"Aapne **{rq_count} Rq** select kiya tha.\n\n"
                f"👉 Pehle aur accounts add karein ya kam Rq select karein.",
                reply_markup=get_main_keyboard(user_id),
            )
            return

        msg = await message.reply_text(
            f"⚡ **Custom Speed Join Active**\n"
            f"👥 Target Accounts: `{rq_count}` / `{total_available}`\n"
            f"⏱️ Delay Per Member: `{delay_str}`\n\n"
            f"Requests start ho rahi hain..."
        )
        
        await send_log_to_owner(client, message.from_user, f"🚀 Channel Join lagaya!\n🔗 Link: {text}\n🎯 Total Rq: {rq_count}\n⏳ Gap: {delay_str}")

        target_sessions = list(USERBOT_SESSIONS.items())[:rq_count]
        joined, failed, reasons = 0, 0, []

        for idx, (session_str, ubot) in enumerate(target_sessions, 1):
            ok, chat_obj, err_msg = await join_target_chat(ubot, text)
            if ok:
                joined += 1
            else:
                failed += 1
                reasons.append(err_msg)

            if idx < rq_count:
                await asyncio.sleep(delay_sec)

        detail_text = (
            f"✅ <b>Join Operation Complete</b>\n\n"
            f"• Total Rq Sent: <b>{rq_count}</b>\n"
            f"• Gap Used: <b>{delay_str}</b>\n"
            f"• Successful Joins: {joined}\n"
            f"• Failed: {failed}"
        )
        if reasons:
            detail_text += f"\n\n❌ <b>Error Detail:</b> {reasons[0]}"
        await msg.edit_text(detail_text)

    elif state_type == "WAITING_FOR_VC_LINK":
        global ACTIVE_VC_COUNT, CURRENT_VC_CHAT
        USER_STATES.pop(user_id, None)
        
        CURRENT_VC_CHAT = text
        
        await send_log_to_owner(client, message.from_user, f"🎙 VC Join ka order lagaya is group me:\n🔗 {text}")
        
        msg = await message.reply_text("⏳ Connecting Voice Chat 24/7...")
        connected, failed, vc_errors = 0, 0, []

        for session_str, ubot in USERBOT_SESSIONS.items():
            ok, err_msg = await join_vc_session(ubot, text)
            if ok:
                connected += 1
            else:
                failed += 1
                vc_errors.append(err_msg)

        ACTIVE_VC_COUNT = connected
        resp_text = (
            "🎙 <b>VC Join Status (24/7 Mode Active)</b>\n\n• Connected:"
            f" {connected}\n• Failed: {failed}"
        )
        if vc_errors:
            resp_text += f"\n\n⚠️ <b>Reason:</b> {vc_errors[0]}"
        await msg.edit_text(resp_text)

    elif state_type == "WAITING_FOR_POST_LINK":
        USER_STATES.pop(user_id, None)
        
        await send_log_to_owner(client, message.from_user, f"❤️ React + Views ka order lagaya is post par:\n🔗 {text}")
        
        try:
            parts = [p for p in text.split("/") if p]
            msg_id = int(parts[-1])

            if len(parts) >= 4 and parts[-3] == "c":
                channel = int(f"-100{parts[-2]}")
            else:
                channel = parts[-2]

            success = 0
            for session_str, ubot in USERBOT_SESSIONS.items():
                try:
                    await ubot.get_messages(channel, msg_id)
                    # Fixed pyrogram v2 reaction sending safely
                    await ubot.send_reaction(chat_id=channel, message_id=msg_id, emoji="❤️")
                    success += 1
                except Exception:
                    continue

            if success == 0:
                await message.reply_text(
                    "⚠️ **0 Reactions Sent!**\n\nPossible Reasons:\n1. Private channel"
                    " hai aur userbots abhi usme Joined NAHI hain.\n2. Post link/ID galat hai.",
                    reply_markup=get_main_keyboard(user_id),
                )
            else:
                await message.reply_text(
                    f"✅ Post par {success} Views + Reactions bhej diye gaye!",
                    reply_markup=get_main_keyboard(user_id),
                )

        except Exception as e:
            await message.reply_text(
                f"❌ Post Link Format galat hai!\nError: `{e}`",
                reply_markup=get_main_keyboard(user_id),
            )

    elif state_type == "WAITING_FOR_ADMIN_ID":
        if user_id == OWNER_ID and text.isdigit():
            new_id = int(text)
            ADMIN_IDS.add(new_id)
            await admins_col.update_one(
                {"user_id": new_id}, {"$set": {"user_id": new_id}}, upsert=True
            )

            USER_STATES.pop(user_id, None)
            await message.reply_text(
                f"✅ User ID <code>{new_id}</code> MongoDB me Admin save ho gaya.",
                reply_markup=get_admin_menu_keyboard(),
            )
        else:
            await message.reply_text("❌ Sahi numeric Telegram User ID bhejein.")


# -------------------- BOT RUNNER WITH DB LOADER --------------------


async def main():
    await app.start()
    await load_data_from_db()
    asyncio.create_task(vc_keepalive_loop())
    print("Sarkar_x_Nox_Bot is fully Started✅")
    await asyncio.Event().wait()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
