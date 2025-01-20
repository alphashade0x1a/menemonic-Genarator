import os
import logging
import asyncio
from web3 import Web3
from mnemonic import Mnemonic
from eth_account import Account
from dotenv import load_dotenv
from aiohttp import ClientSession, ClientTimeout
import time

# Load environment variables
load_dotenv()

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
INFURA_PROJECT_ID = '426db37db1d047a5862bcada33e9c457'
INFURA_URL = f'https://mainnet.infura.io/v3/{INFURA_PROJECT_ID}'
RETRY_DELAY = 2  # seconds
MAX_CONCURRENT_TASKS = os.cpu_count() * 2  # Adjust based on system capabilities

# Connect to Ethereum network
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
if not w3.is_connected():
    logging.error("Failed to connect to Ethereum network.")
    raise SystemExit("Cannot connect to Ethereum network")

# Function to generate a mnemonic phrase
def generate_mnemonic():
    mnemo = Mnemonic("english")
    return mnemo.generate(strength=128)

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
    try:
        url = INFURA_URL
        payload = {
            'jsonrpc': '2.0',
            'method': 'eth_getBalance',
            'params': [address, 'latest'],
            'id': 1
        }
        timeout = ClientTimeout(total=10)  # Set timeout for requests
        async with session.post(url, json=payload, timeout=timeout) as response:
            if response.status != 200:
                logging.error(f"HTTP error: {response.status}")
                return False
            data = await response.json()
            logging.debug(f"Response data: {data}")
            balance = int(data['result'], 16)  # Convert hex balance to integer
            return balance > 0
    except Exception as e:
        logging.error(f"Error checking balance for {address}: {e}")
        return False

# Worker function to generate mnemonic and attempt login
async def try_login(session):
    while True:
        mnemonic = generate_mnemonic()
        account = mnemonic_to_private_key(mnemonic)
        if account is None:
            logging.error("Failed to create account from mnemonic.")
            await asyncio.sleep(RETRY_DELAY)
            continue

        logging.info(f"Trying account: {account.address}")

        if await check_account_balance(session, account.address):
            logging.info(f"Successfully logged in with mnemonic: {mnemonic}")
            return mnemonic  # Return the successful mnemonic
        else:
            logging.info("Login failed, generating a new mnemonic...")
            await asyncio.sleep(RETRY_DELAY)  # Delay between retries

# Main function to manage parallel workers
async def main():
    async with ClientSession() as session:
        # Use asyncio to handle multiple workers
        tasks = [asyncio.create_task(try_login(session)) for _ in range(MAX_CONCURRENT_TASKS)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Find the first successful mnemonic
        for result in results:
            if isinstance(result, str):
                logging.info(f"Successful mnemonic found: {result}")
                return

        logging.info("No successful mnemonic found.")

if __name__ == "__main__":
    asyncio.run(main())
