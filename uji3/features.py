import asyncio
import re
import logging
import json
import os
from telethon import events, errors
from telethon.tl.types import InputPeerUser
from datetime import datetime
from collections import defaultdict
import random
import emoji  # kalau mau pakai library emoji, tapi optional

# Menonaktifkan logging Telethon
logging.basicConfig(level=logging.CRITICAL)

# File untuk menyimpan state
STATE_FILE = 'bot_state.json'

# Struktur data global
active_groups = defaultdict(lambda: defaultdict(bool))
active_bc_interval = defaultdict(lambda: defaultdict(bool))
broadcast_data = defaultdict(dict)
blacklist = set()
auto_replies = defaultdict(list)  # 🛠 Fix utama di sini
user_reply_index = defaultdict(dict)  # 🛠 Track balasan tiap user

def parse_interval(interval_str):
    match = re.match(r'^(\d+)([smhd])$', interval_str)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    return value * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]

def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")

def save_state():
    state = {
        'active_bc_interval': {str(k): dict(v) for k, v in active_bc_interval.items()},
        'auto_replies': {str(k): v for k, v in auto_replies.items()},
        'blacklist': list(blacklist),
        'active_groups': {str(k): dict(v) for k, v in active_groups.items()},
        'broadcast_data': {
            str(user_id): {
                bc_type: data for bc_type, data in user_data.items()
            } for user_id, user_data in broadcast_data.items()
        }
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def load_state():
    global active_bc_interval, auto_replies, blacklist, active_groups, broadcast_data

    if not os.path.exists(STATE_FILE):
        return

    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)

        active_bc_interval.clear()
        for user_id, data in state.get('active_bc_interval', {}).items():
            active_bc_interval[int(user_id)] = defaultdict(bool, data)

        auto_replies.clear()
        for user_id, replies in state.get('auto_replies', {}).items():
            auto_replies[int(user_id)] = list(replies)

        blacklist.clear()
        blacklist.update(set(state.get('blacklist', [])))

        active_groups.clear()
        for group_id, data in state.get('active_groups', {}).items():
            active_groups[int(group_id)] = defaultdict(bool, data)

        broadcast_data.clear()
        for user_id, user_data in state.get('broadcast_data', {}).items():
            broadcast_data[int(user_id)] = user_data

    except Exception as e:
        print(f"Gagal memuat state: {e}")

async def run_broadcast(client, user_id, bc_type, messages, interval):
    while active_bc_interval[user_id].get(bc_type, False):
        async for dialog in client.iter_dialogs():
            if dialog.is_group and dialog.id not in blacklist:
                try:
                    # pilih pesan acak dari list messages
                    message = random.choice(messages)
                    await client.send_message(dialog.id, message)
                except Exception:
                    pass
        await asyncio.sleep(interval)

async def restart_broadcasts(client, user_id):
    for bc_type, is_active in active_bc_interval[user_id].items():
        if is_active and bc_type in broadcast_data.get(user_id, {}):
            data = broadcast_data[user_id][bc_type]
            asyncio.create_task(run_broadcast(client, user_id, bc_type, data['message'], data['interval']))

