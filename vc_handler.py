import asyncio
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.errors import UserAlreadyParticipant

active_vc_clients = []

async def join_vc(chat_id, sessions, api_id, api_hash):
    global active_vc_clients
    success = 0
    failed = 0
    
    # 1. URL Link Cleaning
    # अगर पब्लिक लिंक है (t.me/username), तो उसमें से सिर्फ username निकालेंगे
    target_chat = str(chat_id).strip()
    if target_chat.startswith("http") and "+" not in target_chat and "joinchat" not in target_chat:
        target_chat = target_chat.split("/")[-1]

    for idx, session in enumerate(sessions):
        try:
            acc = Client(f"vc_acc_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            real_chat_id = target_chat
            
            # 2. ग्रुप जॉइन करने की कोशिश (इससे प्राइवेट लिंक की असली ID मिल जाएगी)
            try:
                chat_info = await acc.join_chat(chat_id)
                real_chat_id = chat_info.id # यहाँ से असली Numeric ID मिल गई!
            except UserAlreadyParticipant:
                pass # अगर पहले से जॉइन है, तो कोई बात नहीं
            except Exception:
                pass

            # 3. अगर अकाउंट पहले से ग्रुप में है और लिंक '+' वाला है, तो टेलीग्राम उसे पहचान नहीं सकता
            if isinstance(real_chat_id, str) and ("+" in real_chat_id or "joinchat" in real_chat_id):
                print(f"ID {idx}: प्राइवेट लिंक से Peer Resolve नहीं हो सकता क्यूंकि अकाउंट पहले से जॉइन है।")
                raise Exception("Private Link Resolve Failed")

            # 4. Peer Resolve और VC Join
            peer = await acc.resolve_peer(real_chat_id)
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            
            if getattr(full_chat.full_chat, "call", None):
                await acc.invoke(JoinGroupCall(
                    call=full_chat.full_chat.call,
                    join_as=peer,
                    muted=True
                ))
                active_vc_clients.append(acc) # अकाउंट VC में रहेगा
                success += 1
            else:
                await acc.disconnect()
                failed += 1
                
        except Exception as e:
            print(f"VC Join Error (ID {idx}): {e}")
            try:
                await acc.disconnect()
            except:
                pass
            failed += 1
            
    return success, failed

async def leave_all_vcs():
    global active_vc_clients
    count = 0
    for acc in active_vc_clients:
        try:
            await acc.disconnect()
            count += 1
        except Exception:
            pass
    active_vc_clients.clear()
    return count
