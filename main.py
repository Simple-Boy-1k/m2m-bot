import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message

import config
from keep_alive import keep_alive
from vc_handler import (
    join_vc, leave_all_vcs, get_active_count, 
    join_channel_all, leave_all_channels_all, purge_dead_sessions, 
    recycle_accounts_all, react_and_views_post
)
from database import (
    add_session, delete_all_sessions, get_sessions_count, 
    get_auto_views, toggle_auto_views
)

keep_alive()

app = Client(
    "M2M_VC_Bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

MAIN_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("➕ ADD ACCOUNT", callback_data="btn_add_account"),
        InlineKeyboardButton("🚀 JOIN CHANNEL", callback_data="btn_join_channel")
    ],
    [
        InlineKeyboardButton("🎙 VC JOINER", callback_data="btn_vc_joiner"),
        InlineKeyboardButton("🔴 VC LEAVE", callback_data="btn_vc_leave")
    ],
    [
        InlineKeyboardButton("🚪 LEAVE ALL CHANNEL", callback_data="btn_leave_all_channel"),
        InlineKeyboardButton("🔔 PURGE DEAD", callback_data="btn_purge_dead")
    ],
    [
        InlineKeyboardButton("❤️ REACT + VIEWS", callback_data="btn_react_views"),
        InlineKeyboardButton("👁 VIEWS TOGGLE", callback_data="btn_views_toggle")
    ],
    [
        InlineKeyboardButton("♻️ RECYCLE ACCOUNTS", callback_data="btn_recycle_accounts"),
        InlineKeyboardButton("🔐 ADMIN PANEL", callback_data="btn_admin_panel")
    ],
    [
        InlineKeyboardButton("🔄 REFRESH", callback_data="btn_refresh")
    ]
])

CANCEL_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("❌ CANCEL", callback_data="btn_cancel")]
])

USER_STATES = {}

def is_owner(user_id: int) -> bool:
    return user_id == config.OWNER_ID

async def render_panel_text():
    acc_count = await get_sessions_count()
    active_vc = get_active_count()
    auto_views = await get_auto_views()
    av_status = "ENABLED ✅" if auto_views else "DISABLED ❌"

    return (
        "**P2P M2M CONTROL PANEL**\n\n"
        f"👥 **ACCOUNT** : `{acc_count}` IDs\n"
        f"🗣 **ACTIVE VC** : `{active_vc}` IDs\n"
        f"🟢 **STATUS**: ONLINE 24/7 (MongoDB Secured)\n"
        f"👁 **AUTO-VIEWS**: {av_status}"
    )

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client: Client, message: Message):
    if not is_owner(message.from_user.id):
        await message.reply_text("❌ **Access Denied!** Only Owner can control this bot.")
        return

    text = await render_panel_text()
    await message.reply_text(text, reply_markup=MAIN_KEYBOARD)

