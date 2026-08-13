import os
import logging
import asyncio
from datetime import datetime
import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from info import ADMINS, LOG_CHANNEL, UPDATE_CHNL_LNK, GRP_LNK, OWNER_LNK
from database.ai_db import ai_db
from database.ia_filterdb import get_search_results, dreamxbotz_get_movies
from ai.ai_handler import (
    ai_provider,
    is_user_rate_limited,
    get_ott_info,
    get_spoiler_free_summary,
    get_similar_movies
)
from plugins.pmfilter import auto_filter

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# SCRATCH PATH for temp downloads
SCRATCH_DIR = os.path.join(os.getcwd(), "scratch")
if not os.path.exists(SCRATCH_DIR):
    os.makedirs(SCRATCH_DIR)

# ----------------------------------------------------
# Latest OTT Release Browser Handler
# ----------------------------------------------------
@Client.on_message(filters.command("latest") | filters.regex(r"(?i)^latest\s+movies"))
async def latest_ott_browser(client: Client, message: Message):
    # Log analytics
    await ai_db.log_event("browser_open", message.from_user.id, "latest")
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Trending", callback_data="latest#Trending")
        ],
        [
            InlineKeyboardButton("📅 Today", callback_data="latest#Today"),
            InlineKeyboardButton("📆 Yesterday", callback_data="latest#Yesterday")
        ],
        [
            InlineKeyboardButton("📅 Last Week", callback_data="latest#Last Week"),
            InlineKeyboardButton("📅 This Month", callback_data="latest#This Month")
        ],
        [
            InlineKeyboardButton("📺 Netflix", callback_data="latest#Netflix"),
            InlineKeyboardButton("🎥 Prime Video", callback_data="latest#Prime Video")
        ],
        [
            InlineKeyboardButton("🍿 JioHotstar", callback_data="latest#JioHotstar")
        ],
        [
            InlineKeyboardButton("🌍 Malayalam", callback_data="latest#Malayalam"),
            InlineKeyboardButton("🇮🇳 Hindi", callback_data="latest#Hindi")
        ],
        [
            InlineKeyboardButton("🇹🇦 Tamil", callback_data="latest#Tamil"),
            InlineKeyboardButton("🇹🇪 Telugu", callback_data="latest#Telugu")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ]
    ])
    
    await message.reply_text(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 <b>FilmFox AI</b>\n"
        "Your Smart Movie Assistant\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select a category or platform to browse the newest OTT releases:",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r"^latest#"))
async def latest_category_callback(client: Client, query: CallbackQuery):
    category = query.data.split("#")[1]
    await query.answer(f"Fetching latest for {category}...")
    
    # 24h cached request for titles list via Gemini to make it fast
    cache_key = f"latest_titles_{category.lower().replace(' ', '_')}"
    titles = await ai_db.get_cache(cache_key)
    
    if not titles:
        if not ai_provider.enabled:
            return await query.message.edit_text("<b>AI Service is currently offline. Please try again later.</b>")
            
        current_year = datetime.now().year
        prompt = (
            f"List exactly 8 popular real movies/shows released recently on OTT under the category or platform '{category}' (Year: {current_year}). "
            "Return only their names as a comma-separated list. Do not include release dates or numbering. "
            "Example: Premalu, Aavesham, Manjummel Boys"
        )
        response = await ai_provider.chat(prompt)
        titles = [t.strip() for t in response.split(",") if t.strip()]
        if titles:
            await ai_db.set_cache(cache_key, titles)
            
    if not titles:
        return await query.message.edit_text("<b>No releases found in this category.</b>")
        
    buttons = []
    for title in titles:
        trunc_title = title[:45]
        buttons.append([InlineKeyboardButton(f"🎬 {title}", callback_data=f"lsearch#{trunc_title}")])
        
    buttons.append([InlineKeyboardButton("🔙 Back to Browser", callback_data="back_latest")])
    keyboard = InlineKeyboardMarkup(buttons)
    
    await query.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>Latest releases for: {category}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        "Click a movie name below to check files or request it:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Powered by FilmFox AI\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r"^back_latest$"))
