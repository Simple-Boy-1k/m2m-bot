import asyncio
from pyrogram import Client
from pyrogram.raw.functions.phone import JoinGroupCall
from pyrogram.raw.functions.channels import GetFullChannel

# इन क्लाइंट्स को सेव रखेंगे ताकि ये VC से बाहर न निकलें
active_vc_clients = []

async def join_vc(chat_id, sessions, api_id, api_hash):
    global active_vc_clients
    success = 0
    failed = 0
    
    for idx, session in enumerate(sessions):
        try:
            # नया क्लाइंट बनाएँ
            acc = Client(f"vc_client_{idx}", api_id=api_id, api_hash=api_hash, session_string=session, in_memory=True)
            await acc.connect()
            
            # पहले चैट जॉइन करें (अगर पहले से नहीं है)
            try:
                await acc.join_chat(chat_id)
            except Exception:
                pass 
            
            # VC में घुसने का प्रोसेस
            peer = await acc.resolve_peer(chat_id)
            full_chat = await acc.invoke(GetFullChannel(channel=peer))
            
            if getattr(full_chat.full_chat, "call", None):
                await acc.invoke(JoinGroupCall(
                    call=full_chat.full_chat.call,
                    join_as=peer,
                    muted=True
                ))
                active_vc_clients.append(acc) # अकाउंट को एक्टिव रखें!
                success += 1
            else:
                await acc.disconnect()
                failed += 1
                
        except Exception as e:
            print(f"VC Join Error (ID {idx}): {e}")
            failed += 1
            
    return success, failed

async def leave_all_vcs():
    global active_vc_clients
    count = 0
    for acc in active_vc_clients:
        try:
            await acc.disconnect()
            count += 1
        except:
            pass
    active_vc_clients.clear()
    return count