@app.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ Access Denied!", show_alert=True)
        return

    data = query.data

    if data == "btn_refresh":
        text = await render_panel_text()
        await query.message.edit_text(text, reply_markup=MAIN_KEYBOARD)
        await query.answer("Panel Refreshed! 🔄", show_alert=False)

    elif data == "btn_add_account":
        USER_STATES[user_id] = "WAITING_FOR_SESSION"
        await query.message.edit_text(
            "🔑 **कृपया अपना Pyrogram v2 String Session यहाँ भेजें:**",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_join_channel":
        USER_STATES[user_id] = "WAITING_FOR_CHANNEL"
        await query.message.edit_text(
            "🚀 **जिस चैनल/ग्रुप को जॉइन कराना है उसका लिंक या यूजरनेम भेजें:**",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_vc_joiner":
        USER_STATES[user_id] = "WAITING_FOR_VC"
        await query.message.edit_text(
            "🎙 **जिस ग्रुप/चैनल की VC में आईडी जोड़नी है उसका लिंक या यूजरनेम भेजें:**",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_vc_leave":
        await query.answer("Leaving VC...", show_alert=False)
        msg = await query.message.edit_text("⏳ **सभी सेशंस को VC से निकाला जा रहा है...**")
        count = await leave_all_vcs()
        text = await render_panel_text()
        await msg.edit_text(f"✅ **कुल {count} IDs VC से लीव हो चुकी हैं।**\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif data == "btn_leave_all_channel":
        await query.answer("Leaving All Channels...", show_alert=False)
        msg = await query.message.edit_text("⏳ **सभी सेशंस से चैनल्स/ग्रुप्स लीव किए जा रहे हैं...**")
        count = await leave_all_channels_all(config.API_ID, config.API_HASH)
        text = await render_panel_text()
        await msg.edit_text(f"✅ **{count} सेशंस से सारे चैनल्स लीव कर दिए गए हैं।**\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif data == "btn_purge_dead":
        await query.answer("Purging Dead Sessions...", show_alert=False)
        msg = await query.message.edit_text("⏳ **मृत/एक्सपायर्ड सेशंस चेक और डिलीट किए जा रहे हैं...**")
        removed = await purge_dead_sessions(config.API_ID, config.API_HASH)
        text = await render_panel_text()
        await msg.edit_text(f"🔔 **{removed} खराब सेशंस MongoDB से हटा दिए गए।**\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif data == "btn_recycle_accounts":
        await query.answer("Recycling Accounts...", show_alert=False)
        msg = await query.message.edit_text("⏳ **सभी एकाउंट्स रीसाइक्लिंग और री-वेरीफाई किए जा रहे हैं...**")
        recycled, dead = await recycle_accounts_all(config.API_ID, config.API_HASH)
        text = await render_panel_text()
        await msg.edit_text(
            f"♻️ **Recycle Completed!**\n"
            f"✅ Valid & Active: `{recycled}` IDs\n"
            f"❌ Removed Dead: `{dead}` IDs\n\n" + text,
            reply_markup=MAIN_KEYBOARD
        )

    elif data == "btn_react_views":
        USER_STATES[user_id] = "WAITING_FOR_REACT"
        await query.message.edit_text(
            "❤️ **पोस्ट लिंक और इमोजी भेजें (Format: `Link Emoji`):**\n\n"
            "_(उदाहरण: `https://t.me/channel/123 ❤️`)_",
            reply_markup=CANCEL_BUTTON
        )

    elif data == "btn_views_toggle":
        new_status = await toggle_auto_views()
        status_txt = "ENABLED ✅" if new_status else "DISABLED ❌"
        await query.answer(f"Auto-Views: {status_txt}", show_alert=True)
        text = await render_panel_text()
        await query.message.edit_text(text, reply_markup=MAIN_KEYBOARD)

    elif data == "btn_admin_panel":
        acc_count = await get_sessions_count()
        active_vc = get_active_count()
        admin_text = (
            "🔐 **ADMIN CONTROL PANEL**\n\n"
            f"👑 **Owner ID:** `{config.OWNER_ID}`\n"
            f"👥 **Total Accounts:** `{acc_count}`\n"
            f"🎙 **Active in VC:** `{active_vc}`\n"
            f"🌐 **Server:** Heroku Active 24/7\n"
            f"🗄 **Database:** MongoDB Connected\n\n"
            "सभी फीचर्स और बटन्स पूरी तरह सक्रिय हैं।"
        )
        await query.message.edit_text(admin_text, reply_markup=MAIN_KEYBOARD)

    elif data == "btn_cancel":
        if user_id in USER_STATES:
            del USER_STATES[user_id]
        text = await render_panel_text()
        await query.message.edit_text(text, reply_markup=MAIN_KEYBOARD)

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
        text = await render_panel_text()
        if added:
            await message.reply_text("✅ **String Session सफलतापूर्वक सेव हो गया!**\n\n" + text, reply_markup=MAIN_KEYBOARD)
        else:
            await message.reply_text("⚠️ **यह Session पहले से मौजूद है!**\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif state == "WAITING_FOR_CHANNEL":
        del USER_STATES[user_id]
        target = message.text.strip()
        status_msg = await message.reply_text("🔄 **चैनल जॉइन कराया जा रहा है...**")
        succ, fail = await join_channel_all(target, config.API_ID, config.API_HASH)
        text = await render_panel_text()
        await status_msg.edit_text(f"🚀 **Channel Join Done!**\n✅ Success: {succ}\n❌ Failed: {fail}\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif state == "WAITING_FOR_VC":
        del USER_STATES[user_id]
        target = message.text.strip()
        status_msg = await message.reply_text("🎙 **VC से कनेक्ट हो रहा है...**")
        succ, fail, status = await join_vc(target, config.API_ID, config.API_HASH)
        text = await render_panel_text()
        if status == "No Sessions Found":
            await status_msg.edit_text("❌ **कोई Session नहीं मिला!** पहले `➕ ADD ACCOUNT` से सेशन जोड़ें।", reply_markup=MAIN_KEYBOARD)
            return
        await status_msg.edit_text(f"🎙 **VC Join Completed!**\n👍 Success: {succ}\n👎 Failed: {fail}\n\n" + text, reply_markup=MAIN_KEYBOARD)

    elif state == "WAITING_FOR_REACT":
        del USER_STATES[user_id]
        parts = message.text.strip().split()
        if len(parts) < 2:
            await message.reply_text("❌ गलत फॉर्मेट! `Link Emoji` फॉर्मेट में भेजें।", reply_markup=MAIN_KEYBOARD)
            return
        link, emoji = parts[0], parts[1]
        status_msg = await message.reply_text("🔄 **Reactions और Views भेजे जा रहे हैं...**")
        count = await react_and_views_post(link, emoji, config.API_ID, config.API_HASH)
        text = await render_panel_text()
        await status_msg.edit_text(f"❤️ **{count} सेशंस से Reaction & View सफलतापूर्वक भेजे गए!**\n\n" + text, reply_markup=MAIN_KEYBOARD)

if __name__ == "__main__":
    print("P2M M2M Control Panel Starting...")
    app.run()
