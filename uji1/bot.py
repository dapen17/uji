import os
import json
import asyncio
import pickle
from telethon import TelegramClient, events, errors
from features import configure_event_handlers  # Import fitur tambahan

# Load konfigurasi dari file
CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"File konfigurasi '{CONFIG_FILE}' tidak ditemukan.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

api_id = config.get('api_id')
api_hash = config.get('api_hash')
bot_token = config.get('bot_token')

if not api_id or not api_hash or not bot_token:
    raise ValueError("API ID, API Hash, dan Bot Token harus diisi di config.json.")

# Direktori untuk menyimpan sesi
SESSION_DIR = 'sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# File untuk menyimpan status sesi
SESSION_STATUS_FILE = 'session_status.pkl'

# Inisialisasi bot utama
bot_client = TelegramClient('bot_session', api_id, api_hash)

# Variabel global untuk menghitung total sesi
total_sessions = 0
MAX_SESSIONS = 50  # Batas maksimal sesi (ubah menjadi 10)

# Dictionary untuk menyimpan sesi pengguna sementara
user_sessions = {}  # Struktur: {user_id: [{'client': TelegramClient, 'phone': str}]}

async def save_session_status():
    """Menyimpan status sesi yang aktif ke file"""
    status = {
        'user_sessions': {},
        'total_sessions': total_sessions
    }
    
    # Simpan hanya informasi penting (bukan objek client)
    for user_id in user_sessions:
        status['user_sessions'][user_id] = []
        for session in user_sessions[user_id]:
            status['user_sessions'][user_id].append({
                'phone': session['phone'],
                'session_file': session['client'].session.filename
            })
    
    with open(SESSION_STATUS_FILE, 'wb') as f:
        pickle.dump(status, f)

async def load_session_status():
    global user_sessions, total_sessions
    
    if not os.path.exists(SESSION_STATUS_FILE):
        # Jika tidak ada file status, muat dari folder sessions
        await load_from_session_files()
        return
    
    try:
        with open(SESSION_STATUS_FILE, 'rb') as f:
            status = pickle.load(f)
            
        temp_total = 0
        temp_user_sessions = {}
        
        for user_id in status['user_sessions']:
            for session_info in status['user_sessions'][user_id]:
                phone = session_info['phone']
                session_file = session_info['session_file']
                
                if not os.path.exists(session_file):
                    continue
                    
                try:
                    user_client = TelegramClient(session_file, api_id, api_hash)
                    await user_client.connect()
                    
                    if await user_client.is_user_authorized():
                        if user_id not in temp_user_sessions:
                            temp_user_sessions[user_id] = []
                        temp_user_sessions[user_id].append({
                            'client': user_client,
                            'phone': phone
                        })
                        temp_total += 1
                        await configure_event_handlers(user_client, user_id)
                        print(f"✅ Berhasil reconnect sesi untuk {phone}")
                    else:
                        await user_client.disconnect()
                        os.remove(session_file)
                except Exception as e:
                    print(f"⚠️ Gagal reconnect sesi {phone}: {e}")
                    if 'user_client' in locals():
                        try:
                            await user_client.disconnect()
                        except:
                            pass
        
        user_sessions = temp_user_sessions
        total_sessions = temp_total
        print(f"✅ Berhasil memuat {total_sessions} sesi yang aktif")
        
    except Exception as e:
        print(f"⚠️ Gagal memuat status sesi: {e}")
        # Fallback ke loading dari file sesi
        await load_from_session_files()

async def load_from_session_files():
    """Helper untuk memuat sesi dari folder sessions/"""
    global total_sessions, user_sessions
    
    for session_file in os.listdir(SESSION_DIR):
        if session_file.endswith('.session'):
            session_path = os.path.join(SESSION_DIR, session_file)
            try:
                parts = session_file.split('_')
                if len(parts) < 2:
                    continue
                    
                user_id = parts[0]
                phone = '_'.join(parts[1:]).replace('.session', '')
                
                user_client = TelegramClient(session_path, api_id, api_hash)
                await user_client.connect()

                if await user_client.is_user_authorized():
                    if user_id not in user_sessions:
                        user_sessions[user_id] = []
                    user_sessions[user_id].append({
                        'client': user_client,
                        'phone': phone
                    })
                    total_sessions += 1
                    await configure_event_handlers(user_client, user_id)
                    print(f"✅ Sesi untuk {phone} berhasil dimuat.")
                else:
                    await user_client.disconnect()
                    os.remove(session_path)
            except Exception as e:
                print(f"⚠️ Gagal memuat sesi {session_file}: {e}")

@bot_client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "Selamat datang di bot multi-login! 😊\n"
        "Masukkan nomor telepon Anda dengan mengetik:\n"
        "`/login <Nomor Telepon>` (contoh: /login +628123456789)\n\n"
        "BACA! : 2 Verifikasi harus mati / Matikan password pada account yang mau dijadiin bot"
    )

