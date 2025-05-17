import os
from datetime import datetime, timedelta
from collections import deque
from telegram import Bot, Update, ChatPermissions
from telegram.ext import Application, MessageHandler, CommandHandler, filters, CallbackContext
import threading
import time

# Token dari environment
TOKEN = '8130216387:AAGd8zq5WTQrtp6p05Ch2tXObvODA6ykVXw'
ADMIN_GROUP_ID = -1002369898305

# Daftar grup yang diizinkan
ALLOWED_GROUP_IDS = {
    -1002604965354,
    -1002422132097,
    -1002181377143,
    -1002391683524,
    -1002494436143
}

bot = Bot(token=TOKEN)

user_message_timestamps = {}
user_reported_status = {}

# Fungsi untuk menangani perintah /start
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Hai bot aktif, ini bot buat mendeteksi userbot di grup LPM HASTLE. Mau punya bot buat deteksi userbot? Bisa hubungi @Galantedump.")

# Deteksi interval konsisten
def check_bot(user_id, message_time):
    current_time = datetime.strptime(message_time, '%Y-%m-%d %H:%M:%S')

    if user_id not in user_message_timestamps:
        user_message_timestamps[user_id] = deque(maxlen=80)
    user_message_timestamps[user_id].append(current_time)

    if len(user_message_timestamps[user_id]) < 80:
        return False, 0

    intervals = [
        (user_message_timestamps[user_id][i] - user_message_timestamps[user_id][i - 1]).total_seconds()
        for i in range(1, len(user_message_timestamps[user_id]))
    ]

    avg_interval = sum(intervals) / len(intervals)

    for interval in intervals:
        if not (avg_interval - 10 <= interval <= avg_interval + 10):
            return False, avg_interval

    return True, avg_interval

# Lapor ke admin
async def report_to_admin(update: Update, avg_interval):
    user = update.message.from_user
    chat = update.message.chat
    user_id = user.id
    username = f"@{user.username}" if user.username else "(tidak ada)"
    full_name = f"{user.first_name} {user.last_name or ''}".strip()
    last_message = update.message

    try:
        text = (
            f"🚨 *Deteksi Userbot*\n\n"
            f"👤 *Nama:* {full_name}\n"
            f"🔗 *Username:* {username}\n"
            f"🆔 *User ID:* `{user_id}`\n"
        )

        if chat.username:
            msg_link = f"https://t.me/{chat.username}/{last_message.message_id}"
            text += f"📨 *Pesan:* [Klik untuk lihat]({msg_link})\n"

        text += (
            f"📊 *Jumlah Pesan:* 80\n"
            f"⏱️ *Rata-rata Interval:* {avg_interval:.2f} detik\n"
            f"⚠️ *Status:* Terindikasi userbot (interval waktu konsisten ±10 detik)\n"
            f"⚠️ *Status:* Sudah di-mute selama 1 bulan"
        )

        await bot.send_message(ADMIN_GROUP_ID, text, parse_mode='Markdown', disable_web_page_preview=True)

        if not chat.username:
            await bot.forward_message(ADMIN_GROUP_ID, chat.id, last_message.message_id)

    except Exception as e:
        print(f"Gagal kirim laporan: {e}")

# Mute pengguna selama 1 bulan
async def mute_user(update: Update):
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    until_date = datetime.now() + timedelta(days=30)

    try:
        permissions = ChatPermissions(can_send_messages=False)
        await bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date
        )
        print(f"Pengguna {user_id} telah dimute selama 1 bulan.")
    except Exception as e:
        print(f"Gagal mute pengguna: {e}")

# Proses pesan masuk
async def process_message(update: Update, context: CallbackContext):
    message = update.message
    chat_id = message.chat.id

    if chat_id not in ALLOWED_GROUP_IDS:
        return

    user_id = message.from_user.id
    message_time = message.date.strftime('%Y-%m-%d %H:%M:%S')

    if user_id in user_reported_status and user_reported_status[user_id]:
        return

    is_bot, avg_interval = check_bot(user_id, message_time)

    if is_bot:
        await report_to_admin(update, avg_interval)
        await mute_user(update)
        user_reported_status[user_id] = True

# Reset harian jam 00:00
def schedule_daily_reset():
    def reset_loop():
        while True:
            now = datetime.now()
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
            wait_seconds = (midnight - now).total_seconds()
            time.sleep(wait_seconds)

            user_message_timestamps.clear()
            user_reported_status.clear()
            print("🔥 Data userbot direset otomatis jam 00:00")

    thread = threading.Thread(target=reset_loop, daemon=True)
    thread.start()

# Main
def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))
    schedule_daily_reset()
    application.run_polling()

if __name__ == '__main__':
    main()
    print("Bot is running...")
