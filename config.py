import os

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_DB_URI = os.environ.get("MONGO_DB_URI", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# Dynamic Button Colour Config
BUTTON_COLOUR = os.environ.get("BUTTON_COLOUR", "True").lower() in ("true", "1", "t")