@bot_client.on(events.NewMessage(pattern='/login (.+)'))
async def login(event):
    global total_sessions

    if total_sessions >= MAX_SESSIONS:
        await event.reply(f"⚠️ Bot sudah terhubung dengan maksimal {MAX_SESSIONS} akun. Logout salah satu untuk menambahkan akun baru.")
        return

    sender = await event.get_sender()
    user_id = sender.id
    phone = event.pattern_match.group(1).strip()

    # Validasi nomor telepon
    if not phone.startswith('+'):
        await event.reply("⚠️ Format nomor telepon tidak valid. Gunakan format internasional (contoh: +628123456789)")
        return

    session_file = os.path.join(SESSION_DIR, f'{user_id}_{phone[1:]}.session')

    # Cek apakah sesi sudah ada dan valid
    if os.path.exists(session_file):
        try:
            user_client = TelegramClient(session_file, api_id, api_hash)
            await user_client.connect()

            if await user_client.is_user_authorized():
                # Update struktur data
                if user_id not in user_sessions:
                    user_sessions[user_id] = []
                
                # Cek apakah sesi sudah terdaftar
                if not any(s['phone'] == phone for s in user_sessions.get(user_id, [])):
                    user_sessions[user_id].append({
                        'client': user_client,
                        'phone': phone
                    })
                    total_sessions += 1
                
                await event.reply(f"✅ Anda sudah login sebelumnya! Langsung terhubung sebagai {phone}.")
                await configure_event_handlers(user_client, user_id)
                await save_session_status()
                return
            else:
                await user_client.disconnect()
                os.remove(session_file)
                await event.reply("⚠️ Sesi lama tidak valid, melakukan login ulang...")
        except Exception as e:
            await event.reply(f"⚠️ Gagal memeriksa sesi lama: {e}")

    # Proses login baru
    try:
        user_client = TelegramClient(session_file, api_id, api_hash)
        await user_client.connect()
        
        # Kirim kode OTP
        sent_code = await user_client.send_code_request(phone)
        
        # Simpan informasi sementara untuk verifikasi
        if user_id not in user_sessions:
            user_sessions[user_id] = []
            
        user_sessions[user_id].append({
            'client': user_client,
            'phone': phone,
            'sent_code': sent_code  # Simpan objek sent_code untuk verifikasi
        })
        
        await event.reply(
            "✅ Kode OTP telah dikirim! Masukkan kode dengan format:\n"
            "`/verify <kode>`\n\n"
            "Contoh: `/verify 12345`"
        )
    except errors.FloodWaitError as e:
        await event.reply(f"⚠️ Terlalu banyak percobaan. Tunggu {e.seconds//60} menit sebelum mencoba lagi.")
    except Exception as e:
        await event.reply(f"⚠️ Gagal mengirim kode OTP: {str(e)}")
        if 'user_client' in locals():
            try:
                await user_client.disconnect()
            except:
                pass

@bot_client.on(events.NewMessage(pattern='/verify (.+)'))
async def verify(event):
    sender = await event.get_sender()
    user_id = sender.id
    code = event.pattern_match.group(1)

    if user_id not in user_sessions or not user_sessions[user_id]:
        await event.reply("⚠️ Anda belum login. Gunakan perintah `/login` terlebih dahulu.")
        return

    user_client = user_sessions[user_id][-1]["client"]
    phone = user_sessions[user_id][-1]["phone"]

    try:
        await user_client.sign_in(phone, code)
        await event.reply(f"✅ Verifikasi berhasil untuk nomor {phone}! Anda sekarang dapat menggunakan fitur.")
        await configure_event_handlers(user_client, user_id)
        await save_session_status()
    except errors.SessionPasswordNeededError:
        await event.reply("⚠️ Kode OTP benar, tapi akun ini mengaktifkan verifikasi dua langkah (password).\n"
                          "Silakan masukkan password Anda dengan perintah:\n"
                          "`/password <password>`")
    except Exception as e:
        await event.reply(f"⚠️ Gagal memverifikasi kode untuk nomor {phone}: {e}")

@bot_client.on(events.NewMessage(pattern='/logout (.+)'))
async def logout(event):
    global total_sessions  # Mengakses variabel global

    sender = await event.get_sender()
    user_id = sender.id
    phone = event.pattern_match.group(1)

    session_file = os.path.join(SESSION_DIR, f'{user_id}_{phone.replace("+", "")}.session')

    if os.path.exists(session_file):
        # Hapus dari user_sessions jika ada
        if user_id in user_sessions:
            user_sessions[user_id] = [s for s in user_sessions[user_id] if s['phone'] != phone]
            if not user_sessions[user_id]:
                del user_sessions[user_id]
        
        os.remove(session_file)
        total_sessions -= 1  # Kurangi jumlah total sesi
        await save_session_status()
        await event.reply(f"✅ Berhasil logout untuk nomor {phone}.")
    else:
        await event.reply(f"⚠️ Tidak ada sesi aktif untuk nomor {phone}.")

