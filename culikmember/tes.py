from telethon.sync import TelegramClient
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError, UserBotError
from telethon.tl.functions.channels import InviteToChannelRequest, GetFullChannelRequest
import csv
import time
import logging
import traceback

# Konfigurasi awal
api_id = 25540929
api_hash = "57b0e14140418e8d350790c0962c59ea"
phone_numbers = ["+6282210517552"]
group_username = "@LPMHASTLE2"
target_group_link = "@Lpm_Roleplayer_23"
csv_file = 'members.csv'
num_users_per_account = 60
delay_between_adds = 40
delay_between_batches = 1800

# Logging
logging.basicConfig(filename='telegram_bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scrape_users(client, target_group_link):
    try:
        target_group = client(GetFullChannelRequest(target_group_link)).chats[0]
        participants = client.get_participants(target_group, aggressive=True)
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'username', 'access_hash', 'name'])
            for user in participants:
                writer.writerow([user.id, user.username or "", user.access_hash, user.first_name or ""])
        logging.info(f"Successfully scraped users from {target_group_link}")
        print(f"Successfully scraped users from {target_group_link}")
    except Exception as e:
        logging.error(f"Failed to scrape users from {target_group_link}: {e}")
        traceback.print_exc()

def add_users(client, target_group, num_users_per_account=60):
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            users = list(csv.reader(f))[1:]
        for i, user in enumerate(users):
            if i % num_users_per_account == 0 and i > 0:
                logging.info("Sleeping for a while to avoid rate limiting...")
                print("Sleeping for a while to avoid rate limiting...")
                time.sleep(delay_between_batches)

            try:
                user_to_add = client.get_input_entity(int(user[0]))
                client(InviteToChannelRequest(target_group, [user_to_add]))
                logging.info(f"Added {user[1]} (ID: {user[0]})")
                print(f"Added {user[1]} (ID: {user[0]})")
                time.sleep(delay_between_adds)
            except PeerFloodError:
                logging.error("Getting Flood Error from Telegram. Script is stopping now. Try again later.")
                print("Getting Flood Error from Telegram. Script is stopping now. Try again later.")
                break
            except UserPrivacyRestrictedError:
                logging.warning(f"User {user[1]} has privacy restrictions")
                print(f"User {user[1]} has privacy restrictions")
            except UserBotError:
                logging.error("Bots cannot perform this action. Please use a user account.")
                print("Bots cannot perform this action. Please use a user account.")
                break
            except Exception as e:
                logging.error(f"Error: {e}")
                traceback.print_exc()
    except Exception as e:
        logging.error(f"Failed to read CSV file or add users: {e}")
        traceback.print_exc()

def login_with_otp(client, phone):
    try:
        client.connect()
        if not client.is_user_authorized():
            client.send_code_request(phone)
            otp_code = input(f'Enter the OTP for {phone}: ')
            client.sign_in(phone, otp_code)
        return client
    except Exception as e:
        logging.error(f"Failed to connect or login with {phone}: {e}")
        traceback.print_exc()

def main():
    for phone in phone_numbers:
        client = TelegramClient(phone, api_id, api_hash)
        client = login_with_otp(client, phone)
        if client.is_user_authorized():
            try:
                scrape_users(client, target_group_link)
                add_users(client, group_username, num_users_per_account)
            finally:
                client.disconnect()
        else:
            logging.warning(f"Could not authorize {phone}. Skipping...")

if __name__ == '__main__':
    main()
