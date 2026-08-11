import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Logging setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION (YAHAN APNI DETAILS DALEIN) ====================
API_ID = int(os.environ.get("API_ID", "123456"))          # Yahan apna API ID dalein
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")    # Yahan apna API HASH dalein
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")  # Yahan BotFather se mila BOT TOKEN dalein
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))   # Yahan apna Telegram User ID dalein
# ====================================================================================

# Admin IDs Set (Main Owner hamesha default rahega)
ADMIN_IDS = {OWNER_ID}

# Temporary User States (Input tracking ke liye)
user_states = {}

# Pyrogram Client Setup
app = Client("account_manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Control Panel Text (Exact Screenshot Style)
PANEL_TEXT = (
    "<b>P2P M2M CONTROL PANEL</b>\n\n"
    "👥 <b>ACCOUNT</b> : 3 IDs\n"
    "🗣 <b>ACTIVE VC</b> : 0 IDs\n"
    "🟢 <b>STATUS</b>: ONLINE 24/7 (MongoDB Secured)\n"
    "👁 <b>AUTO-VIEWS</b>: ENABLED ✅"
)

# -------------------- KEYBOARD LAYOUTS --------------------

def get_main_keyboard():
    # Screenshot ke exact buttons & layout
    buttons = [
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
    ]
    return InlineKeyboardMarkup(buttons)

def get_admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add New Admin", callback_data="prompt_add_admin")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data="prompt_remove_admin")],
        [InlineKeyboardButton("📜 Admin List", callback_data="list_admins")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]
    ])


# -------------------- COMMAND HANDLERS --------------------

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    
    # Access check: Only Owner & Admins
    if user_id not in ADMIN_IDS:
        await message.reply_text("⛔ **Access Denied:** Aapke paas is bot ka access nahi hai.")
        return

    await message.reply_text(
        text=PANEL_TEXT,
        reply_markup=get_main_keyboard()
    )


# -------------------- CALLBACK QUERY HANDLER --------------------

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Security check: User admin ya owner hona chahiye
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⛔ Access Denied!", show_alert=True)
        return

    data = callback_query.data

    # Screenshot Buttons Operations
    if data == "add_account":
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add Account Panel</b>\n\nApna session string ya login details send karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_to_main")]])
        )

    elif data == "join_channel":
        await callback_query.answer("Joining channels...", show_alert=True)

    elif data == "vc_joiner":
        await callback_query.answer("Connecting to VC...", show_alert=True)

    elif data == "vc_leave":
        await callback_query.answer("Leaving VC...", show_alert=True)

    elif data == "leave_all_channel":
        await callback_query.answer("Leaving all channels...", show_alert=True)

    elif data == "purge_dead":
        await callback_query.answer("Purging dead accounts...", show_alert=True)

    elif data == "react_views":
        await callback_query.answer("React + Views triggered!", show_alert=True)

    elif data == "views_toggle":
        await callback_query.answer("Views toggled!", show_alert=True)

    elif data == "recycle_accounts":
        await callback_query.answer("Recycling accounts...", show_alert=True)

    elif data == "refresh":
        await callback_query.answer("Refreshed! 🔄")
        await callback_query.edit_message_text(
            text=PANEL_TEXT,
            reply_markup=get_main_keyboard()
        )

    # 🔐 ADMIN PANEL (STRICTLY OWNER ONLY)
    elif data == "admin_panel":
        if user_id != OWNER_ID:  # Added Admins ko block karne ka logic
            await callback_query.answer("⛔ Sirf Main Owner hi Admin Panel use kar sakta hai!", show_alert=True)
            return
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nYahan se aap naye Admin add ya remove kar sakte hain:",
            reply_markup=get_admin_menu_keyboard()
        )

    elif data == "prompt_add_admin":
        if user_id != OWNER_ID:
            await callback_query.answer("Only Main Owner can add admins!", show_alert=True)
            return
        
        user_states[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add New Admin</b>\n\nJis user ko Admin banana hai uska <b>Telegram User ID</b> message karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]])
        )

    elif data == "prompt_remove_admin":
        if user_id != OWNER_ID:
            await callback_query.answer("Only Main Owner can remove admins!", show_alert=True)
            return

        # Owner ke alawa bakee saare admins ke remove buttons generate honge
        remove_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                remove_buttons.append([InlineKeyboardButton(f"❌ Remove: {aid}", callback_data=f"rem_adm_{aid}")])

        if not remove_buttons:
            await callback_query.answer("Koi extra Admin nahi hai jise remove kiya jaye!", show_alert=True)
            return

        remove_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➖ Remove Admin Panel</b>\n\nJis Specific Admin ko hatana hai us par click karein:",
            reply_markup=InlineKeyboardMarkup(remove_buttons)
        )

    elif data.startswith("rem_adm_"):
        if user_id != OWNER_ID:
            await callback_query.answer("Only Main Owner can remove admins!", show_alert=True)
            return
        
        target_id = int(data.split("_")[2])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)  # Sirf usi selected User ID ko remove karega
            await callback_query.answer(f"User {target_id} ko admin list se hata diya gaya!", show_alert=True)
        
        await callback_query.edit_message_text(
            text="<b>🔐 ADMIN PANEL MANAGEMENT</b>\n\nSelected Admin remove ho gaya hai.",
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
        user_states.pop(user_id, None)
        await callback_query.edit_message_text(
            text=PANEL_TEXT,
            reply_markup=get_main_keyboard()
        )


# -------------------- TEXT MESSAGE HANDLER --------------------

@app.on_message(filters.private & ~filters.command(["start"]))
async def message_handler(client, message):
    user_id = message.from_user.id
    
    if user_id == OWNER_ID and user_states.get(user_id) == "WAITING_FOR_ADMIN_ID":
        text = message.text.strip()
        
        if text.isdigit():
            new_admin_id = int(text)
            ADMIN_IDS.add(new_admin_id)
            user_states.pop(user_id, None)
            
            await message.reply_text(
                f"✅ **Success!** User ID <code>{new_admin_id}</code> ko Admin bana diya gaya hai.",
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await message.reply_text("❌ Kripya valid numeric Telegram User ID bhejein.")


# -------------------- BOT STARTUP --------------------

if __name__ == "__main__":
    print("Bot startup initialized...")
    app.run()