async def back_latest(client: Client, query: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Trending", callback_data="latest#Trending")
        ],
        [
            InlineKeyboardButton("📅 Today", callback_data="latest#Today"),
            InlineKeyboardButton("📆 Yesterday", callback_data="latest#Yesterday")
        ],
        [
            InlineKeyboardButton("📅 Last Week", callback_data="latest#Last Week"),
            InlineKeyboardButton("📅 This Month", callback_data="latest#This Month")
        ],
        [
            InlineKeyboardButton("📺 Netflix", callback_data="latest#Netflix"),
            InlineKeyboardButton("🎥 Prime Video", callback_data="latest#Prime Video")
        ],
        [
            InlineKeyboardButton("🍿 JioHotstar", callback_data="latest#JioHotstar")
        ],
        [
            InlineKeyboardButton("🌍 Malayalam", callback_data="latest#Malayalam"),
            InlineKeyboardButton("🇮🇳 Hindi", callback_data="latest#Hindi")
        ],
        [
            InlineKeyboardButton("🇹🇦 Tamil", callback_data="latest#Tamil"),
            InlineKeyboardButton("🇹🇪 Telugu", callback_data="latest#Telugu")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ]
    ])
    await query.message.edit_text(
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎬 <b>FilmFox AI</b>\n"
        "Your Smart Movie Assistant\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select a category or platform to browse the newest OTT releases:",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r"^lsearch#"))
