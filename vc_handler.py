import json
import asyncio
import random
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall, GetGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.types import DataJSON, InputGroupCall
from vc_utils import resolve_chat_entity
from database import get_all_sessions, delete_session

ACTIVE_SESSIONS = {}

async def vc_keep_alive(acc: Client, input_call: InputGroupCall):
    while True:
        try:
            await asyncio.sleep(15)
            await acc.invoke(GetGroupCall(call=input_call, limit=1))
        except asyncio.CancelledError:
            break
        except Exception:
            break

async def join_vc(chat_input, api_id, api_hash):
    global ACTIVE_SESSIONS
    success = 0
    failed = 0
    
    await leave_all_vcs()
    sessions = await get_all_sessions()

    if not sessions:
        return 0, 0, "No Sessions Found"

    for idx, session in enumerate(sessions):
        if not session or session.strip() == "":
            continue
        
        acc = None
        try:
            acc = Client(
                f"vc_acc_{idx}_{random.randint(100, 999)}",
                api_id=api_id,
                api_hash=api_hash,
                session_string=session.strip(),
                in_memory=True
            )
            await acc.connect()
            
            chat = await resolve_chat_entity(acc, chat_input)
            if not chat:
                await acc.disconnect()
                failed += 1
                continue

            peer = await acc.resolve_peer(chat.id)
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            call_info = getattr(full_chat.full_chat, "call", None)

            if not call_info and getattr(full_chat.full_chat, "linked_chat_id", None):
                linked_peer = await acc.resolve_peer(full_chat.full_chat.linked_chat_id)
                full_chat = await acc.invoke(GetFullChannel(channel=linked_peer))
                call_info = getattr(full_chat.full_chat, "call", None)

            if not call_info:
                await acc.disconnect()
                failed += 1
                continue

            input_call = InputGroupCall(id=call_info.id, access_hash=call_info.access_hash)
            self_peer = await acc.resolve_peer("me")
            
            webrtc_params = DataJSON(data=json.dumps({
                "ssrc": random.randint(1000000, 9999999),
                "muted": True,
                "video_stopped": True,
                "screencast_stopped": True
            }))

            await acc.invoke(JoinGroupCall(call=input_call, join_as=self_peer, params=webrtc_params, muted=True))

            task = asyncio.create_task(vc_keep_alive(acc, input_call))
            
            ACTIVE_SESSIONS[idx] = {
                "client": acc,
                "task": task
            }

            success += 1

        except Exception as e:
            print(f"Join error (ID {idx}): {e}")
            if acc:
                try: await acc.disconnect()
                except: pass
            failed += 1

    return success, failed, "OK"

async def leave_all_vcs():
    global ACTIVE_SESSIONS
    count = 0
    for idx, item in list(ACTIVE_SESSIONS.items()):
        try:
            item["task"].cancel()
            await item["client"].disconnect()
            count += 1
        except Exception:
            pass
    ACTIVE_SESSIONS.clear()
    return count

def get_active_count():
    return len(ACTIVE_SESSIONS)

# 🚀 JOIN CHANNEL
async def join_channel_all(chat_input, api_id, api_hash):
    sessions = await get_all_sessions()
    success, failed = 0, 0
    for idx, session in enumerate(sessions):
        try:
            async with Client(f"ch_join_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True) as acc:
                await resolve_chat_entity(acc, chat_input)
                success += 1
        except Exception:
            failed += 1
    return success, failed

# 🚪 LEAVE ALL CHANNELS
async def leave_all_channels_all(api_id, api_hash):
    sessions = await get_all_sessions()
    success = 0
    for idx, session in enumerate(sessions):
        try:
            async with Client(f"ch_leave_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True) as acc:
                async for dialog in acc.get_dialogs():
                    if dialog.chat.type in ["channel", "group", "supergroup"]:
                        try:
                            await acc.leave_chat(dialog.chat.id)
                        except Exception:
                            pass
                success += 1
        except Exception:
            pass
    return success

# 🔔 PURGE DEAD
async def purge_dead_sessions(api_id, api_hash):
    sessions = await get_all_sessions()
    removed = 0
    for session in sessions:
        try:
            async with Client("purge_chk", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True) as acc:
                await acc.get_me()
        except Exception:
            await delete_session(session)
            removed += 1
    return removed

# ❤️ REACT + VIEWS
async def react_and_views_post(post_link, emoji, api_id, api_hash):
    sessions = await get_all_sessions()
    success = 0
    for idx, session in enumerate(sessions):
        try:
            async with Client(f"react_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True) as acc:
                parts = post_link.replace("https://t.me/", "").split("/")
                chat_username = parts[0]
                message_id = int(parts[1])
                await acc.send_reaction(chat_username, message_id, emoji)
                await acc.get_messages(chat_username, message_id)
                success += 1
        except Exception:
            pass
    return success
