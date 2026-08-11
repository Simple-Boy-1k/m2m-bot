import motor.motor_asyncio
import config

client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_DB_URI)
db = client["M2M_VC_BOT"]
sessions_col = db["sessions"]
settings_col = db["settings"]

async def add_session(session_string: str) -> bool:
    clean_session = session_string.strip()
    exists = await sessions_col.find_one({"session": clean_session})
    if not exists:
        await sessions_col.insert_one({"session": clean_session})
        return True
    return False

async def get_all_sessions() -> list:
    sessions = []
    async for doc in sessions_col.find({}):
        sessions.append(doc["session"])
    return sessions

async def delete_session(session_string: str):
    await sessions_col.delete_one({"session": session_string.strip()})

async def delete_all_sessions() -> int:
    result = await sessions_col.delete_many({})
    return result.deleted_count

async def get_sessions_count() -> int:
    return await sessions_col.count_documents({})

async def get_auto_views() -> bool:
    doc = await settings_col.find_one({"type": "auto_views"})
    if doc:
        return doc.get("status", True)
    await settings_col.insert_one({"type": "auto_views", "status": True})
    return True

async def toggle_auto_views() -> bool:
    current = await get_auto_views()
    new_status = not current
    await settings_col.update_one(
        {"type": "auto_views"},
        {"$set": {"status": new_status}},
        upsert=True
    )
    return new_status