async def latest_search_callback(client: Client, query: CallbackQuery):
    import time
    start_time = time.time()
    movie_title = query.data.split("#")[1]
    chat_id = query.message.chat.id
    
    # 1. Pipeline Check: MongoDB search
    files, _, _ = await get_search_results(chat_id, movie_title, max_results=10)
    
    if files:
        await query.answer()
        # Redirect query message text to trigger auto_filter layout
        fake_msg = query.message
        fake_msg.text = movie_title
        fake_msg.from_user = query.from_user
        # Trigger direct AutoFilter search display
        await query.message.delete()
        await auto_filter(client, fake_msg)
        return
        
    # 2. OTT metadata search with temporary loading message
    await query.message.edit_text("🤖 <b>FilmFox AI is searching...</b>", parse_mode=enums.ParseMode.HTML)
    
    from ai.ai_handler import get_premium_movie_details, format_premium_reply
    from urllib.parse import quote_plus
    details = await get_premium_movie_details(movie_title)
    details["elapsed"] = time.time() - start_time
    text = format_premium_reply(details)
    
    # Premium Inline Buttons
    buttons = []
    buttons.append([
        InlineKeyboardButton("📩 Request Movie", callback_data=f"req_movie#{movie_title}"),
        InlineKeyboardButton("🔔 Notify Me", callback_data=f"req_movie#{movie_title}")
    ])
    
    if details.get("similar"):
        buttons.append([
            InlineKeyboardButton("❤️ Similar", callback_data=f"similar_info#{movie_title[:40]}"),
            InlineKeyboardButton("📺 OTT Info", callback_data=f"ott_info#{movie_title[:40]}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("📺 OTT Info", callback_data=f"ott_info#{movie_title[:40]}")
        ])
        
    buttons.append([
        InlineKeyboardButton("🎞 Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(movie_title)}+trailer"),
        InlineKeyboardButton("❌ Close", callback_data="close_data")
    ])
    keyboard = InlineKeyboardMarkup(buttons)
    
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

# ----------------------------------------------------
# Request Movie Notification
# ----------------------------------------------------
@Client.on_callback_query(filters.regex(r"^req_movie#"))
async def request_movie_callback(client: Client, query: CallbackQuery):
    movie_title = query.data.split("#")[1]
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    username = query.from_user.username
    
    # Save to movie_requests DB collection
    await ai_db.add_request(movie_title, user_id, chat_id, username)
    await ai_db.log_event("movie_request", user_id, movie_title)
    
    # Send Request to Admin Channel or Log Channel
    kolkata_tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(kolkata_tz)
    date_str = now.strftime("%d %B %Y")
    time_str = now.strftime("%I:%M %p")
    
    admin_log_msg = (
        f"<b>📩 NEW MOVIE REQUEST</b>\n\n"
        f"🎬 <b>Movie Name:</b> <code>{movie_title}</code>\n"
        f"👤 <b>Requested by:</b> {query.from_user.mention}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"📅 <b>Date:</b> {date_str}\n"
        f"⏰ <b>Time:</b> {time_str}"
    )
    
    try:
        await client.send_message(chat_id=LOG_CHANNEL, text=admin_log_msg, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error("Failed to send request log to LOG_CHANNEL: %s", e)
        
    await query.answer("✅ Your request has been sent successfully.", show_alert=True)
    await query.message.delete()

# ----------------------------------------------------
# Trending Lists `/trending`
# ----------------------------------------------------
@Client.on_message(filters.command("trending"))
async def trending_menu(client: Client, message: Message):
    await ai_db.log_event("menu_open", message.from_user.id, "trending")
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Today's Searches", callback_data="trend#today"),
            InlineKeyboardButton("📩 Most Requested", callback_data="trend#requested")
        ],
        [
            InlineKeyboardButton("🍿 Most Watched", callback_data="trend#watched"),
            InlineKeyboardButton("🆕 Recently Added", callback_data="trend#added")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ]
    ])
    await message.reply_text(
        "<b>🔥 Tʀᴇɴᴅɪɴɢ & Rᴇᴄᴇɴᴛ Sᴇᴄᴛɪᴏɴs 🎬</b>\n\n"
        "Explore the top searches, downloads, requests, and latest movies:",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@Client.on_callback_query(filters.regex(r"^trend#"))
async def trending_tabs_callback(client: Client, query: CallbackQuery):
    tab = query.data.split("#")[1]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Trending", callback_data="back_trending")]
    ])
    
    if tab == "today":
        # Get last 24h trending keywords
        from database.config_db import mdb
        titles = await mdb.get_top_messages(limit=10)
        if not titles:
            return await query.message.edit_text("<b>No searches logged today.</b>", reply_markup=keyboard)
            
        list_str = "\n".join([f"✨ <code>{t}</code>" for t in titles])
        await query.message.edit_text(f"<b>🔥 Top searches in the last 24 hours:</b>\n\n{list_str}", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        
    elif tab == "requested":
        summary = await ai_db.get_analytics_summary()
        reqs = summary.get("most_requested", [])
        if not reqs:
            return await query.message.edit_text("<b>No movie requests registered yet.</b>", reply_markup=keyboard)
            
        list_str = "\n".join([f"📌 <code>{r['title']}</code> - {r['count']} requests" for r in reqs])
        await query.message.edit_text(f"<b>📩 Most requested movies:</b>\n\n{list_str}", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        
    elif tab == "watched":
        summary = await ai_db.get_analytics_summary()
        watched = summary.get("most_watched", [])
        if not watched:
            return await query.message.edit_text("<b>No download logs found yet.</b>", reply_markup=keyboard)
            
        list_str = "\n".join([f"🍿 <code>{w['title']}</code> - {w['count']} downloads" for w in watched])
        await query.message.edit_text(f"<b>🍿 Most watched movies:</b>\n\n{list_str}", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        
    elif tab == "added":
        titles = await dreamxbotz_get_movies(limit=10)
        if not titles:
            return await query.message.edit_text("<b>No files in database.</b>", reply_markup=keyboard)
            
        list_str = "\n".join([f"🎬 <code>{t}</code>" for t in titles])
        await query.message.edit_text(f"<b>🆕 Recently added movies:</b>\n\n{list_str}", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex(r"^back_trending$"))
async def back_trending(client: Client, query: CallbackQuery):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 Today's Searches", callback_data="trend#today"),
            InlineKeyboardButton("📩 Most Requested", callback_data="trend#requested")
        ],
        [
            InlineKeyboardButton("🍿 Most Watched", callback_data="trend#watched"),
            InlineKeyboardButton("🆕 Recently Added", callback_data="trend#added")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="close_data")
        ]
    ])
    await query.message.edit_text(
        "<b>🔥 Tʀᴇɴᴅɪɴɢ & Rᴇᴄᴇɴᴛ Sᴇᴄᴛɪᴏɴs 🎬</b>\n\n"
        "Explore the top searches, downloads, requests, and latest movies:",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

# ----------------------------------------------------
# Admin Analytics Dashboard `/analytics` or `/dashboard`
# ----------------------------------------------------
@Client.on_message(filters.command(["analytics", "dashboard"]) & filters.user(ADMINS))
async def admin_dashboard(client: Client, message: Message):
    status_msg = await message.reply_text("<b>Calculating dashboard statistics... ⏳</b>")
    summary = await ai_db.get_analytics_summary()
    
    req_str = "\n".join([f"• {r['title']} ({r['count']} reqs)" for r in summary['most_requested']]) or "• None"
    wat_str = "\n".join([f"• {w['title']} ({w['count']} views)" for w in summary['most_watched']]) or "• None"
    lang_str = "\n".join([f"• {l['language']} ({l['count']} hits)" for l in summary['top_languages']]) or "• None"
    genre_str = "\n".join([f"• {g['genre']} ({g['count']} hits)" for g in summary['top_genres']]) or "• None"
    fail_str = "\n".join([f"• {f}" for f in summary['failed_searches']]) or "• None"
    
    dashboard_text = (
        f"<b>📊 Bot Analytics Dashboard (24h)</b>\n\n"
        f"📈 <b>Daily Searches:</b> {summary['daily_searches_success']} ✅ / {summary['daily_searches_fail']} ❌\n"
        f"📥 <b>Daily Downloads:</b> {summary['daily_downloads']}\n"
        f"👥 <b>Active Users:</b> {summary['active_users_24h']}\n\n"
        f"<b>📩 Most Requested Movies:</b>\n{req_str}\n\n"
        f"<b>🍿 Most Watched Movies:</b>\n{wat_str}\n\n"
        f"<b>🗣️ Top Languages:</b>\n{lang_str}\n\n"
        f"<b>🎭 Top Genres:</b>\n{genre_str}\n\n"
        f"<b>🔍 Recent Failed Searches:</b>\n{fail_str}"
    )
    
    await status_msg.edit_text(dashboard_text, parse_mode=enums.ParseMode.HTML)

# ----------------------------------------------------
# Voice Search Handler (`filters.voice` or `filters.audio`)
# ----------------------------------------------------
@Client.on_message((filters.private | filters.group) & (filters.voice | filters.audio))
async def voice_search_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return
        
    # Rate limiter check for AI operations
    if is_user_rate_limited(user_id):
        return await message.reply_text("<b>⚠️ Rate Limit Exceeded:</b> You can perform up to 15 AI requests per hour. Please type your search text manually.")
        
    import time
    start_time = time.time()
    status_msg = await message.reply_text("🤖 <b>FilmFox AI is searching...</b>")
    
    try:
        # Download voice note to scratch directory
        local_path = await message.download(file_name=os.path.join(SCRATCH_DIR, f"voice_{user_id}_{message.id}.ogg"))
        
        # Log analytics
        await ai_db.log_event("voice_search_request", user_id, f"voice_msg_{message.id}")
        
        # Transcribe
        transcription = await ai_provider.transcribe_audio(local_path)
        
        # Clean file
        try:
            os.remove(local_path)
        except:
            pass
            
        if not transcription:
            return await status_msg.edit_text("<b>❌ Transcribe failed. Please try speaking clearly or type movie search name.</b>")
        
        # Search the pipeline by overriding message text and calling auto_filter
        message.start_time = start_time
        message.ai_confidence = "95%"
        message.text = transcription
        await status_msg.delete()
        await auto_filter(client, message)
        
    except Exception as e:
        logger.error("Error in voice search handler: %s", e)
        await status_msg.edit_text("<b>❌ An error occurred during voice search transcription.</b>")

# ----------------------------------------------------
# Screenshot Visual Search Handler (`filters.photo`)
# ----------------------------------------------------
@Client.on_message(filters.private & filters.photo)
async def screenshot_search_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # Rate limiter check for AI operations
    if is_user_rate_limited(user_id):
        return await message.reply_text("<b>⚠️ Rate Limit Exceeded:</b> You can perform up to 15 AI requests per hour. Please type your search text manually.")
        
    import time
    start_time = time.time()
    status_msg = await message.reply_text("🤖 <b>FilmFox AI is searching...</b>")
    
    try:
        # Download photo to scratch directory
        local_path = await message.download(file_name=os.path.join(SCRATCH_DIR, f"photo_{user_id}_{message.id}.jpg"))
        
        # Log analytics
        await ai_db.log_event("screenshot_search_request", user_id, f"photo_msg_{message.id}")
        
        # Identify image
        movie_title = await ai_provider.identify_image(local_path)
        
        # Clean file
        try:
            os.remove(local_path)
        except:
            pass
            
        if not movie_title:
            return await status_msg.edit_text("<b>❌ Could not identify the movie in this image. Make sure it's a clear screenshot or poster.</b>")
            
        # Search database
        message.start_time = start_time
        message.ai_confidence = "92%"
        message.text = movie_title
        await status_msg.delete()
        await auto_filter(client, message)
        
    except Exception as e:
        logger.error("Error in screenshot search handler: %s", e)
        await status_msg.edit_text("<b>❌ An error occurred during image search analysis.</b>")

# ----------------------------------------------------
# AI Chat Assistant Command `/ai` or `/ask`
# ----------------------------------------------------
@Client.on_message(filters.command(["ai", "ask"]))
async def ai_chat_assistant(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return
        
    # Rate limiter check for AI operations
    if is_user_rate_limited(user_id):
        return await message.reply_text("<b>⚠️ Rate Limit Exceeded:</b> You can perform up to 15 AI requests per hour.")
        
    if len(message.command) < 2:
        # Send animated AI/Robot Sticker
        sticker_msg = None
        try:
            sticker_msg = await message.reply_sticker("CAACAgIAAxkBAAE9-dpl4-8zL9L0Q4n-x7-nL1l2s_E_AAI1AAO9vJ8_vXzL")
        except Exception:
            pass
            
        if sticker_msg:
            await asyncio.sleep(1.5)
            try:
                await sticker_msg.delete()
            except Exception:
                pass

        intro_text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 <b>FɪʟᴍFᴏx AI Mᴏᴅᴇ ɪs Aᴄᴛɪᴠᴇ !</b> 🎬\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "👋 <b>Welcome to FilmFox Smart AI Movie Assistant!</b>\n\n"
            "💡 <b>How Does <code>/ai</code> Work?</b>\n"
            "The AI feature activates <b>only</b> when you type your question or query directly along with the <code>/ai</code> command!\n\n"
            "✨ <b>What I Can Do For You:</b>\n"
            "• 🍿 <b>Movie Recommendations:</b> Ask for top movies in any genre or language.\n"
            "  <i>Example: <code>/ai Top 5 thriller Malayalam movies</code></i>\n\n"
            "• 📺 <b>OTT Release Dates & Platforms:</b> Get exact OTT streaming info.\n"
            "  <i>Example: <code>/ai RRR OTT release date</code></i>\n\n"
            "• 🎬 <b>Plot & Scene Identifier:</b> Describe any scene or story plot to guess the movie.\n"
            "  <i>Example: <code>/ai A group of friends visit Guna cave</code></i>\n\n"
            "• 📊 <b>Movie Comparisons:</b> Compare storyline, ratings, and reviews.\n"
            "  <i>Example: <code>/ai Compare Interstellar and Inception</code></i>\n\n"
            "• 🎙️ <b>Voice & Image Search:</b> Send voice messages or movie posters directly!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>How To Use:</b>\n"
            "Type <code>/ai [your question here]</code> to get instant AI answers!\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍿 Demo: Movie Suggestions", callback_data="ai_demo#suggest"),
                InlineKeyboardButton("📺 Demo: OTT Release", callback_data="ai_demo#ott")
            ],
            [
                InlineKeyboardButton("📩 Contact Admin", url=OWNER_LNK),
                InlineKeyboardButton("❌ Close", callback_data="close_data")
            ]
        ])
        return await message.reply_text(intro_text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        
    prompt = message.text.split(None, 1)[1]
    import time
    start_time = time.time()
    
    if "ott" in prompt.lower():
        status_msg = await message.reply_text("🤖 <b>FilmFox AI is checking OTT status...</b>")
        clean_movie = re.sub(r'(?i)\b(ott|release|date|when|is|coming|on|out|status)\b', '', prompt).strip()
        if not clean_movie:
            clean_movie = prompt
        text, reply_markup = await build_ott_response(clean_movie, message.chat.id)
        return await status_msg.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

    status_msg = await message.reply_text("🤖 <b>FilmFox AI is thinking...</b>")
    
    try:
        await ai_db.log_event("ai_chat", user_id, prompt)
        response = await ai_provider.chat(prompt)
        elapsed = time.time() - start_time
        
        premium_chat_response = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>FilmFox AI Chat</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎯 AI Confidence : High\n\n"
            f"{response}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Powered by FilmFox AI\n"
            f"⚡ Response Time: {elapsed:.2f} sec\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        await status_msg.edit_text(premium_chat_response, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error("Error in AI chat assistant command: %s", e)
        await status_msg.edit_text("<b>❌ An error occurred while communicating with the AI.</b>")

# ----------------------------------------------------
# Guess the Movie Command `/guess`
# ----------------------------------------------------
@Client.on_message(filters.command("guess"))
async def guess_movie_command(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return
        
    # Rate limiter check for AI operations
    if is_user_rate_limited(user_id):
        return await message.reply_text("<b>⚠️ Rate Limit Exceeded:</b> You can perform up to 15 AI requests per hour.")
        
    if len(message.command) < 2:
        return await message.reply_text("<b>Usage:</b> `/guess <scene or plot description>`\n\nExample: `/guess Hero has a dog. Revenge story.`")
        
    description = message.text.split(None, 1)[1]
    import time
    start_time = time.time()
    status_msg = await message.reply_text("🤖 <b>FilmFox AI is searching...</b>")
    
    try:
        await ai_db.log_event("guess_movie_request", user_id, description)
        guess = await ai_provider.guess_movie(description)
        
        if not guess:
            return await status_msg.edit_text("<b>❌ Sorry, AI couldn't guess the movie from this description. Try giving more details.</b>")
            
        # Search database
        message.start_time = start_time
        message.ai_confidence = "88%"
        message.text = guess
        await status_msg.delete()
        await auto_filter(client, message)
        
    except Exception as e:
        logger.error("Error in guess movie command: %s", e)
        await status_msg.edit_text("<b>❌ An error occurred while communicating with the AI.</b>")

# ----------------------------------------------------
# Similar & OTT Info Callbacks
# ----------------------------------------------------
@Client.on_callback_query(filters.regex(r"^similar_info#"))
async def similar_info_callback(client: Client, query: CallbackQuery):
    movie_title = query.data.split("#")[1]
    await query.answer("Fetching similar movies...")
    from ai.ai_handler import get_similar_movies
    similar = await get_similar_movies(movie_title)
    if not similar:
        return await query.answer("No similar movies found.", show_alert=True)
        
    buttons = []
    for s in similar[:5]:
        buttons.append([InlineKeyboardButton(f"🎬 {s}", callback_data=f"lsearch#{s[:45]}")])
    buttons.append([InlineKeyboardButton("🔙 Back to Movie", callback_data=f"lsearch#{movie_title}")])
    
    await query.message.edit_text(
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 <b>Similar Movies Suggestions</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Here are movies similar to <b>{movie_title}</b>:\n\n"
        f"Click a movie name below to search or request:\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Powered by FilmFox AI\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML
    )

async def build_ott_response(movie_title: str, chat_id: int):
    from ai.ai_handler import get_ott_info
    from database.ia_filterdb import get_search_results

    ott = await get_ott_info(movie_title)

    display_title = ott.get("movie_title") or movie_title
    released = ott.get("released", False)
    release_date = ott.get("release_date") or "TBA / Not Announced"
    platforms_list = ott.get("platforms", [])
    platforms_str = ", ".join(platforms_list) if platforms_list else "TBA / Not Announced"

    # Check if files exist in our MongoDB database
    try:
        files, _, _ = await get_search_results(chat_id, display_title, max_results=1)
        has_files_in_db = bool(files)
    except Exception as e:
        logger.warning(f"DB search check skipped in build_ott_response: {e}")
        has_files_in_db = False

    buttons = []

    if not released:
        status_text = "⏳ <b>Not Yet Released on OTT</b>"
        note = f"This movie has not been released on OTT yet. Official/expected release date: <b>{release_date}</b>."
        buttons.append([
            InlineKeyboardButton("📩 Request Movie", callback_data=f"req_movie#{display_title[:40]}"),
            InlineKeyboardButton("📩 Contact Admin", url=OWNER_LNK)
        ])
    else:
        status_text = "✅ <b>Released on OTT!</b>"
        if has_files_in_db:
            note = "🎉 Good news! This movie is released and available in our bot database. Click below to get files!"
            buttons.append([
                InlineKeyboardButton("🔍 Search Files", callback_data=f"lsearch#{display_title[:40]}")
            ])
        else:
            note = "⚠️ <b>Note:</b> This movie is released on OTT, but the files have <b>not been added</b> to our bot database yet by the admin."
            buttons.append([
                InlineKeyboardButton("📩 Contact Admin", url=OWNER_LNK),
                InlineKeyboardButton("📩 Request Movie", callback_data=f"req_movie#{display_title[:40]}")
            ])

    buttons.append([
        InlineKeyboardButton("🔙 Back to Movie", callback_data=f"lsearch#{display_title[:40]}"),
        InlineKeyboardButton("❌ Close", callback_data="close_data")
    ])

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📺 <b>FilmFox AI OTT Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎬 <b>Movie:</b> <code>{display_title}</code>\n"
        f"📌 <b>Status:</b> {status_text}\n"
        f"🖥️ <b>Streaming Platform:</b> {platforms_str}\n"
        f"📅 <b>OTT Release Date:</b> {release_date}\n\n"
        f"ℹ️ {note}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Powered by FilmFox AI\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    return text, InlineKeyboardMarkup(buttons)

@Client.on_message(filters.command(["ott", "ottinfo"]))
async def ott_command_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not user_id:
        return
    if is_user_rate_limited(user_id):
        return await message.reply_text("<b>⚠️ Rate Limit Exceeded:</b> Please wait before making more AI/OTT requests.")

    if len(message.command) < 2:
        return await message.reply_text("<b>Usage:</b> `/ott <movie name>`\n\nExample: `/ott RRR` or `/ott Manjummel Boys`")

    movie_title = message.text.split(None, 1)[1]
    status_msg = await message.reply_text("🤖 <b>Fetching OTT release status...</b>")
    try:
        text, reply_markup = await build_ott_response(movie_title, message.chat.id)
        await status_msg.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error("Error in /ott command handler: %s", e)
        await status_msg.edit_text("<b>❌ Error fetching OTT release details.</b>")

@Client.on_callback_query(filters.regex(r"^ott_info#"))
async def ott_info_callback(client: Client, query: CallbackQuery):
    movie_title = query.data.split("#")[1]
    await query.answer("Fetching OTT release details...")
    text, reply_markup = await build_ott_response(movie_title, query.message.chat.id)
    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query(filters.regex(r"^ai_demo#"))
async def ai_demo_callback(client: Client, query: CallbackQuery):
    demo_type = query.data.split("#")[1]
    chat_id = query.message.chat.id
    
    if demo_type == "suggest":
        await query.answer("Running demo: Top Malayalam movies of 2024...")
        await query.message.edit_text("🤖 <b>FilmFox AI is running demo query...</b>", parse_mode=enums.ParseMode.HTML)
        response = await ai_provider.chat("Suggest top 3 Malayalam movies of 2024 with genre and short description.")
        text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 <b>FilmFox AI Demo Result</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{response}\n\n"
            f"💡 <i>Tip: You can ask your own question anytime using <code>/ai [your question]</code>!</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 Demo: OTT Release", callback_data="ai_demo#ott")],
            [InlineKeyboardButton("📩 Contact Admin", url=OWNER_LNK), InlineKeyboardButton("❌ Close", callback_data="close_data")]
        ])
        await query.message.edit_text(text, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)

    elif demo_type == "ott":
        await query.answer("Running demo: OTT status for Manjummel Boys...")
        await query.message.edit_text("🤖 <b>FilmFox AI is checking OTT status...</b>", parse_mode=enums.ParseMode.HTML)
        text, reply_markup = await build_ott_response("Manjummel Boys", chat_id)
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
