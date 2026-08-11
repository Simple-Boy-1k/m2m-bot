import os
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Logging configuration setup
logging.basicConfig(level=logging.INFO)

# ==================== CONFIGURATION (YAHAN APNI DETAILS DALEIN) ====================
API_ID = int(os.environ.get("API_ID", "123456"))          # Yahan apna API ID dalein
API_HASH = os.environ.get("API_HASH", "YOUR_API_HASH")    # Yahan apna API HASH dalein
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")  # Yahan BotFather se mila BOT TOKEN dalein
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))   # Yahan apna Telegram User ID dalein
# ====================================================================================

# Admin IDs Set (Owner hamesha by default rehga)
ADMIN_IDS = {OWNER_ID}

# Temporary User States (Admin ID receive karne ke liye)
user_states = {}

# Pyrogram Client Setup
app = Client("account_manager_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# -------------------- KEYBOARD LAYOUTS --------------------

def get_main_keyboard(user_id):
    buttons = [
        [InlineKeyboardButton("➕ Add Account", callback_data="add_account")],
        [InlineKeyboardButton("❌ Remove Account", callback_data="remove_account")]
    ]
    # Sirf Main Owner ko hi "👑 Manage Admins" wala button dikhega
    if user_id == OWNER_ID:
        buttons.append([InlineKeyboardButton("👑 Manage Admins", callback_data="manage_admins")])
    
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
    
    # Permission Check: Sirf Owner aur Admins access kar sakte hain
    if user_id not in ADMIN_IDS:
        await message.reply_text("⛔ **Access Denied:** Aapke paas is bot ka access nahi hai.")
        return

    await message.reply_text(
        text="<b>⚙️ Account Management Panel</b>\n\nNiche diye gaye options me se select karein:",
        reply_markup=get_main_keyboard(user_id)
    )


# -------------------- CALLBACK QUERY HANDLER --------------------

@app.on_callback_query()
async def callback_handler(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Security check: User admin hona chahiye
    if user_id not in ADMIN_IDS:
        await callback_query.answer("⛔ Access Denied!", show_alert=True)
        return

    data = callback_query.data

    # 1. Add Account
    if data == "add_account":
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add Account Panel</b>\n\nApna new session string ya login details enter karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]])
        )

    # 2. Remove Account
    elif data == "remove_account":
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>❌ Remove Account Panel</b>\n\nJo account remove karna hai uska ID select karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]])
        )

    # 3. Admin Management Menu (Owner Only)
    elif data == "manage_admins":
        if user_id != OWNER_ID:
            await callback_query.answer("Sirf Main Owner hi admins manage kar sakta hai!", show_alert=True)
            return
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>👑 Admin Management Panel</b>\n\nYahan se aap naye admin add ya kisi ko remove kar sakte hain:",
            reply_markup=get_admin_menu_keyboard()
        )

    # 4. Prompt Add Admin
    elif data == "prompt_add_admin":
        if user_id != OWNER_ID:
            await callback_query.answer("Only Owner can add admins!", show_alert=True)
            return
        
        user_states[user_id] = "WAITING_FOR_ADMIN_ID"
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➕ Add New Admin</b>\n\nJis user ko Admin banana hai uska <b>Telegram User ID</b> chat me message karein:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="manage_admins")]])
        )

    # 5. Prompt Remove Admin (Shows buttons for each admin)
    elif data == "prompt_remove_admin":
        if user_id != OWNER_ID:
            await callback_query.answer("Only Owner can remove admins!", show_alert=True)
            return

        # Sabhi admins ke individual removal buttons generate ho rahe hain
        remove_buttons = []
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:  # Owner khud ko remove nahi kar sakta
                remove_buttons.append([InlineKeyboardButton(f"❌ Remove: {aid}", callback_data=f"rem_adm_{aid}")])

        if not remove_buttons:
            await callback_query.answer("Koi extra Admin nahi hai jise remove kiya jaye!", show_alert=True)
            return

        remove_buttons.append([InlineKeyboardButton("🔙 Back", callback_data="manage_admins")])
        await callback_query.answer()
        await callback_query.edit_message_text(
            text="<b>➖ Remove Admin Panel</b>\n\nJis Specific Admin ko hatana hai us par click karein:",
            reply_markup=InlineKeyboardMarkup(remove_buttons)
        )

    # 6. Specific Admin Remove Logic
    elif data.startswith("rem_adm_"):
        if user_id != OWNER_ID:
            await callback_query.answer("Only Owner can remove admins!", show_alert=True)
            return
        
        target_id = int(data.split("_")[2])
        if target_id in ADMIN_IDS:
            ADMIN_IDS.remove(target_id)  # Sirf wahi targeted ID remove hogi
            await callback_query.answer(f"User {target_id} ko admin list se hata diya gaya hai!", show_alert=True)
        
        await callback_query.edit_message_text(
            text="<b>👑 Admin Management Panel</b>\n\nSelected admin successfully remove ho gaya hai.",
            reply_markup=get_admin_menu_keyboard()
        )

    # 7. List All Admins
    elif data == "list_admins":
        admin_text = "<b>📜 Current Admins List:</b>\n\n"
        for aid in ADMIN_IDS:
            role = " (Main Owner)" if aid == OWNER_ID else " (Admin)"
            admin_text += f"• <code>{aid}</code>{role}\n"
            
        await callback_query.answer()
        await callback_query.edit_message_text(
            text=admin_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="manage_admins")]])
        )

    # 8. Back To Main Menu
    elif data == "back_to_main":
        user_states.pop(user_id, None)
        await callback_query.edit_message_text(
            text="<b>⚙️ Account Management Panel</b>\n\nNiche diye gaye options me se select karein:",
            reply_markup=get_main_keyboard(user_id)
        )


# -------------------- TEXT MESSAGE HANDLER --------------------

@app.on_message(filters.private & ~filters.command(["start"]))
async def message_handler(client, message):
    user_id = message.from_user.id
    
    # Input capturing for adding Admin ID
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
            await message.reply_text("❌ Kripya sahi Telegram User ID (numbers) bhejein.")


# -------------------- BOT STARTUP --------------------

if __name__ == "__main__":
    print("Sarkar_Bot_Start...")
    app.run()
