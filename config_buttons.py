# config_buttons.py
import random
from pyrogram.types import InlineKeyboardButton

# Available styles
STYLES = ["primary", "success", "danger"]

def get_button_style(enabled: bool):
    """Agar enabled True hai, toh random style return karega, warna None."""
    if enabled:
        return random.choice(STYLES)
    return None

def create_safe_button(text, callback_data, enabled=True):
    """Yeh function safe button create karega bina crash ke."""
    style = get_button_style(enabled)
    # Pyrogram version check ke liye basic implementation
    try:
        if style:
            return InlineKeyboardButton(text, callback_data=callback_data, style=style)
        return InlineKeyboardButton(text, callback_data=callback_data)
    except TypeError:
        # Agar 'style' argument support nahi karta toh normal button return karega
        return InlineKeyboardButton(text, callback_data=callback_data)

