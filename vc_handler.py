import json
import asyncio
import random
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall, GetGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.types import DataJSON, InputGroupCall
from pyrogram.errors import RPCError

from vc_utils import resolve_chat_entity

# 24/7 Memory Reference (Saves clients from background deletion)
ACTIVE_VC_SESSIONS = {}

async def vc_maintainer_loop(acc, chat_input, input_call):
    """
    24/7 Maintainer Loop:
    Har 15 sec me connection check karega. Agar account disconnect hota hai ya kick hota hai,
    to jab tak VC ON hai, ye wapas AUTO-REJOIN kara dega.
    """
    while True:
        try:
            await asyncio.sleep(15)
            
            # 1. Connection alive check
            if not acc.is_connected:
                await acc.connect()

            # 2. VC Active Ping
            await acc.invoke(GetGroupCall(call=input_call, limit=1))

        except asyncio.CancelledError:
            break
        except Exception as e:
            # Agar disconnection hua, to auto-rejoin try karega
            print(f"VC connection re-establishing... ({e})")
            try:
                chat = await resolve_chat_entity(acc, chat_input)
                if chat:
                    peer = await acc.resolve_peer(chat.id)
                    full_chat = await acc.invoke(GetFullChannel(channel=peer))
                    call_info = getattr(full_chat.full_chat, "call", None)
                    
                    if call_info:
                        new_call = InputGroupCall(id=call_info.id, access_hash=call_info.access_hash)
                        self_peer = await acc.resolve_peer("me")
                        webrtc_params = DataJSON(data=json.dumps({
                            "ssrc": random.randint(1000000, 9999999),
                            "muted": True,
                            "video_stopped": True,
                            "screencast_stopped": True
                        }))
                        await acc.invoke(JoinGroupCall(call=new_call, join_as=self_peer, params=webrtc_params, muted=True))
                        input_call = new_call
            except Exception:
                pass


async def join_vc(chat_input, sessions, api_id, api_hash):
    global ACTIVE_VC_SESSIONS
    success = 0
    failed = 0
    
    # Purane active session clean karein
    await leave_all_vcs()

    for idx, session in enumerate(sessions):
        acc = None
        try:
            acc = Client(f"vc_acc_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            # Chat resolve
            chat = await resolve_chat_entity(acc, chat_input)
            if not chat:
                await acc.disconnect()
                failed += 1
                continue

            peer = await acc.resolve_peer(chat.id)
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            call_info = getattr(full_chat.full_chat, "call", None)

            # Linked Group support for Channels
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
            random_ssrc = random.randint(1000000, 9999999)
            
            webrtc_params = DataJSON(data=json.dumps({
                "ssrc": random_ssrc,
                "muted": True,
                "video_stopped": True,
                "screencast_stopped": True
            }))

            # Initial Join
            await acc.invoke(JoinGroupCall(call=input_call, join_as=self_peer, params=webrtc_params, muted=True))

            # Start 24/7 Auto-Rejoin Loop
            task = asyncio.create_task(vc_maintainer_loop(acc, chat_input, input_call))
            
            # Save session in permanent memory dictionary
            ACTIVE_VC_SESSIONS[idx] = {
                "client": acc,
                "task": task
            }

            success += 1
            await asyncio.sleep(1)

        except Exception as e:
            print(f"Join Error (ID {idx}): {e}")
            if acc:
                try: await acc.disconnect()
                except: pass
            failed += 1

    return success, failed


async def leave_all_vcs():
    global ACTIVE_VC_SESSIONS
    count = 0
    for idx, data in list(ACTIVE_VC_SESSIONS.items()):
        try:
            data["task"].cancel()
            await data["client"].disconnect()
            count += 1
        except Exception:
            pass
    ACTIVE_VC_SESSIONS.clear()
    return count
