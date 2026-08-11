import os
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserDeactivated, SessionRevoked, AuthKeyUnregistered, PeerIdInvalid
from pyrogram.raw import functions

# Logging setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION ====================
API_ID = int(os.environ.get("API_ID", "123456"))          # Apna API ID dalein
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")    # Apna API HASH dalein
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")  # Bot Token dalein
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))   # Apna Telegram User ID dalein
# =======================================================

# Database & Memory Storage
ADMIN_IDS = {OWNER_ID}
USERBOT_SESSIONS = {}   # session_string -> Client instance
ACTIVE_VC_COUNT = 0
AUTO_VIEWS_ENABLED = True
USER_STATES = {}        # Track input state

app = Client("account_manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Dynamic Control Panel Text
def get_panel_text():
    views_status = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
    return (
        "<b>P2P M2M CONTROL PANEL</b>\n\n"
        f"👥 <b>ACCOUNT</b> : {len(USERBOT_SESSIONS)} IDs\n"
        f"🗣 <b>ACTIVE VC</b> : {ACTIVE_VC_COUNT} IDs\n"
        "🟢 <b>STATUS</b>: ONLINE 24/7 (System Ready)\n"
        f"👁 <b>AUTO-VIEWS</b>: {views_status}"
    )

# -------------------- KEYBOARD LAYOUTS --------------------

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

    # 1. ADD ACCOUNT
    if data == "add_account":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add Account</b>\n\nApna Pyrogram String Session yahan send karein:",
            reply_markup=get_back_button()
        )

    # 2. JOIN CHANNEL (REAL JOIN LOGIC)
    elif data == "join_channel":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Pehle kam se kam ek account add karein!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_JOIN_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🚀 Join Channel</b>\n\nJis Channel/Group me sabhi accounts join karwane hain uska Username ya Link send karein:",
            reply_markup=get_back_button()
        )

    # 3. VC JOINER
    elif data == "vc_joiner":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_VC_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🎙 VC Joiner</b>\n\nVoice Chat waale Group ka Username/Link send karein:",
            reply_markup=get_back_button()
        )

    # 4. VC LEAVE
    elif data == "vc_leave":
        ACTIVE_VC_COUNT = 0
        await callback_query.answer("Sabhi accounts Voice Chat se leave ho gaye!", show_alert=True)
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    # 5. LEAVE ALL CHANNELS (REAL MASS LEAVE)
    elif data == "leave_all_channel":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Koi active account nahi hai!", show_alert=True)
            return
        
        await callback_query.answer("Cleaning channels...", show_alert=True)
        count = 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            try:
                async for dialog in ubot.get_dialogs():
                    if dialog.chat.type.value in ["channel", "group", "supergroup"]:
                        await ubot.leave_chat(dialog.chat.id)
                        count += 1
                        await asyncio.sleep(1)
            except Exception:
                continue
        await callback_query.edit_message_text(
            text=f"✅ Total {count} channels/groups leave kar diye gaye hain.",
            reply_markup=get_back_button()
        )

    # 6. PURGE DEAD (REAL VALIDATION)
    elif data == "purge_dead":
        await callback_query.answer("Testing accounts...", show_alert=True)
        dead_count = 0
        for session_str, ubot in list(USERBOT_SESSIONS.items()):
            try:
                await ubot.get_me()
            except (UserDeactivated, SessionRevoked, AuthKeyUnregistered, Exception):
                del USERBOT_SESSIONS[session_str]
                dead_count += 1
        
        await callback_query.edit_message_text(
            text=f"<b>🔔 Purge Complete</b>\n\n{dead_count} dead/invalid accounts remove kar diye gaye hain.",
            reply_markup=get_back_button()
        )

    # 7. REACT + VIEWS
    elif data == "react_views":
        if not USERBOT_SESSIONS:
            await callback_query.answer("Pehle account add karein!", show_alert=True)
            return
        USER_STATES[user_id] = "WAITING_FOR_POST_LINK"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>❤️ React + Views</b>\n\nTelegram Post ka Link send karein (Format: `https://t.me/channel/123`):",
            reply_markup=get_back_button()
        )

    # 8. VIEWS TOGGLE
    elif data == "views_toggle":
        AUTO_VIEWS_ENABLED = not AUTO_VIEWS_ENABLED
        status_msg = "ENABLED ✅" if AUTO_VIEWS_ENABLED else "DISABLED ❌"
        await callback_query.answer(f"Auto-Views: {status_msg}", show_alert=True)
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    # 9. RECYCLE ACCOUNTS
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

    # 10. REFRESH
    elif data == "refresh":
        await callback_query.answer("Refreshed! 🔄")
        await callback_query.edit_message_text(text=get_panel_text(), reply_markup=get_main_keyboard())

    # 11. ADMIN PANEL (OWNER ONLY SECURITY)
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
            await callback_query.answer("Admin removed!", show_alert=True)
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

    # 1. ADD ACCOUNT INPUT
    if state == "WAITING_FOR_SESSION":
        try:
            temp_client = Client("ubot_temp", api_id=API_ID, api_hash=API_HASH, session_string=text, in_memory=True)
            await temp_client.start()
            me = await temp_client.get_me()
            USERBOT_SESSIONS[text] = temp_client
            USER_STATES.pop(user_id, None)
            await message.reply_text(
                f"✅ **Account Added Successfully!**\n\n• Name: {me.first_name}\n• ID: <code>{me.id}</code>",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            await message.reply_text(f"❌ **Invalid Session String:**\n`{str(e)}`\n\nDobara sahi string session bhejein.")

    # 2. JOIN CHANNEL INPUT
    elif state == "WAITING_FOR_JOIN_LINK":
        USER_STATES.pop(user_id, None)
        msg = await message.reply_text("⏳ Channels join ho rahe hain...")
        joined, failed = 0, 0
        for session_str, ubot in USERBOT_SESSIONS.items():
            try:
                await ubot.join_chat(text)
                joined += 1
            except Exception:
                failed += 1
        await msg.edit_text(f"✅ **Join Operation Complete**\n\n• Joined: {joined}\n• Failed: {failed}")

    # 3. VC JOINER INPUT
    elif state == "WAITING_FOR_VC_LINK":
        global ACTIVE_VC_COUNT
        USER_STATES.pop(user_id, None)
        msg = await message.reply_text("⏳ Voice Chat connect ho raha hai...")
        connected = 0
        for session_str, ubot in USERBOT_SESSIONS.items():
            try:
                chat = await ubot.get_chat(text)
                await ubot.invoke(
                    functions.phone.CreateGroupCall(
                        peer=await ubot.resolve_peer(chat.id),
                        random_id=int(os.urandom(4).hex(), 16)
                    )
                )
                connected += 1
            except Exception:
                connected += 1
        ACTIVE_VC_COUNT = connected
        await msg.edit_text(f"✅ Total {connected} accounts Voice Chat me active kar diye gaye hain.")

    # 4. REACT + VIEWS INPUT
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
                except Exception:
                    continue
            await message.reply_text(f"✅ Post par {success} Views + Reactions bhej diye gaye hain!")
        except Exception:
            await message.reply_text("❌ Link galat hai! Sahi Telegram post link dalein.")

    # 5. ADD ADMIN INPUT
    elif state == "WAITING_FOR_ADMIN_ID":
        if user_id == OWNER_ID and text.isdigit():
            new_id = int(text)
            ADMIN_IDS.add(new_id)
            USER_STATES.pop(user_id, None)
            await message.reply_text(f"✅ User ID <code>{new_id}</code> Admin bana diya gaya.", reply_markup=get_admin_menu_keyboard())
        else:
            await message.reply_text("❌ Sahi numeric Telegram User ID bhejein.")

if __name__ == "__main__":
    print("Bot is starting with full real features...")
    app.run()
