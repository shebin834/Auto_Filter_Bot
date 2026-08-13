import logging
import re
import aiohttp
import time
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from info import GEMINI_API_KEY, AI_RATE_LIMIT_HOUR, AI_PROVIDER, TMDB_API_KEY
from ai.ai_providers import GeminiProvider
from database.ai_db import ai_db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# In-memory rate limiter tracker: {user_id: [timestamp, timestamp]}
_ai_requests_timestamps = {}

# Initialize AI Provider
ai_provider = GeminiProvider(GEMINI_API_KEY)

def is_user_rate_limited(user_id: int) -> bool:
    """Checks if a user is rate limited for AI commands (Max limit/hour)."""
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    
    # Initialize list if missing
    if user_id not in _ai_requests_timestamps:
        _ai_requests_timestamps[user_id] = [now]
        return False
        
    # Filter out timestamps older than 1 hour
    timestamps = [ts for ts in _ai_requests_timestamps[user_id] if ts > hour_ago]
    _ai_requests_timestamps[user_id] = timestamps
    
    if len(timestamps) >= AI_RATE_LIMIT_HOUR:
        return True
        
    _ai_requests_timestamps[user_id].append(now)
    return False

def reset_user_rate_limit(user_id: int):
    """Resets rate limit for a specific user (useful for testing or premium)."""
    if user_id in _ai_requests_timestamps:
        del _ai_requests_timestamps[user_id]

