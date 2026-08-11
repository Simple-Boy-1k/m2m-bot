from pyrogram import Client
from pyrogram.errors import UserAlreadyParticipant
from pyrogram.raw.functions.messages import CheckChatInvite
from pyrogram.raw.types import ChatInviteAlready, ChatInvite

async def resolve_chat_entity(acc: Client, chat_input: str):
    clean_input = str(chat_input).strip()
    
    if "+" in clean_input or "joinchat" in clean_input:
        try:
            return await acc.join_chat(clean_input)
        except UserAlreadyParticipant:
            try:
                return await acc.get_chat(clean_input)
            except Exception:
                hash_str = clean_input.split("+")[-1].split("/")[0] if "+" in clean_input else clean_input.split("joinchat/")[-1].split("/")[0]
                try:
                    res = await acc.invoke(CheckChatInvite(hash=hash_str))
                    if isinstance(res, (ChatInviteAlready, ChatInvite)):
                        return await acc.get_chat(res.chat.id)
                except Exception:
                    pass
        except Exception:
            try:
                return await acc.get_chat(clean_input)
            except Exception:
                pass
        return None

    if clean_input.lstrip("-").isdigit():
        try:
            return await acc.get_chat(int(clean_input))
        except Exception:
            return None

    target = clean_input.replace("https://t.me/", "").replace("t.me/", "").replace("@", "").strip()
    try:
        return await acc.get_chat(target)
    except Exception:
        try:
            return await acc.join_chat(target)
        except UserAlreadyParticipant:
            return await acc.get_chat(target)
        except Exception:
            return None
