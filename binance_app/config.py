import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv('.env', override=True)

class Config:
    API_KEY = os.getenv('API_KEY')
    PRIVATE_KEY_PATH = os.getenv('PRIVATE_KEY_PATH')
    
    # Base URLs
    PAPI_URL = "https://papi.binance.com"
    FAPI_URL = "https://fapi.binance.com"

    if not API_KEY:
        raise ValueError("API_KEY not found in environment variables")
    if not PRIVATE_KEY_PATH:
        raise ValueError("PRIVATE_KEY_PATH not found in environment variables")
    if not os.path.exists(PRIVATE_KEY_PATH):
        raise FileNotFoundError(f"Private key file not found at: {PRIVATE_KEY_PATH}")