# ----------------------------------------------------
# Official OTT Metadata Lookup (TMDB API)
# ----------------------------------------------------
async def fetch_ott_info_tmdb(title: str) -> dict:
    """
    Query the official TMDB API for a movie's release date and OTT platforms.
    """
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not configured. Skipping TMDB OTT search.")
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. Search for the movie
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={quote_plus(title)}"
            async with session.get(search_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                results = data.get("results")
                if not results:
                    return None
                
                # Take the first match
                movie = results[0]
                movie_id = movie["id"]
                display_title = movie["title"]
                raw_release_date = movie.get("release_date")
                
            # 2. Get watch providers
            providers_url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={TMDB_API_KEY}"
            async with session.get(providers_url) as resp:
                if resp.status != 200:
                    return None
                providers_data = await resp.json()
                results = providers_data.get("results", {})
                
                # We focus on India (IN) but fallback to US or global if none found
                providers_in = results.get("IN", {})
                flatrate_providers = providers_in.get("flatrate", [])
                
                if not flatrate_providers:
                    # Fallback: check other regions if India doesn't have it
                    for country, config in results.items():
                        if isinstance(config, dict) and "flatrate" in config:
                            flatrate_providers = config["flatrate"]
                            break
                            
                platforms = [p["provider_name"] for p in flatrate_providers]
                
            # Parse release date
            release_dt = None
            if raw_release_date:
                try:
                    # Convert YYYY-MM-DD to "DD Month YYYY"
                    dt = datetime.strptime(raw_release_date, "%Y-%m-%d")
                    release_dt = dt.strftime("%d %B %Y")
                except Exception:
                    release_dt = raw_release_date

            # Check if already released on OTT (has platforms or release date is in the past)
            released = False
            if platforms:
                released = True
            elif raw_release_date:
                try:
                    dt = datetime.strptime(raw_release_date, "%Y-%m-%d")
                    if dt < datetime.utcnow():
                        released = True
                except Exception:
                    pass

            return {
                "movie_title": display_title,
                "released": released,
                "release_date": release_dt,
                "platforms": platforms,
                "source": "TMDB"
            }
    except Exception as e:
        logger.error("Error fetching OTT from TMDB for '%s': %s", title, e)
    return None

async def fetch_ott_info_ai(title: str) -> dict:
    """
    Fallback method to query AI about OTT release details.
    """
    if not ai_provider.enabled:
        return None
    try:
        current_date = datetime.utcnow().strftime("%d %B %Y")
        prompt = (
            f"As of today ({current_date}), what is the OTT release status of the movie '{title}'? "
            "Reply with a JSON block containing these fields:\n"
            "- 'movie_title': string (corrected title)\n"
            "- 'released': boolean (has it been released on OTT?)\n"
            "- 'release_date': string or null (if officially announced or released, specify date e.g. '19 June 2026', otherwise null)\n"
            "- 'platforms': list of strings or [] (platforms like Netflix, Prime Video, etc.)\n"
            "Rules:\n"
            "1. Never hallucinate release dates. If the date is not officially announced, set 'release_date' to null.\n"
            "2. Ensure valid JSON format. Return ONLY the JSON object, nothing else."
        )
        response = await ai_provider.chat(prompt)
        text = response.strip()
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
        import json
        data = json.loads(text)
        data["source"] = "AI"
        return data
    except Exception as e:
        logger.error("Error fetching OTT from AI for '%s': %s", title, e)
    return None

async def get_ott_info(title: str) -> dict:
    """
    Fetch OTT info from cache, or query TMDB (primary) and AI (fallback).
    Stores results in cache for 24 hours.
    """
    cache_key = f"ott_info_{title.lower().strip()}"
    cached = await ai_db.get_cache(cache_key)
    if cached:
        return cached

    # Try TMDB first
    ott_info = await fetch_ott_info_tmdb(title)
    
    # Fallback to AI if TMDB returns nothing
    if not ott_info:
        ott_info = await fetch_ott_info_ai(title)

    if ott_info:
        # Save to cache
        await ai_db.set_cache(cache_key, ott_info)
        return ott_info
        
    return {
        "movie_title": title,
        "released": False,
        "release_date": None,
        "platforms": [],
        "source": "None"
    }

# ----------------------------------------------------
# Combined Wrapper Functions
# ----------------------------------------------------
async def get_spoiler_free_summary(title: str) -> str:
    cache_key = f"summary_{title.lower().strip()}"
    cached = await ai_db.get_cache(cache_key)
    if cached:
        return cached.get("summary")

    summary = await ai_provider.get_summary(title)
    if summary:
        await ai_db.set_cache(cache_key, {"summary": summary})
    return summary

async def get_similar_movies(title: str) -> list:
    cache_key = f"similar_{title.lower().strip()}"
    cached = await ai_db.get_cache(cache_key)
    if cached:
        return cached.get("movies")

    movies = await ai_provider.get_similar_movies(title)
    if movies:
        await ai_db.set_cache(cache_key, {"movies": movies})
    return movies or []

# ----------------------------------------------------
# Premium Reply Layout Helpers
# ----------------------------------------------------
async def get_premium_movie_details(title: str, confidence: str = None) -> dict:
    """
    Fetch complete metadata for the movie to build the premium layout.
    """
    cache_key = f"premium_details_{title.lower().strip()}"
    cached = await ai_db.get_cache(cache_key)
    if cached:
        if confidence:
            cached["confidence"] = confidence
        return cached
        
    details = {
        "title": title,
        "year": "N/A",
        "rating": "N/A",
        "genres": "N/A",
        "languages": "N/A",
        "qualities": "480p • 720p • 1080p",
        "story": "No summary available.",
        "similar": [],
        "platforms": [],
        "released": False,
        "release_date": "N/A",
        "confidence": confidence or "High"
    }
    
    # 1. Query TMDB
    if TMDB_API_KEY:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={quote_plus(title)}"
                async with session.get(search_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results")
                        if results:
                            movie = results[0]
                            movie_id = movie["id"]
                            details["title"] = movie.get("title", title)
                            
                            rd = movie.get("release_date")
                            if rd:
                                details["release_date"] = rd
                                try:
                                    details["year"] = str(datetime.strptime(rd, "%Y-%m-%d").year)
                                except Exception:
                                    details["year"] = rd[:4]
                                    
                            details["rating"] = f"{movie.get('vote_average', 'N/A')}/10"
                            details["story"] = movie.get("overview", "No summary available.")
                            
                            # Calculate match confidence using WRatio
                            try:
                                from rapidfuzz import fuzz
                                ratio = fuzz.WRatio(title, movie.get("title"))
                                details["confidence"] = confidence or f"{int(ratio)}%"
                            except Exception:
                                pass
                            
                            # Get additional details
                            details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}"
                            async with session.get(details_url) as det_resp:
                                if det_resp.status == 200:
                                    det_data = await det_resp.json()
                                    genres = [g["name"] for g in det_data.get("genres", [])]
                                    if genres:
                                        details["genres"] = " • ".join(genres)
                                    langs = [l["english_name"] for l in det_data.get("spoken_languages", [])]
                                    if langs:
                                        details["languages"] = " • ".join(langs)
                                        
                            # Get watch providers
                            prov_url = f"https://api.themoviedb.org/3/movie/{movie_id}/watch/providers?api_key={TMDB_API_KEY}"
                            async with session.get(prov_url) as prov_resp:
                                if prov_resp.status == 200:
                                    prov_data = await prov_resp.json()
                                    prov_results = prov_data.get("results", {})
                                    providers_in = prov_results.get("IN", {})
                                    flatrate = providers_in.get("flatrate", [])
                                    if not flatrate:
                                        for country, config in prov_results.items():
                                            if isinstance(config, dict) and "flatrate" in config:
                                                flatrate = config["flatrate"]
                                                break
                                    details["platforms"] = [p["provider_name"] for p in flatrate]
                                    if details["platforms"] or (rd and datetime.strptime(rd, "%Y-%m-%d") < datetime.utcnow()):
                                        details["released"] = True
        except Exception as e:
            logger.error("Error fetching premium movie details from TMDB: %s", e)

    # 2. Fallback to Gemini if story or rating is missing
    if (details["story"] == "No summary available." or details["rating"] == "N/A") and ai_provider.enabled:
        try:
            prompt = (
                f"Provide details for the movie '{title}' in this exact JSON format:\n"
                "{\n"
                "  \"title\": \"Movie Name\",\n"
                "  \"year\": \"Year\",\n"
                "  \"rating\": \"Rating/10\",\n"
                "  \"genres\": \"Genre1 • Genre2\",\n"
                "  \"languages\": \"Language1 • Language2\",\n"
                "  \"story\": \"Short spoiler-free summary.\"\n"
                "}\n"
                "Return ONLY the raw JSON object, do not write other text."
            )
            response = await ai_provider.chat(prompt)
            text = response.strip()
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*$", "", text).strip()
            import json
            ai_data = json.loads(text)
            for k in ["title", "year", "rating", "genres", "languages", "story"]:
                if ai_data.get(k):
                    details[k] = ai_data[k]
            details["confidence"] = confidence or "High"
        except Exception as e:
            logger.error("Error fetching premium details from Gemini: %s", e)
            
    # Similar movies
    try:
        similar = await get_similar_movies(title)
        if similar:
            details["similar"] = similar
    except Exception:
        pass
        
    await ai_db.set_cache(cache_key, details)
    return details

def format_premium_reply(details: dict) -> str:
    """
    Formats the movie metadata dictionary into the Premium FilmFox AI Reply Layout.
    """
    title_str = details['title']
    if details.get('year') and details['year'] != "N/A":
        title_str += f" ({details['year']})"
        
    similar_str = "• " + "\n• ".join(details['similar'][:3]) if details.get('similar') else "• No similar movies suggested."
    platforms_str = " • ".join(details['platforms']) if details.get('platforms') else "Not Streaming / TBA"
    release_date_str = details.get('release_date', 'N/A')
    
    confidence = details.get("confidence") or "High"
    elapsed = details.get("elapsed")
    
    footer_lines = []
    footer_lines.append("🤖 Powered by FilmFox AI")
    if elapsed is not None:
        footer_lines.append(f"⚡ Response Time: {elapsed:.2f} sec")
    else:
        footer_lines.append("⚡ Fast • Smart • Accurate")
        
    footer_str = "\n".join(footer_lines)
    
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>FilmFox AI</b>\n"
        f"Your Smart Movie Assistant\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 <b>{title_str}</b>\n\n"
        f"⭐ IMDb : {details.get('rating', 'N/A')}\n"
        f"🎭 Genre : {details.get('genres', 'N/A')}\n"
        f"🌍 Language : {details.get('languages', 'N/A')}\n"
        f"📺 Quality : {details.get('qualities', '480p • 720p • 1080p')}\n\n"
        f"🎯 AI Confidence : {confidence}\n\n"
        f"📝 Story\n"
        f"{details.get('story', 'No summary available.')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 AI Suggestions\n"
        f"• Similar Movies\n"
        f"• OTT Information: {platforms_str} (Rel: {release_date_str})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{footer_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    return text
