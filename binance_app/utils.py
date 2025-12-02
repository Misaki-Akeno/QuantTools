import base64
import time
from cryptography.hazmat.primitives.serialization import load_pem_private_key
def load_private_key(private_key_path):
    """Loads the private key from the specified path."""
    with open(private_key_path, 'rb') as f:
        private_key = load_pem_private_key(data=f.read(), password=None)
    return private_key

def get_timestamp():
    """Returns the current timestamp in milliseconds."""
    return int(time.time() * 1000)

def sign_params(params, private_key):
    """
    Signs the request parameters using the private key.
    Adds 'signature' to the params dictionary.
    """
    # Construct the payload string exactly as in the example
    payload = '&'.join([f'{param}={value}' for param, value in params.items()])
    
    # Sign
    # Assuming Ed25519 key based on the usage in test_connect.py (single argument sign)
    signature = base64.b64encode(private_key.sign(payload.encode('ASCII')))
    
    return signature.decode('ascii')
