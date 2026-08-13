import datetime
import time
import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from pyrogram.errors import FloodWait
from database.users_chats_db import db
from info import ADMINS
from utils import users_broadcast, groups_broadcast, temp, get_readable_time, clear_junk, junk_group
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^broadcast_cancel'))
async def broadcast_cancel(bot, query):
    _, target = query.data.split("#", 1)
    if target == 'users':
        temp.B_USERS_CANCEL = True
        await query.message.edit("🛑 Cancelling users broadcasting...")
    elif target == 'groups':
        temp.B_GROUPS_CANCEL = True
        await query.message.edit("🛑 Cancelling groups broadcasting...")

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_users(bot, message):
    if lock.locked():
        return await message.reply("⚠️ Another broadcast is currently in progress. Please wait.")
        
    ask = await message.reply(
        "<b>Do you want to pin this message for users?</b>",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    
    try:
        user_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
    except asyncio.TimeoutError:
        await ask.delete()
        return await message.reply("❌ Timed out. Broadcast cancelled.")
        
    await ask.delete()
    if user_response.text not in ("Yes", "No"):
        return await message.reply("❌ Invalid input. Broadcast cancelled.")

    is_pin = user_response.text == "Yes"
    b_msg = message.reply_to_message
    
    # എല്ലാവരെയും ഒരൊറ്റ ഡാറ്റാബേസിൽ നിന്നും എടുക്കുന്നു
    users = [user async for user in await db.get_all_users()]
    total_users = len(users)
    
    status_msg = await message.reply_text("📤 <b>Broadcasting your message...</b>")
    
    success = blocked = deleted = failed = 0
    start_time = time.time()
    cancelled = False

    async def send(user):
        try:
            _, result = await users_broadcast(int(user["id"]), b_msg, is_pin)
            return result
        except Exception:
            logging.exception(f"Error sending broadcast to {user['id']}")
            return "Error"

    async with lock:
        for i in range(0, total_users, 100):
            if temp.B_USERS_CANCEL:
                temp.B_USERS_CANCEL = False
                cancelled = True
                break
                
            batch = users[i:i + 100]
            results = await asyncio.gather(*[send(user) for user in batch])

            for res in results:
                if res == "Success":
                    success += 1
                elif res == "Blocked":
                    blocked += 1
                elif res == "Deleted":
                    deleted += 1
                elif res == "Error":
                    failed += 1

            done = i + len(batch)
            elapsed = get_readable_time(time.time() - start_time)
            
            await status_msg.edit(
                f"📣 <b>Broadcast Progress:</b>\n\n"
                f"👥 Total: <code>{total_users}</code>\n"
                f"✅ Done: <code>{done}</code>\n"
                f"📬 Success: <code>{success}</code>\n"
                f"⛔ Blocked: <code>{blocked}</code>\n"
                f"🗑️ Deleted: <code>{deleted}</code>\n"
                f"⏱️ Time: {elapsed}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#users")]
                ])
            )
            await asyncio.sleep(0.1)
            
    elapsed = get_readable_time(time.time() - start_time)
    final_status = (
        f"{'❌ <b>Broadcast Cancelled.</b>' if cancelled else '✅ <b>Broadcast Completed.</b>'}\n\n"
        f"🕒 Time: {elapsed}\n"
        f"👥 Total: <code>{total_users}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"⛔ Blocked: <code>{blocked}</code>\n"
        f"🗑️ Deleted: <code>{deleted}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    await status_msg.edit(final_status)


@Client.on_message(filters.command("grp_broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast_group(bot, message):
    ask = await message.reply(
        "<b>Do you want to pin this message in groups?</b>",
        reply_markup=ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    )
    
    try:
        user_response = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id, timeout=60)
    except asyncio.TimeoutError:
        await ask.delete()
        return await message.reply("❌ Timed out. Broadcast cancelled.")
        
    await ask.delete()
    if user_response.text not in ("Yes", "No"):
        return await message.reply("❌ Invalid input. Broadcast cancelled.")

    is_pin = user_response.text == "Yes"
    b_msg = message.reply_to_message
    
    chats = await db.get_all_chats()
    total_chats = await db.total_chat_count()
    status_msg = await message.reply_text("📤 <b>Broadcasting your message to groups...</b>")
    
    start_time = time.time()
    done = success = failed = 0
    cancelled = False

    async with lock:
        async for chat in chats:
            if temp.B_GROUPS_CANCEL:
                temp.B_GROUPS_CANCEL = False
                cancelled = True
                break
                
            try:
                sts = await groups_broadcast(int(chat['id']), b_msg, is_pin)
            except Exception:
                logging.exception(f"Error broadcasting to group {chat['id']}")
                sts = 'Error'
                
            if sts == "Success":
                success += 1
            else:
                failed += 1
                
            done += 1
            if done % 10 == 0:
                btn = [[InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel#groups")]]
                await status_msg.edit(
                    f"📣 <b>Group Broadcast Progress:</b>\n\n"
                    f"👥 Total Groups: <code>{total_chats}</code>\n"
                    f"✅ Completed: <code>{done} / {total_chats}</code>\n"
                    f"📬 Success: <code>{success}</code>\n"
                    f"❌ Failed: <code>{failed}</code>",
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                
    time_taken = get_readable_time(time.time() - start_time)
    final_text = (
        f"{'❌ <b>Groups broadcast cancelled!</b>' if cancelled else '✅ <b>Group broadcast completed.</b>'}\n"
        f"⏱️ Completed in {time_taken}\n\n"
        f"👥 Total Groups: <code>{total_chats}</code>\n"
        f"✅ Completed: <code>{done} / {total_chats}</code>\n"
        f"📬 Success: <code>{success}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
    
    try:
        await status_msg.edit(final_text)
    except MessageTooLong:
        with open("reason.txt", "w+") as outfile:
            outfile.write(str(failed))
        await message.reply_document("reason.txt", caption=final_text)
        os.remove("reason.txt")

@Client.on_message(filters.command("clear_junk") & filters.user(ADMINS))
async def remove_junkuser_db(bot, message):
    users = await db.get_all_users()
    b_msg = message 
    sts = await message.reply_text('⚙️ Process initiated. Please wait...')   
    start_time = time.time()
    total_users = await db.total_users_count()
    
    blocked = deleted = failed = done = 0
    
    async for user in users:
        pti, sh = await clear_junk(int(user['id']), b_msg)
        if not pti:
            if sh == "Blocked":
                blocked += 1
            elif sh == "Deleted":
                deleted += 1
            elif sh == "Error":
                failed += 1
        done += 1
        
        if done % 50 == 0:
            await sts.edit(
                f"🔄 In Progress:\n\nTotal Users: {total_users}\n"
                f"Completed: {done} / {total_users}\nBlocked: {blocked}\nDeleted: {deleted}"
            )   
            
    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.delete()
    await bot.send_message(
        message.chat.id, 
        f"✅ Task Completed in {time_taken} seconds.\n\n"
        f"Total Users: {total_users}\nCompleted: {done} / {total_users}\n"
        f"Blocked: {blocked}\nDeleted: {deleted}"
    )

@Client.on_message(filters.command(["junk_group", "clear_junk_group"]) & filters.user(ADMINS))
async def junk_clear_group(bot, message):
    groups = await db.get_all_chats()
    if not groups:
        grp = await message.reply_text("❌ No groups found in the database.")
        await asyncio.sleep(60)
        await grp.delete()
        return
        
    b_msg = message
    sts = await message.reply_text('⚙️ Scanning groups...')
    start_time = time.time()
    total_groups = await db.total_chat_count()
    
    done = deleted = 0
    failed = ""
    
    async for group in groups:
        pti, sh, ex = await junk_group(int(group['id']), b_msg)        
        if not pti:
            if sh == "deleted":
                deleted += 1 
                failed += str(ex) + "\n"
                try:
                    await bot.leave_chat(int(group['id']))
                except Exception as e:
                    logging.error(f"Failed to leave chat {group['id']}: {e}")  
        done += 1
        
        if done % 50 == 0:
            await sts.edit(
                f"🔄 In Progress:\n\nTotal Groups: {total_groups}\n"
                f"Completed: {done} / {total_groups}\nDeleted: {deleted}"
            )   
            
    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.delete()
    
    final_text = (
        f"✅ Task Completed in {time_taken} seconds.\n\n"
        f"Total Groups: {total_groups}\nCompleted: {done} / {total_groups}\n"
        f"Deleted: {deleted}"
    )
    
    try:
        if failed:
            final_text += f"\n\nFailed Reasons:\n{failed[:500]}..." 
        await bot.send_message(message.chat.id, final_text)    
    except MessageTooLong:
        with open('junk.txt', 'w+') as outfile:
            outfile.write(failed)
        await message.reply_document('junk.txt', caption=f"✅ Task Completed in {time_taken} seconds.\nTotal Groups: {total_groups}\nDeleted: {deleted}")
        os.remove("junk.txt")