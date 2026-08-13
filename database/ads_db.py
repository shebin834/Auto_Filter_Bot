import motor.motor_asyncio
from datetime import datetime, timedelta
from info import DATABASE_URI, DATABASE_NAME

class AdsDatabase:
    """
    Database handler for managing advertisements and their rotation mechanism.
    """
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db.ads
        self.rotation_col = self.db.ads_rotation

    async def add_ad(self, ad_id, content, msg_type, days, caption=None):
        """
        Inserts a new advertisement into the database with an expiration date.
        """
        expiry = datetime.now() + timedelta(days=days)
        ad_data = {
            "ad_id": ad_id,
            "content": content,
            "type": msg_type,
            "expiry": expiry,
            "caption": caption
        }
        await self.col.insert_one(ad_data)

    async def get_active_ads(self):
        """
        Retrieves all active advertisements and automatically purges expired ones.
        """
        await self.col.delete_many({"expiry": {"$lt": datetime.now()}})
        
        ads = []
        async for ad in self.col.find():
            ads.append(ad)
        return ads

    async def delete_ad(self, ad_id):
        """
        Deletes a specific advertisement from the database using its unique ad_id.
        """
        await self.col.delete_one({"ad_id": ad_id})

    async def get_next_ad(self):
        """
        Fetches the next advertisement based on a round-robin rotation mechanism.
        """
        ads = await self.get_active_ads()
        if not ads:
            return None
        
        rot_data = await self.rotation_col.find_one({"_id": "rotation"})
        current_index = rot_data.get("index", 0) if rot_data else 0
        
        if current_index >= len(ads):
            current_index = 0
        
        selected_ad = ads[current_index]
        
        next_index = (current_index + 1) % len(ads)
        await self.rotation_col.update_one(
            {"_id": "rotation"}, 
            {"$set": {"index": next_index}}, 
            upsert=True
        )
        
        return selected_ad

# Initialize the database instance
ads_db = AdsDatabase(DATABASE_URI, DATABASE_NAME)