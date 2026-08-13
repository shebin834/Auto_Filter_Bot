import shutil
import psutil
from pyrogram import Client, filters
from info import ADMINS
from database.users_chats_db import db
from database.ia_filterdb import Media

@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def get_stats(bot, message):
    sts = await message.reply("🔄 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛᴀᴛꜱ...")
    
    # Database Counts
    try:
        total_users = await db.total_users_count()
    except Exception:
        total_users = "Error"
        
    try:
        total_groups = await db.total_chat_count()
    except Exception:
        total_groups = "Error"
        
    try:
        total_files = await Media.collection.count_documents({})
    except Exception:
        total_files = "Error"
        
    # Server Storage Info (VPS)
    total, used, free = shutil.disk_usage("/")
    free_space = f"{free / (1024 ** 3):.2f} GB"
    used_space = f"{used / (1024 ** 3):.2f} GB"
    total_space = f"{total / (1024 ** 3):.2f} GB"
    
    # CPU & RAM Usage
    cpu_usage = psutil.cpu_percent(interval=0.5)
    ram_usage = psutil.virtual_memory().percent
    
    stats_text = (
        f"📊 **ꜱʏꜱᴛᴇᴍ & ʙᴏᴛ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ**\n\n"
        f"👥 **ᴜꜱᴇʀꜱ & ɢʀᴏᴜᴘꜱ:**\n"
        f" ├ 👤 ᴀʟʟ ᴜꜱᴇʀꜱ: `{total_users}`\n"
        f" └ 🏢 ᴀʟʟ ɢʀᴏᴜᴘꜱ: `{total_groups}`\n\n"
        f"📂 **ᴅᴀᴛᴀʙᴀꜱᴇ ɪɴꜰᴏ:**\n"
        f" └ 🗃️ ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ: `{total_files}`\n\n"
        f"💻 **ꜱᴇʀᴠᴇʀ ᴅᴇᴛᴀɪʟꜱ (VPS):**\n"
        f" ├ 💾 ᴛᴏᴛᴀʟ ꜱᴛᴏʀᴀɢᴇ: `{total_space}`\n"
        f" ├ 🟢 ꜰʀᴇᴇ ꜱᴛᴏʀᴀɢᴇ: `{free_space}`\n"
        f" ├ 🔴 ᴜꜱᴇᴅ ꜱᴛᴏʀᴀɢᴇ: `{used_space}`\n"
        f" ├ 🖥️ ᴄᴘᴜ ᴜꜱᴀɢᴇ: `{cpu_usage}%`\n"
        f" └ ⚙️ ʀᴀᴍ ᴜꜱᴀɢᴇ: `{ram_usage}%`\n\n"
        f"✅ **ᴅᴀᴛᴀʙᴀꜱᴇ ᴍᴏᴅᴇ:** `Single DB (Optimized)`"
    )
    
    await sts.edit(stats_text)