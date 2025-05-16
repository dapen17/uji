import asyncio
import re
import logging
from telethon import events, errors
from telethon.tl.types import InputPeerUser
from datetime import datetime
from collections import defaultdict

# Menonaktifkan logging Telethon
logging.basicConfig(level=logging.CRITICAL)

# Menyimpan status per akun dan grup
active_groups = defaultdict(lambda: defaultdict(bool))  # {group_id: {user_id: status}}
active_bc_interval = defaultdict(lambda: defaultdict(bool))  # {user_id: {type: status}}
blacklist = set()
auto_replies = defaultdict(str)  # {user_id: auto_reply_message}

def parse_interval(interval_str):
    """Konversi format [10s, 1m, 2h, 1d] menjadi detik."""
    match = re.match(r'^(\d+)([smhd])$', interval_str)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    return value * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]

def get_today_date():
    """Mengembalikan tanggal hari ini dalam format YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")

async def configure_event_handlers(client, user_id):
    """Konfigurasi semua fitur bot untuk user_id tertentu."""

    # Spam pesan ke grup dengan interval tertentu
    @client.on(events.NewMessage(pattern=r'^ami hastle (.+) (\d+[smhd])$'))
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
        await event.reply(f"✅ Memulai spam: {custom_message} setiap {interval_str} untuk akun Anda.")
        while active_groups[group_id][user_id]:
            try:
                await client.send_message(group_id, custom_message)
                await asyncio.sleep(interval)
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception as e:
                # Menangani error tanpa output log
                active_groups[group_id][user_id] = False

    # Hentikan spam di grup
    @client.on(events.NewMessage(pattern=r'^ami stop$'))
    async def stop_handler(event):
        group_id = event.chat_id
        if active_groups[group_id][user_id]:
            active_groups[group_id][user_id] = False
            await event.reply("✅ Spam dihentikan untuk akun Anda di grup ini.")
        else:
            await event.reply("⚠️ Tidak ada spam yang berjalan untuk akun Anda di grup ini.")

    # Tes koneksi bot
    @client.on(events.NewMessage(pattern=r'^ami ping$'))
    async def ping_handler(event):
        await event.reply("🏓 Pong! Bot aktif.")

    # Broadcast pesan ke semua chat kecuali blacklist
    @client.on(events.NewMessage(pattern=r'^ami bcstar (.+)$'))
    async def broadcast_handler(event):
        custom_message = event.pattern_match.group(1)
        await event.reply(f"✅ Memulai broadcast ke semua chat: {custom_message}")
        async for dialog in client.iter_dialogs():
            if dialog.id in blacklist:
                continue
            try:
                await client.send_message(dialog.id, custom_message)
            except Exception as e:
                # Menangani error tanpa output log
                pass

    # Broadcast pesan hanya ke grup dengan interval tertentu
    @client.on(events.NewMessage(pattern=r'^ami bcstargr(\d+) (\d+[smhd]) (.+)$'))
    async def broadcast_group_handler(event):
        group_number = event.pattern_match.group(1)
        interval_str, custom_message = event.pattern_match.groups()[1:]
        interval = parse_interval(interval_str)

        if not interval:
            await event.reply("⚠️ Format waktu salah! Gunakan format 10s, 1m, 2h, dll.")
            return

        if active_bc_interval[user_id][f"group{group_number}"]:
            await event.reply(f"⚠️ Broadcast ke grup {group_number} sudah berjalan.")
            return

        active_bc_interval[user_id][f"group{group_number}"] = True
        await event.reply(f"✅ Memulai broadcast ke grup {group_number} dengan interval {interval_str}: {custom_message}")
        while active_bc_interval[user_id][f"group{group_number}"]:
            async for dialog in client.iter_dialogs():
                if dialog.is_group and dialog.id not in blacklist:
                    try:
                        await client.send_message(dialog.id, custom_message)
                    except Exception as e:
                        # Menangani error tanpa output log
                        pass
            await asyncio.sleep(interval)

    # Hentikan broadcast grup
    @client.on(events.NewMessage(pattern=r'^ami stopbcstargr(\d+)$'))
    async def stop_broadcast_group_handler(event):
        group_number = event.pattern_match.group(1)
        if active_bc_interval[user_id][f"group{group_number}"]:
            active_bc_interval[user_id][f"group{group_number}"] = False
            await event.reply(f"✅ Broadcast ke grup {group_number} dihentikan.")
        else:
            await event.reply(f"⚠️ Tidak ada broadcast grup {group_number} yang berjalan.")

    # Tambahkan grup/chat ke blacklist
    @client.on(events.NewMessage(pattern=r'^ami bl$'))
    async def blacklist_handler(event):
        chat_id = event.chat_id
        blacklist.add(chat_id)
        await event.reply("✅ Grup ini telah ditambahkan ke blacklist.")

    # Hapus grup/chat dari blacklist
    @client.on(events.NewMessage(pattern=r'^ami unbl$'))
    async def unblacklist_handler(event):
        chat_id = event.chat_id
        if chat_id in blacklist:
            blacklist.remove(chat_id)
            await event.reply("✅ Grup ini telah dihapus dari blacklist.")
        else:
            await event.reply("⚠️ Grup ini tidak ada dalam blacklist.")

    # Tampilkan daftar perintah
    @client.on(events.NewMessage(pattern=r'^ami help$'))
    async def help_handler(event):
        help_text = (
            "📋 **Daftar Perintah yang Tersedia:**\n\n"
            "1. ami hastle [pesan] [waktu][s/m/h/d]\n"
            "   Spam pesan di grup dengan interval tertentu.\n"
            "2. ami stop\n"
            "   Hentikan spam di grup.\n"
            "3. ami ping\n"
            "   Tes koneksi bot.\n"
            "4. ami bcstar [pesan]\n"
            "   Broadcast ke semua chat kecuali blacklist.\n"
            "5. ami bcstargr [waktu][s/m/h/d] [pesan]\n"
            "   Broadcast hanya ke grup dengan interval tertentu.\n"
            "6. ami stopbcstargr[1-10]\n"
            "   Hentikan broadcast ke grup tertentu.\n"
            "7. ami bl\n"
            "    Tambahkan grup/chat ke blacklist.\n"
            "8. ami unbl\n"
            "    Hapus grup/chat dari blacklist.\n"
        )
        await event.reply(help_text)

    # Atur auto-reply
    @client.on(events.NewMessage(pattern=r'^ami setreply (.+)$'))
    async def set_auto_reply(event):
        reply_message = event.pattern_match.group(1)
        auto_replies[user_id] = reply_message
        await event.reply(f"\u2705 Auto-reply diatur: {reply_message}")

    # Menangani auto-reply
    @client.on(events.NewMessage(incoming=True))
    async def auto_reply_handler(event):
        if event.is_private and user_id in auto_replies and auto_replies[user_id]:
            try:
                sender = await event.get_sender()
                peer = InputPeerUser(sender.id, sender.access_hash)
                await client.send_message(peer, auto_replies[user_id])
                await client.send_read_acknowledge(peer)
            except errors.rpcerrorlist.UsernameNotOccupiedError:
                pass  # Jangan tampilkan error
            except errors.rpcerrorlist.FloodWaitError as e:
                pass  # Jangan tampilkan error
            except Exception as e:
                pass  # Jangan tampilkan error

    # Hentikan semua pengaturan
    @client.on(events.NewMessage(pattern=r'^ami stopall$'))
    async def stop_all_handler(event):
        for group_key in active_bc_interval[user_id].keys():
            active_bc_interval[user_id][group_key] = False
        auto_replies[user_id] = ""
        blacklist.clear()
        for group_id in active_groups.keys():
            active_groups[group_id][user_id] = False
        for group_key in active_bc_interval[user_id].keys():
            if active_bc_interval[user_id][group_key]:
                active_bc_interval[user_id][group_key] = False
        await event.reply("\u2705 Semua pengaturan telah direset dan semua broadcast dihentikan.")
