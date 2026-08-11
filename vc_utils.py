from pyrogram import Client
from pyrogram.errors import UserAlreadyParticipant

async def resolve_chat_entity(acc: Client, chat_input: str):
    clean_input = str(chat_input).strip()
    
    # 1. Private Invite Link (+ or joinchat)
    if "+" in clean_input or "joinchat" in clean_input:
        try:
            chat_obj = await acc.join_chat(clean_input)
            return chat_obj
        except UserAlreadyParticipant:
            try:
                invite_info = await acc.get_chat_invite_link_info(clean_input)
                return invite_info.chat
            except Exception as e:
                print(f"Invite link info error: {e}")
                return None
        except Exception as e:
            print(f"Join chat error: {e}")
            return None

    # 2. Group/Channel Numeric ID (-100...)
    if clean_input.lstrip("-").isdigit():
        chat_id = int(clean_input)
        try:
            return await acc.get_chat(chat_id)
        except Exception as e:
            print(f"Get chat by ID error: {e}")
            return None

    # 3. Public Username or Public Link
    target = clean_input.replace("https://t.me/", "").replace("t.me/", "").replace("@", "").strip()
    try:
        return await acc.get_chat(target)
    except Exception:
        try:
            return await acc.join_chat(target)
        except UserAlreadyParticipant:
            return await acc.get_chat(target)
        except Exception as e:
            print(f"Get/Join chat by username error: {e}")
            return None
