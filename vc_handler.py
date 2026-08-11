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
            # 1. Start Pyrogram Client for ID
            acc = Client(f"vc_acc_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            # 2. High-Level API से Chat Fetch करो (ताकि Access Hash Memory में आ जाए)
            chat = None
            try:
                chat = await acc.join_chat(clean_input)
            except UserAlreadyParticipant:
                chat = await acc.get_chat(clean_input)
            except Exception:
                try:
                    chat = await acc.get_chat(clean_input)
                except Exception as e:
                    print(f"ID {idx} Chat Fetch Failed: {e}")

            if not chat:
                print(f"ID {idx}: Channel/Group Resolve nahi ho paya")
                await acc.disconnect()
                failed += 1
                continue

            # 3. Peer resolve karo (अब Access Hash होने के कारण एरर नहीं आएगा)
            peer = await acc.resolve_peer(chat.id)
            
            # 4. Channel / Group Call Info
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            call_info = getattr(full_chat.full_chat, "call", None)
            
            # अगर Channel से Linked Group है तो वहाँ स्विच करो
            if not call_info and hasattr(full_chat.full_chat, "linked_chat_id") and full_chat.full_chat.linked_chat_id:
                linked_peer = await acc.resolve_peer(full_chat.full_chat.linked_chat_id)
                full_chat = await acc.invoke(GetFullChannel(channel=linked_peer))
                call_info = getattr(full_chat.full_chat, "call", None)
                peer = linked_peer

            if not call_info:
                print(f"ID {idx}: Live Stream / VC Chalu nahi hai!")
                await acc.disconnect()
                failed += 1
                continue

            # 5. Join Live Stream / VC
            self_peer = await acc.resolve_peer("me")
            webrtc_params = DataJSON(
                data=json.dumps({
                    "muted": True,
                    "video_stopped": True,
                    "screencast_stopped": True
                })
            )

            await acc.invoke(
                JoinGroupCall(
                    call=call_info,
                    join_as=self_peer,
                    params=webrtc_params,
                    muted=True
                )
            )

            active_vc_clients.append(acc) # अकाउंट कनेक्टेड रहेगा
            success += 1

        except Exception as e:
            print(f"VC/LiveStream Join Error (ID {idx}): {e}")
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
