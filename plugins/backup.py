import os
import gzip
import pytz
import logging
import asyncio
from datetime import datetime
from bson.json_util import dumps
from pyrogram import Client, filters, enums
from pyrogram.types import Message

from info import LOG_CHANNEL, ADMINS, COLLECTION_NAME, DATABASE_NAME
from database.ia_filterdb import db as ia_db

logger = logging.getLogger(__name__)


def write_batch_to_gzip(gz_file, batch):
    lines = [dumps(doc) + '\n' for doc in batch]
    gz_file.write(''.join(lines))


async def generate_backup_file(file_path: str) -> int:
    total_docs = await ia_db[COLLECTION_NAME].count_documents({})
    loop = asyncio.get_running_loop()

    with gzip.open(file_path, 'wt', encoding='utf-8') as gz:
        batch = []
        async for doc in ia_db[COLLECTION_NAME].find({}):
            batch.append(doc)
            if len(batch) >= 5000:
                await loop.run_in_executor(None, write_batch_to_gzip, gz, batch)
                batch = []
                await asyncio.sleep(0.01)

        if batch:
            await loop.run_in_executor(None, write_batch_to_gzip, gz, batch)

    return total_docs


async def send_backup_to_log(client: Client, manual: bool = False, user_mention: str = None):
    os.makedirs("backups", exist_ok=True)
    ist_tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist_tz)
    date_str = now.strftime('%Y-%m-%d_%H-%M-%S')
    display_date = now.strftime('%Y-%m-%d %I:%M:%S %p')

    file_name = f"backup_{COLLECTION_NAME}_{date_str}.json.gz"
    file_path = os.path.join("backups", file_name)

    try:
        total_docs = await generate_backup_file(file_path)
        archive_size_bytes = os.path.getsize(file_path)
        archive_size_mb = f"{archive_size_bytes / (1024 * 1024):.2f}"

        backup_type = "MANUAL DATABASE BACKUP" if manual else "AUTOMATIC DAILY DATABASE BACKUP"

        caption = (
            f"📦 <b>{backup_type}</b>\n\n"
            f"📅 <b>Date:</b> {display_date}\n"
            f"🗂️ <b>Collection:</b> {COLLECTION_NAME}\n"
            f"📊 <b>Total Documents:</b> {total_docs:,}\n"
            f"💾 <b>Archive Size:</b> {archive_size_mb} MB\n\n"
            f"⚜️ <b>Powered by MalluTheater Bot Engine</b>"
        )
        if manual and user_mention:
            caption += f"\n👤 <b>Triggered By:</b> {user_mention}"

        await client.send_document(
            chat_id=LOG_CHANNEL,
            document=file_path,
            caption=caption,
            parse_mode=enums.ParseMode.HTML
        )
        logger.info(f"Database backup successfully sent to LOG_CHANNEL ({LOG_CHANNEL}).")
        return True, total_docs, archive_size_mb
    except Exception as e:
        logger.error(f"Failed to create/send database backup: {e}", exc_info=True)
        return False, 0, "0"
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


async def start_daily_backup_scheduler(client: Client):
    logger.info("Daily Database Backup Scheduler started.")
    await asyncio.sleep(10)
    while True:
        try:
            logger.info("Running scheduled daily database backup...")
            await send_backup_to_log(client, manual=False)
        except Exception as e:
            logger.error(f"Error in daily backup scheduler: {e}")

        # Wait 24 hours (86400 seconds) for next backup
        await asyncio.sleep(86400)


@Client.on_message(filters.command("backup") & filters.user(ADMINS))
async def manual_backup_handler(client: Client, message: Message):
    status_msg = await message.reply_text("⏳ <b>Generating database backup, please wait...</b>", parse_mode=enums.ParseMode.HTML)
    user_mention = message.from_user.mention if message.from_user else "Admin"
    success, total_docs, size_mb = await send_backup_to_log(
        client,
        manual=True,
        user_mention=user_mention
    )
    if success:
        await status_msg.edit_text(
            f"✅ <b>Database Backup Completed!</b>\n\n"
            f"📊 <b>Documents:</b> <code>{total_docs:,}</code>\n"
            f"💾 <b>Size:</b> <code>{size_mb} MB</code>\n"
            f"📤 Sent to Log Channel!",
            parse_mode=enums.ParseMode.HTML
        )
    else:
        await status_msg.edit_text("❌ <b>Failed to create database backup. Check logs for details.</b>", parse_mode=enums.ParseMode.HTML)
