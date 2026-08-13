from pyrogram import Client, filters
from pyrogram.types import Message
from database.ads_db import ads_db
from info import ADMINS
import uuid

@Client.on_message(filters.command("add_ad") & filters.user(ADMINS))
async def add_new_ad(client: Client, message: Message):
    """
    Command to add a new advertisement.
    Usage: Reply to any message (Text, Photo, or Video) with /add_ad [days]
    Example: /add_ad 30
    """
    if not message.reply_to_message:
        return await message.reply_text("⚠️ Please reply to a message (Text/Photo/Video) to add it as an Ad.")
    
    try:
        command_args = message.command
        if len(command_args) < 2:
            return await message.reply_text("⚠️ Please provide the duration in days. Example: `/add_ad 30`")
        
        days = int(command_args[1])
        if days <= 0:
            return await message.reply_text("⚠️ Days must be greater than 0.")
        
        replied_msg = message.reply_to_message
        
        # Generating a unique 8-character ID for the Ad
        ad_id = str(uuid.uuid4())[:8] 
        
        content = None
        msg_type = None
        
        # --- ഇവിടെയാണ് ക്യാപ്ഷൻ ഫോർമാറ്റോട് കൂടി എടുക്കുന്നത് ---
        caption = replied_msg.caption.html if replied_msg.caption else None

        # Determine the type of the ad message and extract content
        if replied_msg.photo:
            content = replied_msg.photo.file_id
            msg_type = "photo"
        elif replied_msg.video:
            content = replied_msg.video.file_id
            msg_type = "video"
        elif replied_msg.text:
            content = replied_msg.text.html if replied_msg.text else None
            msg_type = "text"
        else:
            return await message.reply_text("⚠️ Unsupported message format. Only Text, Photo, and Video are supported.")

        # Save to database (ക്യാപ്ഷൻ കൂടി ഡാറ്റാബേസ് ഫങ്ക്ഷനിലേക്ക് പാസ്സ് ചെയ്യുന്നു)
        await ads_db.add_ad(ad_id, content, msg_type, days, caption)
        
        success_msg = (
            f"✅ **Ad Successfully Added!**\n\n"
            f"**Ad ID:** `{ad_id}`\n"
            f"**Type:** {msg_type.capitalize()}\n"
            f"**Duration:** {days} days"
        )
        await message.reply_text(success_msg)
        
    except ValueError:
        await message.reply_text("⚠️ Invalid format. Days must be an integer.")
    except Exception as e:
        await message.reply_text(f"❌ An error occurred: {e}")


@Client.on_message(filters.command("ads") & filters.user(ADMINS))
async def list_active_ads(client: Client, message: Message):
    """
    Command to list all currently active advertisements in the database.
    Usage: /ads
    """
    ads = await ads_db.get_active_ads()
    if not ads:
        return await message.reply_text("ℹ️ There are no active ads currently.")
    
    text = "**📢 Active Advertisements:**\n\n"
    for ad in ads:
        expiry_date = ad['expiry'].strftime("%Y-%m-%d %H:%M:%S")
        text += f"**ID:** `{ad['ad_id']}`\n"
        text += f"**Type:** {ad['type'].capitalize()}\n"
        text += f"**Expires On:** {expiry_date}\n"
        text += "--------------------------\n"
        
    await message.reply_text(text)


@Client.on_message(filters.command("del_ad") & filters.user(ADMINS))
async def delete_existing_ad(client: Client, message: Message):
    """
    Command to delete a specific advertisement using its Ad ID.
    Usage: /del_ad [ad_id]
    """
    command_args = message.command
    if len(command_args) < 2:
        return await message.reply_text("⚠️ Please provide the Ad ID to delete. Example: `/del_ad a1b2c3d4`")
    
    ad_id = command_args[1]
    await ads_db.delete_ad(ad_id)
    await message.reply_text(f"✅ Ad with ID `{ad_id}` has been deleted from the database.")