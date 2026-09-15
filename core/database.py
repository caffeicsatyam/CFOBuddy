import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.environ.get("MONGODB_URL", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "cfobuddy")

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

async def connect_to_mongo():
    db_instance.client = AsyncIOMotorClient(
        MONGODB_URL,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
    )
    db_instance.db = db_instance.client[MONGODB_DB_NAME]
    # Verify connectivity early so we get a clear error at startup
    try:
        await db_instance.client.admin.command("ping")
        print("Connected to MongoDB")
    except Exception as e:
        print(f"⚠ MongoDB connection failed: {e}")
        print("  Auth endpoints that require the database will return errors.")

async def close_mongo_connection():
    if db_instance.client:
        db_instance.client.close()
        print("Closed MongoDB connection")

def get_db():
    return db_instance.db