async def configure_event_handlers(client, user_id):
    await restart_broadcasts(client, user_id)

    if user_id in auto_replies and auto_replies[user_id]:
        print(f"Auto-reply untuk user {user_id} diaktifkan kembali")

    @client.on(events.NewMessage(pattern=r'^cloe hastle (.+) (\d+[smhd])$'))
    async def hastle_handler(event):
        custom_message, interval_str = event.pattern_match.groups()
        group_id = event.chat_id
        interval = parse_interval(interval_str)

        if not interval:
            await event.reply("⚠️ Format waktu salah! Gunakan format 10s, 1m, 2h, dll.")
            return

        if active_groups[group_id][user_id]:
            await event.reply("⚠️ Spam sudah berjalan untuk akun Anda di grup ini.")
            return

        active_groups[group_id][user_id] = True
        save_state()
        await event.reply(f"✅ Memulai spam: {custom_message} setiap {interval_str} untuk akun Anda.")
        while active_groups[group_id][user_id]:
            try:
                await client.send_message(group_id, custom_message)
                await asyncio.sleep(interval)
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                active_groups[group_id][user_id] = False
                save_state()

    @client.on(events.NewMessage(pattern=r'^cloe stop$'))
    async def stop_handler(event):
        group_id = event.chat_id
        if active_groups[group_id][user_id]:
            active_groups[group_id][user_id] = False
            save_state()
            await event.reply("✅ Spam dihentikan untuk akun Anda di grup ini.")
        else:
            await event.reply("⚠️ Tidak ada spam yang berjalan untuk akun Anda di grup ini.")

    @client.on(events.NewMessage(pattern=r'^cloe ping$'))
    async def ping_handler(event):
        await event.reply("🏓 Pong! Bot aktif.")

    @client.on(events.NewMessage(pattern=r'^cloe bcstar (.+)$'))
    async def broadcast_handler(event):
        custom_message = event.pattern_match.group(1)
        await event.reply(f"✅ Memulai broadcast ke semua chat: {custom_message}")
        async for dialog in client.iter_dialogs():
            if dialog.id in blacklist:
                continue
            try:
                await client.send_message(dialog.id, custom_message)
            except Exception:
                pass

    @client.on(events.NewMessage(pattern=r'^cloe bcstargr(\d+) (\d+[smhd]) (.+)$'))
    async def broadcast_group_handler(event):
        user_id = event.sender_id
        group_number = event.pattern_match.group(1)
        interval_str, custom_message_raw = event.pattern_match.groups()[1:]
        interval = parse_interval(interval_str)

        if not interval:
            await event.reply("⚠️ Format waktu salah! Gunakan format 10s, 1m, 2h, dll.")
            return

        # Pisahkan pesan dengan delimiter "|" dan simpan dalam list
        custom_message_list = [msg.strip() for msg in custom_message_raw.split("|") if msg.strip()]
        
        bc_type = f"group{group_number}"
        if active_bc_interval[user_id][bc_type]:
            await event.reply(f"⚠️ Broadcast ke grup {group_number} sudah berjalan.")
            return

        # Simpan list pesan di broadcast_data
        broadcast_data[user_id][bc_type] = {
            'message': custom_message_list,
            'interval': interval
        }

        active_bc_interval[user_id][bc_type] = True
        save_state()

        await event.reply(f"✅ Memulai broadcast ke grup {group_number} dengan interval {interval_str}: {', '.join(custom_message_list)}")
        await run_broadcast(client, user_id, bc_type, custom_message_list, interval)

    @client.on(events.NewMessage(pattern=r'^cloe stopbcstargr(\d+)$'))
    async def stop_broadcast_group_handler(event):
        group_number = event.pattern_match.group(1)
        bc_type = f"group{group_number}"
        if active_bc_interval[user_id][bc_type]:
            active_bc_interval[user_id][bc_type] = False
            save_state()
            await event.reply(f"✅ Broadcast ke grup {group_number} dihentikan.")
        else:
            await event.reply(f"⚠️ Tidak ada broadcast grup {group_number} yang berjalan.")

    @client.on(events.NewMessage(pattern=r'^cloe bl$'))
    async def blacklist_handler(event):
        chat_id = event.chat_id
        blacklist.add(chat_id)
        save_state()
        await event.reply("✅ Grup ini telah ditambahkan ke blacklist.")

    @client.on(events.NewMessage(pattern=r'^cloe unbl$'))
    async def unblacklist_handler(event):
        chat_id = event.chat_id
        if chat_id in blacklist:
            blacklist.remove(chat_id)
            save_state()
            await event.reply("✅ Grup ini telah dihapus dari blacklist.")
        else:
            await event.reply("⚠️ Grup ini tidak ada dalam blacklist.")

    @client.on(events.NewMessage(pattern=r'^cloe help$'))
    async def help_handler(event):
        help_text = (
            "📋 **Daftar Perintah yang Tersedia:**\n\n"
            "1. cloe hastle [pesan] [waktu][s/m/h/d]\n"
            "2. cloe stop\n"
            "3. cloe ping\n"
            "4. cloe bcstar [pesan]\n"
            "5. cloe bcstargr[waktu][s/m/h/d] [pesan]\n"
            "6. cloe stopbcstargr[1-10]\n"
            "7. cloe bl\n"
            "8. cloe unbl\n"
        )
        await event.reply(help_text)


    bot_replies = [
        "wwkwk bukan bot bang",
        "manusia asli bang",
        "yeuu bukan bukan bot",
        "santuy, bukan bot kok",
        "bot apaan? ini manusia asli dan ganteng bre",
        "asli manusia bro",
        "jangan salah, manusia asli nih",
        "ini bukan bot, serius",
        "ceelah bukan bot bwng"
    ]
    sorry_replies = [
        "wwkwkkw iya gapapa",
        "wkkwkw its oke",
        "iya gapapa ko",
        "aman"
    ]
    single_char_replies = [
        "hah?",
        "kenapa??",
        "iya?",
        "lho?",
        "ada apa?",
        "apa?",
        "?",
        "apaan"
    ]
    okay_replies = [
        "owh",
        "ohhh",
        "oh oke",
        "sip",
        "yaudah",
        "oke deh",
        "hmm",
        "ya gapapa"
    ]

    sapaan_replies = [
        "iyaa haloo",
        "haii juga",
        "iya hayyy",
        "iyaaa",
        "haii",
        "haloo jugaa",
        "hii jugaaa",
        "iya hay",
        "iya hay juga",
        "hai jugaa hehe"
    ]

    laugh_replies = [
        "wkwkw",
        "hahah",
        "😭",
        "🤣",
        "haha lucu",
        "wkwk lucu si tiba tiba ketawa",
        "kwkwkw sumpah",
        "wlekwlek",
        "lu ngapa ketawa dah",
        "ketawa sendiri 😭"
    ]


    @client.on(events.NewMessage(pattern=r'^cloe setreply\d+'))
    async def set_multi_reply(event):
        me = await client.get_me()
        uid = me.id
        message_lines = event.raw_text.strip().split('\n')

        if len(message_lines) < 2:
            await event.reply("⚠️ Harap isi pesan balasan setelah perintah. Contoh:\ncloe setreply1\nHai")
            return

        header = message_lines[0]
        match = re.match(r'^cloe setreply(\d+)', header)
        if not match:
            await event.reply("⚠️ Format salah. Gunakan: cloe setreply1, cloe setreply2, dst")
            return

        index = int(match.group(1)) - 1
        reply_msg = message_lines[1].strip()

        while len(auto_replies[uid]) <= index:
            auto_replies[uid].append(None)

        auto_replies[uid][index] = reply_msg
        save_state()
        await event.reply(f"✅ Balasan otomatis ke-{index + 1} berhasil diatur.")

    @client.on(events.NewMessage(incoming=True))
    async def auto_reply_staged(event):
        if not event.is_private or event.out:
            return

        me = await client.get_me()
        uid = me.id

        sender = await event.get_sender()
        sid = sender.id

        # Tambahan: jika pengirim bot, hanya ack baca, tanpa balas
        if getattr(sender, 'bot', False):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                await client.send_read_acknowledge(peer)
            except Exception:
                pass
            return

        message_text = event.raw_text.strip()
        message_text_lower = message_text.lower()

        # --- Tambahan khusus: kalau kata done, sudah, makasih, terima kasih dll ---
        thanks_patterns = [
            r'\b(done|dn|sudah|syudah|oke||dh|sip|udah)\b',
            r'makasih',
            r'terimakasihh yah',
            r'makasiiih lucu sayang',
            r'makasih yaaah \^\^',
            r'makasih cantik luv luv',
            r'thanks btw \^\^',
            r'thx ya',
            r'maacciii sudah mau masuk ><'
        ]
        if any(re.search(pat, message_text_lower) for pat in thanks_patterns):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                await asyncio.sleep(random.randint(3, 6))
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                # Bisa disesuaikan balasan, ini contoh:
                await client.send_message(peer, "Makasih ya! 😊")
            except Exception:
                pass
            return  # langsung stop, tidak lanjut cek kondisi lain

        # --- Kondisi khusus dulu: single char, sticker, gif, emoji ---
        is_single_char_text = len(message_text) == 1
        is_single_sticker = (
            event.media and getattr(event.media, 'document', None) and
            hasattr(event.media.document, 'attributes') and
            any(type(attr).__name__ == 'DocumentAttributeSticker' for attr in event.media.document.attributes)
        )
        is_single_gif = (
            event.media and getattr(event.media, 'document', None) and
            event.media.document.mime_type == 'video/mp4' and
            'animated' in (attr.__class__.__name__.lower() for attr in event.media.document.attributes)
        )
        is_single_emoji = len(message_text) == 1 and emoji.is_emoji(message_text)

        if is_single_char_text or is_single_sticker or is_single_gif or is_single_emoji:
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                total_delay = random.randint(5, 10)
                await asyncio.sleep(total_delay - 2)
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                reply_text = random.choice(single_char_replies)
                await client.send_message(peer, reply_text)
            except Exception:
                pass
            return

        if re.search(r'\b(sry|sorry|maaf|mf|srry)\b', message_text_lower):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                total_delay = random.randint(5, 10)
                await asyncio.sleep(total_delay - 2)
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                reply_text = random.choice(sorry_replies)
                await client.send_message(peer, reply_text)
            except Exception:
                pass
            return

        if 'bot' in message_text_lower:
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                total_delay = random.randint(5, 10)
                await asyncio.sleep(total_delay - 2)
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                reply_text = random.choice(bot_replies)
                await client.send_message(peer, reply_text)
            except Exception:
                pass
            return

        if uid in auto_replies and any(auto_replies[uid]):
            idx = user_reply_index[uid].get(sid, 0)
            replies = auto_replies[uid]
            if idx < len(replies) and replies[idx]:
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    total_delay = random.randint(5, 10)
                    await asyncio.sleep(total_delay - 2)
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    await client.send_message(peer, replies[idx])
                    user_reply_index[uid][sid] = idx + 1
                except Exception:
                    pass
                return

        # --- Prioritas tinggi: need/nd + temen/friend/bestie ---
        if re.search(r'\b(nd|need|pacaran|pacar|pacal)\b', message_text_lower):
            if re.search(r'\b(temen|temenan|friend|friends?|bestie)\b', message_text_lower):
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    await asyncio.sleep(random.randint(5, 10))
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    await client.send_message(peer, "sabi ga si boleh siapa tau jadi bestie wwkwkwk")
                except Exception:
                    pass
                return
            elif re.search(r'\bgf\b', message_text_lower):
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    await asyncio.sleep(random.randint(5, 10))
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    await client.send_message(peer, "iya gua need gf")
                except Exception:
                    pass
                return
            else:
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    await asyncio.sleep(random.randint(5, 10))
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    options = ["iya need gf,", "need apa aja,", "iya gua need,", "iya need gua"]
                    await client.send_message(peer, random.choice(options))
                except Exception:
                    pass
                return

        # --- Fambst/famb ---
        if re.search(r'\b(famb|fambs?t)\b', message_text_lower):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                await asyncio.sleep(random.randint(5, 10))
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                await client.send_message(peer, "iya boleh, mau jadi apa?")
            except Exception:
                pass
            return

        # --- Temen/friend/bestie (kalau gak pakai need) ---
        if re.search(r'\b(temen|temenan|friend|friends?|bestie)\b', message_text_lower):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                await asyncio.sleep(random.randint(5, 10))
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                await client.send_message(peer, "sabi ga si boleh siapa tau jadi bestie wwkwkwk")
            except Exception:
                pass
            return

        # --- Okay response untuk kata umum ---
        if re.search(r'\b(ngga|ga jadi|gpp|gapapa|ngg|ga|g|bukan apa apa|kepencet|itu)\b', message_text_lower):
            try:
                peer = InputPeerUser(sender.id, sender.access_hash)
                await asyncio.sleep(random.randint(5, 10))
                await client.send_read_acknowledge(peer)
                await asyncio.sleep(2)
                reply_text = random.choice(okay_replies)
                await client.send_message(peer, reply_text)
            except Exception:
                pass
            return

        # --- Sapaan terakhir (jika tidak mengandung kata-kata penting) ---
        if not re.search(r'\b(nd|need|gf|temen|temenan|friend|friends?|bestie|famb|fambs?t)\b', message_text_lower):
            if re.search(r'\b(Hi+|hi+|hy+|hay+|halo+|hawo+|halloo+|haloo+)\b', message_text_lower) or re.search(r'\b(hayy|juga)\b', message_text_lower):
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    await asyncio.sleep(random.randint(3, 6))
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    await client.send_message(peer, random.choice(sapaan_replies))
                except Exception:
                    pass
                return

            if re.search(r'\b(wk|wkwk|wkwkwk|hhh|hh|hhaha|hahaha|haha|hehe|awkwk|kwkw|xixixi|kekeke|lmao|lol)\b', message_text_lower):
                try:
                    peer = InputPeerUser(sender.id, sender.access_hash)
                    total_delay = random.randint(5, 10)
                    await asyncio.sleep(total_delay - 2)
                    await client.send_read_acknowledge(peer)
                    await asyncio.sleep(2)
                    reply_text = random.choice(laugh_replies)
                    await client.send_message(peer, reply_text)
                except Exception:
                    pass
                return

    @client.on(events.NewMessage(pattern=r'^cloe stopall$'))
    async def stop_all_handler(event):
        me = await client.get_me()
        user_id = me.id
        active_bc_interval[user_id].clear()
        auto_replies[user_id] = []
        blacklist.clear()
        for group_id in list(active_groups.keys()):
            if user_id in active_groups[group_id]:
                active_groups[group_id][user_id] = False
        if user_id in broadcast_data:
            broadcast_data[user_id].clear()
        save_state()
        await event.reply("✅ SEMUA FITUR TELAH DIHENTIKAN DAN DIHAPUS")

# Jalankan pemuatan state saat awal
load_state()
