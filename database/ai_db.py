import logging
import re
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from info import DATABASE_URI, DATABASE_NAME

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class AIDatabase:
    def __init__(self, uri: str, db_name: str):
        self.client = AsyncIOMotorClient(uri)
        self.db = self.client[db_name]
        self.cache = self.db.ai_cache
        self.requests = self.db.movie_requests
        self.analytics = self.db.analytics_logs
        self._initialized = False

    async def init_indexes(self):
        """Initialize indexes such as TTL index for cache and indexes for analytics."""
        if self._initialized:
            return
        try:
            # TTL index for 24-hour cache (86400 seconds)
            await self.cache.create_index("created_at", expireAfterSeconds=86400)
            # Indexes for quick queries
            await self.analytics.create_index("timestamp")
            await self.analytics.create_index([("type", 1), ("timestamp", -1)])
            await self.requests.create_index("status")
            self._initialized = True
            logger.info("AIDatabase indexes initialized successfully.")
        except Exception as e:
            logger.error("Failed to initialize AIDatabase indexes: %s", e)

    # ----------------------------------------------------
    # Caching Layer
    # ----------------------------------------------------
    async def get_cache(self, key: str) -> dict:
        await self.init_indexes()
        try:
            doc = await self.cache.find_one({"_id": key})
            if doc:
                return doc.get("data")
        except Exception as e:
            logger.error("Error retrieving cache for key %s: %s", key, e)
        return None

    async def set_cache(self, key: str, data: dict):
        await self.init_indexes()
        try:
            await self.cache.update_one(
                {"_id": key},
                {"$set": {"data": data, "created_at": datetime.utcnow()}},
                upsert=True
            )
        except Exception as e:
            logger.error("Error setting cache for key %s: %s", key, e)

    # ----------------------------------------------------
    # Movie Requests Notification Layer
    # ----------------------------------------------------
    def _normalize_title(self, title: str) -> str:
        title = str(title).lower()
        # Remove years (e.g. 2025, 2026)
        title = re.sub(r"\b(19|20)\d{2}\b", "", title)
        # Remove non-alphanumeric chars
        title = re.sub(r"[^a-z0-9]", "", title)
        return title.strip()

    async def add_request(self, movie_title: str, user_id: int, chat_id: int, username: str):
        await self.init_indexes()
        normalized = self._normalize_title(movie_title)
        if not normalized:
            return
        try:
            user_data = {
                "user_id": int(user_id),
                "chat_id": int(chat_id),
                "username": username or "Unknown",
                "date": datetime.utcnow()
            }
            # Add user to the list of requestors for this normalized title
            await self.requests.update_one(
                {"_id": normalized},
                {
                    "$set": {"movie_title": movie_title, "status": "pending"},
                    "$addToSet": {"requested_users": user_data}
                },
                upsert=True
            )
            logger.info("Movie request recorded for '%s' (User: %s)", movie_title, user_id)
        except Exception as e:
            logger.error("Error adding movie request: %s", e)

    async def check_and_fulfill_requests(self, filename: str) -> list:
        """
        Check if an indexed filename matches a pending movie request.
        If it does, fulfill the request and return the list of users to notify.
        """
        await self.init_indexes()
        normalized_filename = self._normalize_title(filename)
        if not normalized_filename:
            return []
        
        try:
            # Retrieve all pending requests
            cursor = self.requests.find({"status": "pending"})
            fulfilled_users = []
            async for doc in cursor:
                req_id = doc["_id"]
                # If the normalized request title is a substring of the normalized filename
                if req_id in normalized_filename:
                    # Fulfill it!
                    await self.requests.update_one({"_id": req_id}, {"$set": {"status": "fulfilled"}})
                    fulfilled_users.extend(doc.get("requested_users", []))
                    logger.info("Fulfilling movie request for '%s' due to index of '%s'", doc["movie_title"], filename)
            
            # Deduplicate users by user_id
            seen = set()
            unique_users = []
            for u in fulfilled_users:
                if u["user_id"] not in seen:
                    seen.add(u["user_id"])
                    unique_users.append(u)
            return unique_users
        except Exception as e:
            logger.error("Error fulfilling movie requests: %s", e)
            return []

    # ----------------------------------------------------
    # Analytics & Logging Layer
    # ----------------------------------------------------
    async def log_event(self, event_type: str, user_id: int, query_or_file: str, extra: dict = None):
        await self.init_indexes()
        try:
            doc = {
                "type": event_type,
                "user_id": int(user_id) if user_id else None,
                "value": query_or_file,
                "timestamp": datetime.utcnow()
            }
            if extra:
                doc.update(extra)
            await self.analytics.insert_one(doc)
        except Exception as e:
            logger.error("Error logging analytics event: %s", e)

    async def get_analytics_summary(self) -> dict:
        await self.init_indexes()
        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)
        
        summary = {
            "daily_searches_success": 0,
            "daily_searches_fail": 0,
            "daily_downloads": 0,
            "most_requested": [],
            "most_watched": [],
            "top_languages": [],
            "top_genres": [],
            "failed_searches": [],
            "active_users_24h": 0
        }
        
        try:
            # 1. Daily search count
            summary["daily_searches_success"] = await self.analytics.count_documents({
                "type": "search_success",
                "timestamp": {"$gte": day_ago}
            })
            summary["daily_searches_fail"] = await self.analytics.count_documents({
                "type": "search_fail",
                "timestamp": {"$gte": day_ago}
            })

            # 2. Daily downloads
            summary["daily_downloads"] = await self.analytics.count_documents({
                "type": "download",
                "timestamp": {"$gte": day_ago}
            })

            # 3. Active users last 24h
            active_users = await self.analytics.distinct("user_id", {"timestamp": {"$gte": day_ago}})
            summary["active_users_24h"] = len(active_users)

            # 4. Most requested movies (Overall pending/fulfilled requests)
            pipeline_req = [
                {"$unwind": "$requested_users"},
                {"$group": {"_id": "$movie_title", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            req_results = await self.requests.aggregate(pipeline_req).to_list(5)
            summary["most_requested"] = [{"title": r["_id"], "count": r["count"]} for r in req_results]

            # 5. Most watched movies (Overall downloads log)
            pipeline_watched = [
                {"$match": {"type": "download"}},
                {"$group": {"_id": "$value", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            watched_results = await self.analytics.aggregate(pipeline_watched).to_list(5)
            summary["most_watched"] = [{"title": w["_id"], "count": w["count"]} for w in watched_results]

            # 6. Top Languages (parsed from downloads / searches in last 24h)
            pipeline_lang = [
                {"$match": {"type": "download", "timestamp": {"$gte": day_ago}, "language": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$language", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            lang_results = await self.analytics.aggregate(pipeline_lang).to_list(5)
            summary["top_languages"] = [{"language": l["_id"], "count": l["count"]} for l in lang_results]

            # 7. Top Genres (parsed in last 24h)
            pipeline_genre = [
                {"$match": {"type": "download", "timestamp": {"$gte": day_ago}, "genre": {"$exists": True, "$ne": None}}},
                {"$group": {"_id": "$genre", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]
            genre_results = await self.analytics.aggregate(pipeline_genre).to_list(5)
            summary["top_genres"] = [{"genre": g["_id"], "count": g["count"]} for g in genre_results]

            # 8. Failed searches (last 10)
            failed_cursor = self.analytics.find({"type": "search_fail"}).sort("timestamp", -1).limit(10)
            summary["failed_searches"] = [f["value"] async for f in failed_cursor]

        except Exception as e:
            logger.error("Error fetching analytics summary: %s", e)

        return summary

# Instantiate database instance with standard credentials
ai_db = AIDatabase(DATABASE_URI, DATABASE_NAME)