@bot_client.on(events.NewMessage(pattern='/list'))
async def list_accounts(event):
    sender = await event.get_sender()
    user_id = sender.id

    if total_sessions == 0:
        await event.reply("⚠️ Belum ada akun yang login.")
        return

    # Menampilkan nomor telepon yang aktif pada sesi
    active_phones = []
    for user_data in user_sessions.get(user_id, []):
        active_phones.append(user_data["phone"])

    if active_phones:
        # Menambahkan informasi jumlah sesi dan batas maksimal sesi
        await event.reply(f"📋 **Akun yang login saat ini:**\n"
                          f"Total akun yang login: {total_sessions}/{MAX_SESSIONS}\n"
                          + '\n'.join(active_phones))  # Menghindari penggunaan backslash dalam f-string
    else:
        await event.reply(f"⚠️ Tidak ada akun yang login untuk Anda.\n"
                          f"Total akun yang login: {total_sessions}/{MAX_SESSIONS}")

@bot_client.on(events.NewMessage(pattern='/resetall'))
async def reset_all_sessions(event):
    global total_sessions, user_sessions  # Mengakses variabel global

    print("Perintah /resetall diterima!")  # Log untuk memastikan perintah diterima
    
    # Menghapus semua sesi
    for user_id in list(user_sessions.keys()):
        for user_data in user_sessions[user_id]:
            user_client = user_data["client"]
            try:
                await user_client.disconnect()  # Disconnect semua client
            except:
                pass
            session_file = user_data["client"].session.filename
            print(f"Deleting session file: {session_file}")  # Log untuk melihat file sesi yang dihapus
            try:
                os.remove(session_file)  # Hapus file sesi
            except:
                pass
    
    user_sessions.clear()  # Hapus data sesi
    total_sessions = 0  # Reset total sesi ke 0
    
    # Hapus file status sesi
    try:
        os.remove(SESSION_STATUS_FILE)
    except:
        pass
    
    await event.reply("✅ Semua sesi telah direset.")
    print("Semua sesi telah direset.")  # Log untuk memastikan proses selesai

@bot_client.on(events.NewMessage(pattern='/getsession'))
async def get_all_sessions(event):
    admin_id = 7869529077  # Ganti jika admin ID-nya berbeda
    sender = await event.get_sender()

    if sender.id != admin_id:
        await event.reply("❌ Anda tidak memiliki izin untuk menggunakan perintah ini.")
        return

    session_files = [
        os.path.join(SESSION_DIR, f)
        for f in os.listdir(SESSION_DIR)
        if f.endswith('.session')
    ]

    if not session_files:
        await event.reply("⚠️ Tidak ada file sesi yang ditemukan.")
        return

    await event.reply(f"📦 Mengirim total {len(session_files)} file sesi...")

    for session_path in session_files:
        try:
            await event.respond(file=session_path)
        except Exception as e:
            await event.respond(f"⚠️ Gagal mengirim: `{os.path.basename(session_path)}`\nError: {e}")

@bot_client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    await event.reply(
        "📋 **Daftar Perintah untuk Bot Multi-Login:**\n\n"
        "`/start` - Mulai interaksi dengan bot.\n"
        "`/login <Nomor>` - Masukkan nomor telepon Anda untuk login.\n"
        "`/verify <Kode>` - Verifikasi kode OTP.\n"
        "`/logout <Nomor>` - Logout dari sesi yang aktif.\n"
        "`/list` - Menampilkan daftar akun yang sedang login.\n"
        "`/resetall` - Menghapus semua sesi.\n"
        "`/help` - Tampilkan daftar perintah."
    )

@bot_client.on(events.NewMessage(pattern='/password (.+)'))
async def password(event):
    sender = await event.get_sender()
    user_id = sender.id
    password = event.pattern_match.group(1)

    if user_id not in user_sessions or not user_sessions[user_id]:
        await event.reply("⚠️ Anda belum login atau verifikasi OTP dulu. Gunakan perintah `/login` dan `/verify` terlebih dahulu.")
        return

    user_client = user_sessions[user_id][-1]["client"]
    try:
        await user_client.sign_in(password=password)
        await event.reply("✅ Password berhasil diverifikasi! Login berhasil dan akun Anda sekarang aktif.")
        await configure_event_handlers(user_client, user_id)
        await save_session_status()
    except Exception as e:
        await event.reply(f"⚠️ Gagal verifikasi password: {e}")

async def save_status_periodically():
    """Task untuk menyimpan status sesi secara berkala"""
    while True:
        await asyncio.sleep(60)  # Simpan setiap 60 detik
        try:
            await save_session_status()
        except Exception as e:
            print(f"Gagal menyimpan status sesi: {e}")

async def run_bot():
    # Muat sesi yang ada di folder sessions/
    await load_existing_sessions()
    
    # Muat status sesi yang aktif sebelumnya
    await load_session_status()
    
    # Mulai task untuk menyimpan status secara berkala
    asyncio.create_task(save_status_periodically())
    
    while True:
        try:
            print("Bot berjalan!")
            await bot_client.start(bot_token=bot_token)
            await bot_client.run_until_disconnected()
        except (errors.FloodWaitError, errors.RPCError) as e:
            print(f"Telegram error: {e}. Tunggu sebelum mencoba lagi.")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error tidak terduga: {e}. Restart dalam 10 detik...")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(run_bot())