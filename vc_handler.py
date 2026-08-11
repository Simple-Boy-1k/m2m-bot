import json
import asyncio
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import CheckChatInvite, ImportChatInvite
from pyrogram.raw.types import DataJSON, ChatInviteAlready, ChatInvite
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
            
            chat_id = None
            
            # 🔥 1. THE ULTIMATE INVITE LINK RESOLVER (+ wale links ke liye)
            if "+" in clean_input or "joinchat" in clean_input:
                if "+" in clean_input:
                    hash_str = clean_input.split("+")[-1].split("/")[0]
                else:
                    hash_str = clean_input.split("joinchat/")[-1].split("/")[0]
                
                try:
                    # Raw API - Bypass UserAlreadyParticipant Error
                    invite_info = await acc.invoke(CheckChatInvite(hash=hash_str))
                    if isinstance(invite_info, ChatInviteAlready):
                        chat_id = invite_info.chat.id  # Agar pehle se joined hai
                    elif getattr(invite_info, "chat", None):
                        res = await acc.invoke(ImportChatInvite(hash=hash_str))
                        chat_id = res.chats[0].id      # Agar naya join kar raha hai
                except Exception as e:
                    print(f"Invite Link Resolve Error: {e}")
                    # Fallback
                    try:
                        chat_obj = await acc.join_chat(clean_input)
                        chat_id = chat_obj.id
                    except UserAlreadyParticipant:
                        pass
            
            # 2. Public Username ya Numeric ID ke liye
            else:
                if clean_input.lstrip("-").isdigit():
                    chat_id = int(clean_input)
                else:
                    target = clean_input.replace("https://t.me/", "").replace("t.me/", "").replace("@", "")
                    try:
                        chat_obj = await acc.join_chat(target)
                        chat_id = chat_obj.id
                    except UserAlreadyParticipant:
                        chat_obj = await acc.get_chat(target)
                        chat_id = chat_obj.id
                    except Exception:
                        chat_id = target

            # Agar chat_id nahi mili to skip
            if not chat_id:
                print(f"ID {idx}: Chat ID resolve nahi ho payi!")
                await acc.disconnect()
                failed += 1
                continue

            # Integer format check
            if str(chat_id).startswith("-100"):
                chat_id = int(chat_id)

            # 3. Resolve Peer
            peer = await acc.resolve_peer(chat_id)
            
            # 4. Check for Linked Discussion Group (Agar Channel ka link hai)
            try:
                full_chat = await acc.invoke(GetFullChannel(channel=peer))
                if hasattr(full_chat.full_chat, "linked_chat_id") and full_chat.full_chat.linked_chat_id:
                    peer = await acc.resolve_peer(full_chat.full_chat.linked_chat_id)
                    full_chat = await acc.invoke(GetFullChannel(channel=peer))
            except Exception:
                pass 

            # 5. Check VC is Active or Not
            call_info = getattr(full_chat.full_chat, "call", None)
            if not call_info:
                print(f"ID {idx}: Group me VC chalu nahi hai!")
                await acc.disconnect()
                failed += 1
                continue

            # 6. Join Voice Chat (Muted)
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
