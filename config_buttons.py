from pyrogram.types import InlineKeyboardButton

def create_safe_button(text, callback_data, enabled=True):
    """
    Creates a safe InlineKeyboardButton.
    """
    return InlineKeyboardButton(text=text, callback_data=callback_data)
