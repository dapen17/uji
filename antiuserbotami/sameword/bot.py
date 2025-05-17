import telebot
from collections import defaultdict
from datetime import datetime, timedelta
import schedule
import time
import threading

# ================= CONFIG =================

# Token bot kamu
TOKEN = '7259365721:AAGFf7iWS3biq0KrdLtlprXPOakLYo3_4sw'
bot = telebot.TeleBot(TOKEN)

# ID grup yang diizinkan
ALLOWED_GROUP_IDS = [
    -1002604965354,
    -1002422132097,
    -1002181377143,
    -1002391683524,
    -1002494436143
]

# Username yang tidak akan pernah kena mute (tanpa @)
WHITELIST_USERNAMES = [
    "marvnc",
    "yunjense",
    "Jasvieswest",
    "eldricknm",
    "Senjunm",
    "KimMeenjuu",
    "m4sbim",
    "egranmephisto",
    "bar4as",
    "jeyun4s",
    "Mask4in",
    "Jiissung",
    "jiisseong",
    "Dooyoungkp",
    "K1mJeko"

]

# Menyimpan data per (chat_id, user_id)
user_data = defaultdict(lambda: {
    'message': None,
    'count': 0,
    'nd_need_count': 0,
    'last_reset': datetime.now()
})

# =============== LOGIC ===============

# Reset harian pukul 00:00 WIB (UTC+7)
def reset_user_data():
    now = datetime.now()
    for key in list(user_data.keys()):
        if now - user_data[key]['last_reset'] > timedelta(days=1):
            user_data[key] = {
                'message': None,
                'count': 0,
                'nd_need_count': 0,
                'last_reset': now
            }
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🔁 Data user telah di-reset.")

schedule.every().day.at("00:00").do(reset_user_data)

# Mute user (durasi bisa diatur)
def mute_user(user_id, chat_id, duration_days=15):
    until_date = int((datetime.now() + timedelta(days=duration_days)).timestamp())
    try:
        bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            can_send_messages=False,
            until_date=until_date
        )
    except Exception as e:
        print(f"❌ Gagal mute user {user_id}: {e}")

# Kirim pesan penghapusan (placeholder)
def delete_user_messages(user_id, chat_id):
    bot.send_message(
        chat_id,
        f"Semua pesan dari <a href='tg://user?id={user_id}'>User</a> telah dihapus karena melanggar aturan.",
        parse_mode='HTML'
    )

# =============== HANDLER GRUP ===============

@bot.message_handler(func=lambda message: message.chat.id in ALLOWED_GROUP_IDS)
def handle_group_message(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username or ""
    text = message.text.lower() if message.text else ""
    key = (chat_id, user_id)

    # Lewati jika user di whitelist
    if username.lower() in [u.lower() for u in WHITELIST_USERNAMES]:
        return

    # Ambil data user
    data = user_data[key]

    # 1. Deteksi awalan need/nd
    if text.startswith("need") or text.startswith("nd"):
        data['nd_need_count'] += 1
        if data['nd_need_count'] >= 200:
            mention = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
            bot.send_message(
                chat_id,
                f"🚫 {mention} Akun Anda terdeteksi SPAM/BOT. Anda dimute selama 2 minggu.",
                parse_mode='HTML'
            )
            mute_user(user_id, chat_id, duration_days=15)
            delete_user_messages(user_id, chat_id)
            user_data[key] = {
                'message': None,
                'count': 0,
                'nd_need_count': 0,
                'last_reset': datetime.now()
            }
        return

    # 2. Deteksi spam pesan sama
    if data['message'] != text:
        data['message'] = text
        data['count'] = 1
    else:
        data['count'] += 1
        if data['count'] >= 150:
            mention = f"<a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>"
            bot.send_message(
                chat_id,
                f"⚠️ {mention} Anda Terdeteksi spam / bot, di mute selama 1 minggu.",
                parse_mode='HTML'
            )
            mute_user(user_id, chat_id, duration_days=7)
            delete_user_messages(user_id, chat_id)
            user_data[key] = {
                'message': None,
                'count': 0,
                'nd_need_count': 0,
                'last_reset': datetime.now()
            }

# =============== HANDLER PRIVATE CHAT ===============

@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_private_message(message):
    bot.send_message(
        message.chat.id,
        "Mau nyewa bot ini demi keamanan grup kalian dari lolosnya userbot? Nyewa botnya rc @Galantedump murah meriah"
    )

# =============== JALANKAN BOT & RESET ===============

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()
    print("🤖 Bot berjalan...")
    bot.polling(none_stop=True)
# ================= END OF FILE =================