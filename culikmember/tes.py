from telethon.sync import TelegramClient
from telethon.errors.rpcerrorlist import PeerFloodError, FloodWaitError, UserPrivacyRestrictedError, UserBotError
from telethon.tl.functions.channels import InviteToChannelRequest, GetFullChannelRequest
import csv
import time
import logging
import traceback

# Configuration
api_id = 29032096
api_hash = '6d468e283f52ce30c7a716f84154a2bd'

group_username = input("Masukkan username grup kamu (contoh: @grupku): ")
target_group_link = input("Masukkan link grup target (contoh: https://t.me/targetgroup): ")

members_file = 'members.csv'
accounts_file = 'accounts.csv'

num_users_per_account = 50
delay_between_adds = 30  # seconds between adding users
delay_between_batches = 900  # 15 minutes between batches
max_flood_wait = 3600  # maximum 1 hour flood wait

# Logging
logging.basicConfig(
    filename='telegram_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def load_phone_numbers():
    phones = []
    try:
        with open(accounts_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                phones.append(row['phone'].strip())
    except Exception as e:
        print(f"[!] Gagal baca {accounts_file}: {e}")
        exit()
    return phones

def login(client, phone):
    try:
        client.connect()
        if not client.is_user_authorized():
            client.send_code_request(phone)
            code = input(f"[{phone}] Masukkan kode OTP: ")
            client.sign_in(phone, code)
        return client
    except Exception as e:
        print(f"[{phone}] ❌ Login gagal: {e}")
        logging.error(f"{phone} Login error: {e}")
        traceback.print_exc()
        return None

def scrape_users(client, link):
    try:
        target = client(GetFullChannelRequest(link)).chats[0]
        participants = client.get_participants(target, aggressive=True)

        with open(members_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'username', 'access_hash', 'name'])
            for user in participants:
                writer.writerow([user.id, user.username or '', user.access_hash, user.first_name or ''])

        print(f"[✓] Berhasil scrap member dari {link}")
        logging.info(f"Scraped users from {link}")
        return len(participants)
    except Exception as e:
        print(f"[✗] Gagal scrape: {e}")
        logging.error(f"Scrape error: {e}")
        traceback.print_exc()
        return 0

def add_users(client, group, phone, account_index, total_accounts):
    try:
        with open(members_file, 'r', encoding='utf-8') as f:
            users = list(csv.reader(f))[1:]  # Skip header

        total_users = len(users)
        print(f"[{phone}] 📊 Total {total_users} user akan ditambahkan")
        
        for i, user in enumerate(users):
            try:
                entity = client.get_input_entity(int(user[0]))
                client(InviteToChannelRequest(group, [entity]))
                username = user[1] if user[1] else "(no username)"
                print(f"[{phone}] ✅ ({i+1}/{total_users}) Menambahkan: {username} ({user[0]})")
                logging.info(f"{phone} added {username} ({user[0]})")
                
                # Progress report every 10 users
                if (i+1) % 10 == 0:
                    print(f"[{phone}] 📌 Progress: {i+1}/{total_users} ({((i+1)/total_users)*100:.1f}%)")
                
                time.sleep(delay_between_adds)
                
            except (FloodWaitError, PeerFloodError) as e:
                raise e  # Re-raise flood errors to handle in main loop
            except UserPrivacyRestrictedError:
                print(f"[{phone}] ⚠️ User {user[1]} privasinya ketat, skip.")
            except UserBotError:
                print(f"[{phone}] ❌ Bot tidak bisa dipakai, gunakan akun biasa.")
                raise
            except Exception as e:
                print(f"[{phone}] ❌ Error lain: {e}")
                logging.error(f"{phone} Add error: {e}")
                traceback.print_exc()
                
    except Exception as e:
        print(f"[{phone}] ❌ Gagal baca file CSV: {e}")
        logging.error(f"{phone} CSV read error: {e}")

def main():
    phones = load_phone_numbers()
    total_accounts = len(phones)
    
    flood_status = [False] * total_accounts  # Track flooded accounts
    flood_wait_until = [0] * total_accounts  # When each account can be retried
    
    while True:
        all_flooded = True
        
        for index, phone in enumerate(phones):
            now = time.time()
            
            # Skip if account is still in flood cooldown
            if flood_status[index] and now < flood_wait_until[index]:
                wait_seconds = int(flood_wait_until[index] - now)
                print(f"[{phone}] ⚠️ Masih kena flood, tunggu {wait_seconds} detik lagi. Lewati dulu.")
                continue
            
            # Reset flood status if cooldown is over
            if flood_status[index] and now >= flood_wait_until[index]:
                print(f"[{phone}] 🟢 Flood selesai, coba lagi.")
                flood_status[index] = False
            
            if flood_status[index]:
                continue
            
            all_flooded = False
            
            print(f"\n[🔐] ({index+1}/{total_accounts}) Login akun: {phone}")
            client = TelegramClient(phone, api_id, api_hash)
            client = login(client, phone)
            
            if client and client.is_user_authorized():
                try:
                    scrape_users(client, target_group_link)
                    try:
                        add_users(client, group_username, phone, index, total_accounts)
                    except FloodWaitError as e:
                        wait_time = e.seconds
                        print(f"[{phone}] ⚠️ Terkena FloodWaitError! Tunggu {wait_time} detik")
                        flood_status[index] = True
                        flood_wait_until[index] = now + wait_time
                    except PeerFloodError:
                        print(f"[{phone}] ⚠️ Terkena PeerFloodError! Tunggu {delay_between_batches} detik")
                        flood_status[index] = True
                        flood_wait_until[index] = now + delay_between_batches
                finally:
                    client.disconnect()
            else:
                print(f"[{phone}] ❌ Tidak berhasil login / otorisasi gagal")
            
            # Short delay between accounts
            print(f"\n⏳ Jeda {delay_between_batches//60} menit sebelum akun berikutnya...")
            time.sleep(delay_between_batches)
        
        if all_flooded:
            # All accounts are flooded, wait before retrying
            wait_time = delay_between_batches
            print(f"\n⚠️ Semua akun kena flood. Tunggu {wait_time//60} menit sebelum coba ulang semua.")
            time.sleep(wait_time)

if __name__ == '__main__':
    print("""
    ======================================
    Telegram Member Adder - Improved Version
    ======================================
    """)
    main()