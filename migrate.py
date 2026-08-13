import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# DB URI-gal ivide nalkuka
OLD_DB_URI = "mongodb+srv://shebin:eOFYZRp6YiCzjtN6@cluster0.hunvcay.mongodb.net/myDatabase?retryWrites=true&w=majority"
NEW_DB_URI = "mongodb://Shebin:Shebin%408156@localhost:27017/admin?authSource=admin"

async def migrate():
    old_client = AsyncIOMotorClient(OLD_DB_URI)
    new_client = AsyncIOMotorClient(NEW_DB_URI)
    
    old_db = old_client['DreamXBotz'] # Ninte db name
    new_db = new_client['DreamXBotz']
    
    # Collections list
    collections = ['media', 'users', 'groups'] # Collections-inte perukal
    
    for coll in collections:
        print(f"Migrating {coll}...")
        data = await old_db[coll].find().to_list(length=None)
        if data:
            await new_db[coll].insert_many(data)
            print(f"Successfully migrated {len(data)} items to {coll}")
            
    print("Migration Completed!")

if __name__ == "__main__":
    asyncio.run(migrate())