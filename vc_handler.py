import json
import asyncio
import random
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall, GetGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.types import DataJSON, InputGroupCall
from pyrogram.errors import RPCError

from vc_utils import resolve_chat_entity

active_vc_clients = []
active_ping_tasks = []

async def vc_keep_alive(acc: Client, input_call: InputGroupCall):
    """हर 10 सेकंड में टेलीग्राम को सिग्नल भेजेगा ताकि अकाउंट VC से Auto-Leave न हो"""
    try:
        while True:
            await asyncio.sleep(10)
            try:
                await acc.invoke(GetGroupCall(call=input_call, limit=1))
            except RPCError:
                break
            except Exception:
                pass
    except asyncio.CancelledError:
        pass

async def join_vc(chat_input, sessions, api_id, api_hash):
    global active_vc_clients, active_ping_tasks
    success = 0
    failed = 0
    
    for idx, session in enumerate(sessions):
        acc = None
        try:
            acc = Client(f"vc_acc_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            # 1. Chat Entity Resolve
            chat = await resolve_chat_entity(acc, chat_input)
            if not chat:
                print(f"ID {idx}: Chat resolve nahi ho payi")
                await acc.disconnect()
                failed += 1
                continue

            # 2. Resolve Peer
            peer = await acc.resolve_peer(chat.id)
            
            # 3. Fetch Full Channel Info
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            call_info = getattr(full_chat.full_chat, "call", None)
            
            # 4. Check Linked Group if Channel
            if not call_info and getattr(full_chat.full_chat, "linked_chat_id", None):
                linked_peer = await acc.resolve_peer(full_chat.full_chat.linked_chat_id)
                full_chat = await acc.invoke(GetFullChannel(channel=linked_peer))
                call_info = getattr(full_chat.full_chat, "call", None)
                peer = linked_peer

            if not call_info:
                print(f"ID {idx}: Voice Chat / Live Stream Active Nahi Hai!")
                await acc.disconnect()
                failed += 1
                continue

            # 5. Construct InputGroupCall Object
            input_call = InputGroupCall(
                id=call_info.id,
                access_hash=call_info.access_hash
            )

            # 6. Generate Unique Random SSRC
            random_ssrc = random.randint(100000, 9999999)
            self_peer = await acc.resolve_peer("me")
            
            webrtc_params = DataJSON(
                data=json.dumps({
                    "ssrc": random_ssrc,
                    "muted": True,
                    "video_stopped": True,
                    "screencast_stopped": True
                })
            )

            # 7. Join Group Call / Live Stream
            await acc.invoke(
                JoinGroupCall(
                    call=input_call,
                    join_as=self_peer,
                    params=webrtc_params,
                    muted=True
                )
            )

            active_vc_clients.append(acc)

            # 8. Keep-Alive Task चालू करें
            task = asyncio.create_task(vc_keep_alive(acc, input_call))
            active_ping_tasks.append(task)

            success += 1
            await asyncio.sleep(1.5)

        except Exception as e:
            print(f"VC Join Error (ID {idx}): {e}")
            if acc:
                try:
                    await acc.disconnect()
                except Exception:
                    pass
            failed += 1

    return success, failed

async def leave_all_vcs():
    global active_vc_clients, active_ping_tasks
    count = 0

    # Ping Tasks बंद करें
    for task in active_ping_tasks:
        task.cancel()
    active_ping_tasks.clear()

    # Accounts Disconnect करें
    for acc in active_vc_clients:
        try:
            await acc.disconnect()
            count += 1
        except Exception:
            pass
    active_vc_clients.clear()
    return count
