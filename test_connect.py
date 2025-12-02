#!/usr/bin/env python3

import base64
import json
import os
from dotenv import load_dotenv
import requests
import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key

load_dotenv('.env', override=True)

# Set up authentication
API_KEY=os.getenv('API_KEY')
PRIVATE_KEY_PATH=os.getenv('PRIVATE_KEY_PATH')

with open(PRIVATE_KEY_PATH, 'rb') as f:
    private_key = load_pem_private_key(data=f.read(),
                                       password=None)

# Set up the request parameters
params = {
    
}

# Timestamp the request
timestamp = int(time.time() * 1000) # UNIX timestamp in milliseconds
params['timestamp'] = timestamp

# Sign the request
payload = '&'.join([f'{param}={value}' for param, value in params.items()])
signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
params['signature'] = signature.decode('ascii')

# Send the request
headers = {
    'X-MBX-APIKEY': API_KEY,
}
try:
    response = requests.get(
        'https://papi.binance.com/papi/v1/balance',
        headers=headers,
        params=params,
    )
    response.raise_for_status()
    data = response.json()
    print(json.dumps(data, indent=4))
except requests.exceptions.RequestException as e:
    print(f"请求失败: {e}")
except ValueError as e:
    print(f"JSON解析失败: {e}")