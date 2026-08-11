import json
import asyncio
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.types import DataJSON
from pyrogram.errors import UserAlreadyParticipant

active_vc_clients = []

async def join_vc(chat_input, sessions, api_id, api_hash):
    global active_vc_clients
    success = 0
    failed = 0
    
    clean_input = str(chat_input).strip()

    for idx, session in enumerate(sessions):
        acc = None
        try:
            acc = Client(f"vc_acc_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            # 1. Join Chat (Channel/Group)
            try:
                chat_obj = await acc.join_chat(clean_input)
                chat_id = chat_obj.id
            except UserAlreadyParticipant:
                # Agar pehle se join hai, to entity get karo
                chat_obj = await acc.get_chat(clean_input)
                chat_id = chat_obj.id
            except Exception:
                chat_id = clean_input

            # 2. Resolve Peer
            peer = await acc.resolve_peer(chat_id)
            
            # 3. Check for Linked Discussion Group (Agar Channel hai to)
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            
            # Agar linked_chat_id hai, to group pe shift ho jao
            if hasattr(full_chat.full_chat, "linked_chat_id") and full_chat.full_chat.linked_chat_id:
                peer = await acc.resolve_peer(full_chat.full_chat.linked_chat_id)
                full_chat = await acc.invoke(GetFullChannel(channel=peer))

            # 4. Check for VC Call
            call_info = getattr(full_chat.full_chat, "call", None)
            if not call_info:
                print(f"ID {idx}: VC Start nahi hai!")
                await acc.disconnect()
                failed += 1
                continue

            # 5. Join Voice Chat
            self_peer = await acc.resolve_peer("me")
            webrtc_params = DataJSON(data=json.dumps({"muted": True, "video_stopped": True, "screencast_stopped": True}))

            await acc.invoke(JoinGroupCall(
                call=call_info,
                join_as=self_peer,
                params=webrtc_params,
                muted=True
            ))

            active_vc_clients.append(acc)
            success += 1

        except Exception as e:
            print(f"VC Join Error (ID {idx}): {e}")
            if acc:
                try: await acc.disconnect()
                except: pass
            failed += 1

    return success, failed

async def leave_all_vcs():
    global active_vc_clients
    count = 0
    for acc in active_vc_clients:
        try: await acc.disconnect()
        except: pass
    active_vc_clients.clear()
    return count
