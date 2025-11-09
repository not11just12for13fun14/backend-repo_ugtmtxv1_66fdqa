import os
from typing import Any, Dict, List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "app_db")

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(DATABASE_URL)
        _db = _client[DATABASE_NAME]
    return _db

# Backwards-compatible export used by the scaffolding
db = get_db()


async def ensure_indexes() -> None:
    # Unique email for users
    await db["user"].create_index("email", unique=True)
    # Basic indexes for courses
    await db["course"].create_index([("published", 1)])
    await db["course"].create_index([("title", 1)])


async def create_document(collection_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    now = datetime.utcnow().isoformat()
    data_to_insert = {**data, "created_at": now, "updated_at": now}
    result = await db[collection_name].insert_one(data_to_insert)
    inserted = await db[collection_name].find_one({"_id": result.inserted_id})
    if inserted:
        inserted["id"] = str(inserted.pop("_id"))
    return inserted or {}


async def get_documents(collection_name: str, filter_dict: Optional[Dict[str, Any]] = None, limit: int = 50) -> List[Dict[str, Any]]:
    filter_dict = filter_dict or {}
    cursor = db[collection_name].find(filter_dict).limit(limit)
    docs: List[Dict[str, Any]] = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        docs.append(doc)
    return docs
