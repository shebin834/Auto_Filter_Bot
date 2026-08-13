import logging
import json
import re
import asyncio
from abc import ABC, abstractmethod
import google.generativeai as genai
from PIL import Image

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL_CANDIDATES = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-1.5-flash"]


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
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.enabled = bool(api_key)
        self.active_model_name = "gemini-3.6-flash"
        if self.enabled:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(self.active_model_name)
                logger.info("Gemini AI Provider initialized with model %s", self.active_model_name)
            except Exception as e:
                logger.exception("Failed to initialize Gemini Provider: %s", e)
                self.enabled = False
        else:
            logger.warning("Gemini Provider disabled or no valid API key was provided.")

    async def _generate_content_async(self, contents, system_instruction=None):
        if not self.enabled or not self.api_key:
            return None

        def _call(model_obj, content_input):
            return model_obj.generate_content(content_input)

        for model_name in [self.active_model_name] + [m for m in MODEL_CANDIDATES if m != self.active_model_name]:
            try:
                genai.configure(api_key=self.api_key)
                if system_instruction:
                    model_obj = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                else:
                    model_obj = genai.GenerativeModel(model_name)

                response = await asyncio.to_thread(_call, model_obj, contents)
                if response:
                    self.active_model_name = model_name
                    self.model = model_obj
                    return response
            except Exception as e:
                err_str = str(e).lower()
                if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                    logger.warning("Gemini model %s returned 404/Not Found, attempting fallback...", model_name)
                    continue
                elif "api key not valid" in err_str or "api_key_invalid" in err_str or "400" in err_str or "403" in err_str:
                    logger.error("Gemini API key is invalid or unauthorized: %s", e)
                    raise ValueError("API_KEY_INVALID: Please configure a valid GEMINI_API_KEY in info.py or environment variables.")
                else:
                    logger.error("Error generating content with %s: %s", model_name, e)
                    raise e
        return None

    async def spell_check(self, query: str) -> str:
        if not self.enabled:
            return query
        try:
            prompt = (
                f"The user is searching for a movie/series and entered: '{query}'. "
                "If it looks misspelled, reply with ONLY the correct movie or series title "
                "(preferably with its release year in brackets, e.g. 'Avengers (2012)'). "
                "If you cannot determine the movie or if it's already correct, "
                "reply with the original text exactly. "
                "Do not include any greeting, explanation, or punctuation."
            )
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                result = response.text.strip()
                return result if result else query
            return query
        except Exception as e:
            logger.error("Error in Gemini spell_check: %s", e)
            return query

    async def parse_nlp_intent(self, query: str) -> list:
        if not self.enabled:
            return []
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
                    return titles
            except Exception:
                matches = re.findall(r'"([^"]+)"', text)
                if matches:
                    return matches
            return []
        except Exception as e:
            logger.error("Error in Gemini parse_nlp_intent: %s", e)
            return []

    async def guess_movie(self, description: str) -> str:
        if not self.enabled:
            return ""
        try:
            prompt = (
                f"Identify the movie from this scene or plot description: '{description}'. "
                "Reply with ONLY the correct movie title (and year if known). "
                "If you cannot identify the movie, reply with 'Unknown'."
            )
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                result = response.text.strip()
                return "" if result.lower() == "unknown" else result
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
        try:
            prompt = f"Write a short, spoiler-free summary for '{movie_title}' in 1-2 sentences."
            response = await self._generate_content_async(prompt)
            if response and hasattr(response, "text"):
                return response.text.strip()
            return "No summary available."
        except Exception as e:
            logger.error("Error in Gemini get_summary: %s", e)
            return "No summary available."

    async def get_similar_movies(self, movie_title: str) -> list:
        if not self.enabled:
            return []
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
                    return [t.strip() for t in titles]
            except Exception:
                matches = re.findall(r'"([^"]+)"', text)
                if matches:
                    return [m.strip() for m in matches]
            return []
        except Exception as e:
            logger.error("Error in Gemini get_similar_movies: %s", e)
            return []

    async def chat(self, prompt: str) -> str:
        if not self.enabled:
            return "⚠️ <b>AI Unavailable:</b> No valid GEMINI_API_KEY configured. Please set a valid Gemini API Key from Google AI Studio in `info.py` or environment variables."

        try:
            system_instruction = (
                "You are an expert Movie Assistant. Answer questions about movies, series, comparisons, cast, crew, recommendations, and reviews naturally, engagingly, and briefly. "
                "If the user asks something completely unrelated to movies, politely redirect them to movie-related topics."
            )

            response = await self._generate_content_async(prompt, system_instruction=system_instruction)

            if not response or not hasattr(response, "text"):
                logger.error("Gemini chat returned an empty response.")
                return "I'm sorry, I couldn't generate a response right now."

            return response.text.strip()

        except ValueError as ve:
            if "API_KEY_INVALID" in str(ve):
                return "⚠️ <b>AI Error:</b> Invalid GEMINI_API_KEY. Please provide a valid Gemini API Key from Google AI Studio in `info.py` or environment variables."
            return f"⚠️ <b>AI Error:</b> {ve}"
        except Exception as e:
            logger.exception("Error in Gemini chat: %s", e)
            return "I'm sorry, I encountered an error processing your request."