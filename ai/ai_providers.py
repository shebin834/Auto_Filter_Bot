import logging
import json
import re
import asyncio
from abc import ABC, abstractmethod
import google.generativeai as genai
from PIL import Image
from info import GEMINI_API_KEY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

import logging
import json
import re
import asyncio
import time
from abc import ABC, abstractmethod
import google.generativeai as genai
from PIL import Image
from info import GEMINI_API_KEY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL_CANDIDATES = [
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-pro",
    "models/gemini-2.0-flash-lite",
]


class BaseAIProvider(ABC):
    @abstractmethod
    async def spell_check(self, query: str) -> str:
        """Correct misspelled movie names."""
        pass

    @abstractmethod
    async def parse_nlp_intent(self, query: str) -> list:
        """Extract matching movie titles from natural language searches."""
        pass

    @abstractmethod
    async def guess_movie(self, description: str) -> str:
        """Guess movie from plot/scene description."""
        pass

    @abstractmethod
    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe voice message containing English, Malayalam, or Manglish."""
        pass

    @abstractmethod
    async def identify_image(self, file_path: str) -> str:
        """Identify movie from screenshot/poster/image."""
        pass

    @abstractmethod
    async def get_summary(self, movie_title: str) -> str:
        """Get a short spoiler-free movie summary."""
        pass

    @abstractmethod
    async def get_similar_movies(self, movie_title: str) -> list:
        """Get 4 similar movies."""
        pass

    @abstractmethod
    async def chat(self, prompt: str) -> str:
        """General movie assistant chat."""
        pass


class GeminiProvider(BaseAIProvider):
    def __init__(self, api_key=None):
        self.api_keys = self._parse_keys(api_key or GEMINI_API_KEY)
        self.enabled = bool(self.api_keys)
        self.current_key_idx = 0
        self.active_model_name = "models/gemini-2.0-flash"
        self.model = None
        self._mem_cache = {}
        self._cache_ttl = 600  # 10 minutes

        if self.enabled:
            try:
                genai.configure(api_key=self.get_current_key())
                self.model = genai.GenerativeModel(self.active_model_name)
                logger.info("Gemini AI Provider initialized with %d key(s) using model %s", len(self.api_keys), self.active_model_name)
            except Exception as e:
                logger.error("Failed to initialize Gemini AI Provider: %s", e)

    def _parse_keys(self, raw_input) -> list:
        if not raw_input:
            return []
        if isinstance(raw_input, list):
            return [k.strip() for k in raw_input if k and isinstance(k, str) and k.strip()]
        if isinstance(raw_input, str):
            # Split by comma or space or newline
            keys = [k.strip() for k in re.split(r'[,\s]+', raw_input) if k.strip()]
            return keys
        return []

    def get_current_key(self) -> str:
        if not self.api_keys:
            return None
        return self.api_keys[self.current_key_idx % len(self.api_keys)]

    def rotate_key(self) -> str:
        if not self.api_keys or len(self.api_keys) <= 1:
            return self.get_current_key()
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        new_key = self.get_current_key()
        logger.info("Rotated Gemini API Key to key index %d (%s...)", self.current_key_idx, new_key[:8] if new_key else "")
        return new_key

    def _get_cache(self, key: str):
        if key in self._mem_cache:
            ts, val = self._mem_cache[key]
            if time.time() - ts < self._cache_ttl:
                return val
            else:
                del self._mem_cache[key]
        return None

    def _set_cache(self, key: str, val):
        if len(self._mem_cache) > 5000:
            self._mem_cache.clear()
        self._mem_cache[key] = (time.time(), val)

    async def _generate_content_async(self, contents, system_instruction=None):
        if not self.enabled or not self.api_keys:
            return None

        def _call(api_key_str, model_name_str, content_input):
            genai.configure(api_key=api_key_str)
            if system_instruction:
                m_obj = genai.GenerativeModel(model_name_str, system_instruction=system_instruction)
            else:
                m_obj = genai.GenerativeModel(model_name_str)
            return m_obj.generate_content(content_input)

        last_exc = None
        num_keys = len(self.api_keys)

        # Try key pool in rotation
        for key_attempt in range(num_keys):
            current_key = self.get_current_key()
            models_to_try = [self.active_model_name] + [m for m in MODEL_CANDIDATES if m != self.active_model_name]

            for model_name in models_to_try:
                try:
                    # Run call with 8 second timeout per attempt
                    response = await asyncio.wait_for(
                        asyncio.to_thread(_call, current_key, model_name, contents),
                        timeout=8.0
                    )
                    if response:
                        self.active_model_name = model_name
                        return response
                except asyncio.TimeoutError:
                    logger.warning("Gemini call timed out on model %s with key index %d", model_name, self.current_key_idx)
                    last_exc = TimeoutError("Gemini request timed out")
                    continue
                except Exception as e:
                    err_str = str(e).lower()
                    last_exc = e

                    # Key validation error check
                    if "leaked" in err_str or "api key not valid" in err_str or "api_key_invalid" in err_str or "permissiondenied" in err_str:
                        logger.error("Gemini API key index %d is invalid/leaked: %s", self.current_key_idx, e)
                        if num_keys > 1:
                            self.rotate_key()
                            break  # Try next key
                        else:
                            raise ValueError("API_KEY_INVALID: Configured GEMINI_API_KEY is invalid, leaked, or revoked. Please update GEMINI_API_KEY in info.py with a new key from Google AI Studio (https://aistudio.google.com/).")
                    elif "resourceexhausted" in err_str or "429" in err_str or "quota" in err_str:
                        logger.warning("Gemini API key index %d rate limited / quota exhausted: %s. Rotating key...", self.current_key_idx, e)
                        if num_keys > 1:
                            self.rotate_key()
                            break  # Try next key
                    else:
                        logger.warning("Gemini model %s error (%s), falling back to next model...", model_name, e)
                        continue

        if last_exc:
            raise last_exc
        return None

    async def spell_check(self, query: str) -> str:
        if not self.enabled:
            return query

        cache_key = f"spell_{query.lower().strip()}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            prompt = (
                f"You are an expert movie title spellchecker specializing in Indian (Malayalam, Tamil, Hindi, Telugu) and International cinema. "
                f"The user entered the search query: '{query}'. "
                f"Correct any spelling mistakes, character swaps, or phonetic typos (e.g. 'Pallichattanbi' -> 'Pallichattambi', 'Idenity' -> 'Identity'). "
                f"Reply ONLY with the corrected movie title. Do NOT include quotes, explanations, years, or extra punctuation."
            )
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                result = response.text.strip()
                res = result if result else query
                self._set_cache(cache_key, res)
                return res
            return query
        except Exception as e:
            logger.error("Error in Gemini spell_check: %s", e)
            return query

    async def parse_nlp_intent(self, query: str) -> list:
        if not self.enabled:
            return []

        cache_key = f"intent_{query.lower().strip()}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            prompt = (
                f"The user query is: '{query}'. This query might contain natural language patterns seeking movies of a certain genre, actor, year, language, or mood. "
                "Extract the user intent and list up to 5 real movie titles that match. "
                "Return a JSON array of strings containing ONLY the movie names. "
                "If this is not a search with attributes or intent, return an empty array []."
            )
            response = await self._generate_content_async(prompt)
            if not response or not hasattr(response, "text"):
                return []
            text = response.text.strip()

            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*$", "", text).strip()

            try:
                titles = json.loads(text)
                if isinstance(titles, list):
                    self._set_cache(cache_key, titles)
                    return titles
            except Exception:
                matches = re.findall(r'"([^"]+)"', text)
                if matches:
                    self._set_cache(cache_key, matches)
                    return matches
            return []
        except Exception as e:
            logger.error("Error in Gemini parse_nlp_intent: %s", e)
            return []

    async def guess_movie(self, description: str) -> str:
        if not self.enabled:
            return ""

        cache_key = f"guess_{description.lower().strip()[:60]}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            prompt = (
                f"Identify the movie from this scene or plot description: '{description}'. "
                "Reply with ONLY the correct movie title (and year if known). "
                "If you cannot identify the movie, reply with 'Unknown'."
            )
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                result = response.text.strip()
                res = "" if result.lower() == "unknown" else result
                self._set_cache(cache_key, res)
                return res
            return ""
        except Exception as e:
            logger.error("Error in Gemini guess_movie: %s", e)
            return ""

    async def transcribe_audio(self, file_path: str) -> str:
        if not self.enabled:
            return ""
        try:
            audio_file = await asyncio.to_thread(genai.upload_file, path=file_path)
            prompt = "Transcribe this audio file and return only the spoken movie title or query."
            response = await self._generate_content_async([audio_file, prompt])

            try:
                await asyncio.to_thread(genai.delete_file, audio_file.name)
            except Exception:
                pass

            if response and hasattr(response, "text"):
                return response.text.strip()
            return ""
        except Exception as e:
            logger.error("Error in Gemini transcribe_audio: %s", e)
            return ""

    async def identify_image(self, file_path: str) -> str:
        if not self.enabled:
            return ""
        try:
            img = Image.open(file_path)
            prompt = (
                "This image is from a movie or TV show. Identify it and reply with ONLY the title and year if known."
            )
            response = await self._generate_content_async([img, prompt])
            if response and hasattr(response, "text"):
                result = response.text.strip()
                return "" if result.lower() == "unknown" else result
            return ""
        except Exception as e:
            logger.error("Error in Gemini identify_image: %s", e)
            return ""

    async def get_summary(self, movie_title: str) -> str:
        if not self.enabled:
            return "No summary available."

        cache_key = f"summary_{movie_title.lower().strip()}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            prompt = f"Write a short, spoiler-free summary for '{movie_title}' in 1-2 sentences."
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                res = response.text.strip()
                self._set_cache(cache_key, res)
                return res
            return "No summary available."
        except Exception as e:
            logger.error("Error in Gemini get_summary: %s", e)
            return "No summary available."

    async def get_similar_movies(self, movie_title: str) -> list:
        if not self.enabled:
            return []

        cache_key = f"similar_{movie_title.lower().strip()}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        try:
            prompt = (
                f"Suggest up to 4 movies similar to '{movie_title}'. "
                "Return a JSON array of strings containing ONLY the titles."
            )
            response = await self._generate_content_async(prompt)
            if not response or not hasattr(response, "text"):
                return []
            text = response.text.strip()

            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*$", "", text).strip()

            try:
                titles = json.loads(text)
                if isinstance(titles, list):
                    res = [t.strip() for t in titles]
                    self._set_cache(cache_key, res)
                    return res
            except Exception:
                matches = re.findall(r'"([^"]+)"', text)
                if matches:
                    res = [m.strip() for m in matches]
                    self._set_cache(cache_key, res)
                    return res
            return []
        except Exception as e:
            logger.error("Error in Gemini get_similar_movies: %s", e)
            return []

    async def chat(self, prompt: str) -> str:
        if not self.enabled:
            return "⚠️ <b>AI Unavailable:</b> No valid GEMINI_API_KEY configured. Please set a valid Gemini API Key from Google AI Studio in `info.py` or environment variables."

        cache_key = f"chat_{prompt.lower().strip()}"
        cached = self._get_cache(cache_key)
        if cached:
            return cached

        try:
            system_instruction = (
                "You are FilmFox AI, the official intelligent AI movie assistant created for FilmFox Bot. "
                "CRITICAL IDENTITY RULE: You must NEVER state or imply that you are Gemini, Google Gemini, Google AI, OpenAI, ChatGPT, or an LLM. "
                "If asked about your identity, name, creator, or model, ALWAYS state clearly in English, Malayalam, or Manglish that you are FilmFox AI, the official intelligent movie assistant of FilmFox Bot. "
                "Answer questions about movies, series, comparisons, cast, crew, recommendations, and reviews naturally, engagingly, and briefly. "
                "If the user asks something completely unrelated to movies, politely redirect them to movie-related topics."
            )

            response = await self._generate_content_async(prompt, system_instruction=system_instruction)

            if not response or not hasattr(response, "text"):
                logger.error("Gemini chat returned an empty response.")
                return "I'm sorry, I couldn't generate a response right now."

            res = response.text.strip()
            self._set_cache(cache_key, res)
            return res

        except ValueError as ve:
            logger.error("ValueError in Gemini chat: %s", ve)
            return "⚠️ <b>AI Error:</b> The configured GEMINI_API_KEY is invalid or reported as leaked. Please update `GEMINI_API_KEY` in `info.py` with a valid key from Google AI Studio (https://aistudio.google.com/)."
        except Exception as e:
            err_str = str(e).lower()
            if "leaked" in err_str or "api key not valid" in err_str or "api_key_invalid" in err_str or "403" in err_str or "permissiondenied" in err_str:
                return "⚠️ <b>AI Error:</b> The configured GEMINI_API_KEY is invalid or reported as leaked. Please update `GEMINI_API_KEY` in `info.py` with a valid key from Google AI Studio (https://aistudio.google.com/)."
            logger.exception("Error in Gemini chat: %s", e)
            return "⚠️ <b>AI Error:</b> Unable to process request. Please ensure a valid `GEMINI_API_KEY` from Google AI Studio is configured in `info.py`."