import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

import config
from keep_alive import keep_alive
from vc_handler import join_vc, leave_all_vcs, get_active_count
from database import add_session, delete_all_sessions, get_sessions_count

keep_alive()

app = Client(
    "M2M_VC_Bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

START_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🚀 Join VC", callback_data="btn_join_vc"),
        InlineKeyboardButton("🛑 Leave VC", callback_data="btn_leave_vc")
    ],
    [
        InlineKeyboardButton("➕ Add Session", callback_data="btn_add_session"),
        InlineKeyboardButton("🗑 Clear Sessions", callback_data="btn_clear_sessions")
    ],
    [
        InlineKeyboardButton("📊 Status", callback_data="btn_status"),
        InlineKeyboardButton("ℹ️ Help", callback_data="btn_help")
    ]
])

CANCEL_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("❌ Cancel", callback_data="btn_cancel")]
])

USER_STATES = {}

def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    if not is_owner(message.from_user.id):
        await message.reply_text("❌ **Access Denied!**\n\nयह बोट केवल बोट ओनर के लिए है।")
        return

    text = (
        "👋 **Welcome Boss!**\n\n"
        "M2M VC Control Panel सक्रिय है। आप बोट के अंदर ही String Sessions जोड़ सकते हैं:"
    )
    await message.reply_text(text, reply_markup=START_BUTTONS)

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ सिर्फ बोट ओनर ही इन बटनों को इस्तेमाल कर सकता है!", show_alert=True)
        return

    data = query.data

    if data == "btn_join_vc":
        USER_STATES[user_id] = "WAITING_FOR_LINK"
        await query.message.edit_text(
            "🔗 **कृपया उस ग्रुप/चैनल का लिंक या यूजरनेम भेजें जहाँ VC जॉइन कराना है:**",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_add_session":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await query.message.edit_text(
            "🔑 **कृपया अपना Pyrogram v2 String Session यहाँ भेजें:**",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_clear_sessions":
        deleted = await delete_all_sessions()
        await leave_all_vcs()
        await query.answer("All Sessions Removed!", show_alert=True)
        await query.message.edit_text(f"🗑 **सफलतापूर्वक {deleted} सेशंस हटा दिए गए हैं।**", reply_markup=START_BUTTONS)

    elif data == "btn_leave_vc":
        await query.answer("Leaving VCs...", show_alert=False)
        msg = await query.message.edit_text("⏳ **VC से लीव कराया जा रहा है...**")
        count = await leave_all_vcs()
        await msg.edit_text(f"✅ **कुल {count} अकाउंट्स VC से लीव हो चुके हैं।**", reply_markup=START_BUTTONS)

    elif data == "btn_status":
        active = get_active_count()
        total_sessions = await get_sessions_count()
        status_text = (
            "📊 **M2M VC Bot Status:**\n\n"
            f"📁 **Total Saved Sessions:** `{total_sessions}`\n"
            f"🟢 **Active VC Connections:** `{active}`\n"
            f"👑 **Owner ID:** `{config.OWNER_ID}`\n"
            f"⚡ **System:** 24/7 Online"
        )
        await query.answer()
        await query.message.edit_text(status_text, reply_markup=START_BUTTONS)

    elif data == "btn_help":
        help_text = (
            "ℹ️ **How to use:**\n\n"
            "1. **➕ Add Session:** यहाँ बटन दबाकर अपने Userbot का Pyrogram String Session भेजें।\n"
            "2. **🚀 Join VC:** VC लिंक डालकर सेव किए गए अकाउंट्स को जॉइन कराएं।\n"
            "3. **🗑 Clear Sessions:** सभी सेव्ड सेशंस डिलीट करें।"
        )
        await query.answer()
        await query.message.edit_text(help_text, reply_markup=START_BUTTONS)

    elif data == "btn_cancel":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        await query.message.edit_text("❌ प्रक्रिया रद्द कर दी गई।", reply_markup=START_BUTTONS)

@app.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_inputs(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        return

    state = USER_STATES.get(user_id)

    if state == "WAITING_FOR_SESSION":
        del USER_STATES[user_id]
        session_str = message.text.strip()
        added = await add_session(session_str)
        if added:
            total = await get_sessions_count()
            await message.reply_text(f"✅ **String Session सफलतापूर्वक सेव हो गया!**\n\nकुल सेव्ड सेशंस: `{total}`", reply_markup=START_BUTTONS)
        else:
            await message.reply_text("⚠️ **यह Session पहले से सेव है!**", reply_markup=START_BUTTONS)

    elif state == "WAITING_FOR_LINK":
        del USER_STATES[user_id]
        chat_link = message.text.strip()
        status_msg = await message.reply_text("🔄 **VC से कनेक्ट हो रहा है, कृपया प्रतीक्षा करें...**")
        
        success, failed, status = await join_vc(chat_link, config.API_ID, config.API_HASH)
        
        if status == "No Sessions Found":
            await status_msg.edit_text("❌ **कोई Session नहीं मिला!** पहले `➕ Add Session` बटन दबाकर Session जोड़ें।", reply_markup=START_BUTTONS)
            return

        result_text = (
            "🎯 **VC Join Result:**\n\n"
            f"✅ **Successfully Joined:** `{success}`\n"
            f"❌ **Failed:** `{failed}`"
        )
        await status_msg.edit_text(result_text, reply_markup=START_BUTTONS)

if __name__ == "__main__":
    print("M2M VC Bot Started!")
    app.run()
