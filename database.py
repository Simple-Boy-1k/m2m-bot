import motor.motor_asyncio
import config

client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_DB_URI)
db = client["M2M_VC_BOT"]
sessions_col = db["sessions"]

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

async def delete_all_sessions() -> int:
    result = await sessions_col.delete_many({})
    return result.deleted_count

async def get_sessions_count() -> int:
    return await sessions_col.count_documents({})

