import requests
import json
import time
from .config import Config
from .utils import load_private_key, get_timestamp, sign_params

class BinanceClient:
    def __init__(self, base_url=Config.PAPI_URL):
        self.base_url = base_url
        self.api_key = Config.API_KEY
        self.private_key = load_private_key(Config.PRIVATE_KEY_PATH)
        self.session = requests.Session()
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        })
        self.time_offset = 0
        self.sync_time()

    def get_timestamp(self):
        return int((time.time() * 1000) + self.time_offset)

    def sync_time(self):
        """
        Synchronizes local time with Binance server time.
        Uses FAPI endpoint as it is publicly available and reliable for time.
        """
        try:
            # Using FAPI public endpoint for time sync
            response = requests.get("https://fapi.binance.com/fapi/v1/time")
            response.raise_for_status()
            server_time = response.json()['serverTime']
            local_time = int(time.time() * 1000)
            # Calculate offset: server_time = local_time + offset
            # offset = server_time - local_time
            self.time_offset = server_time - local_time
            # print(f"系统时间已同步。本地时间偏移: {self.time_offset}ms")
        except Exception as e:
            print(f"时间同步失败: {e}")

    def _request(self, method, endpoint, params=None, signed=False):
        if params is None:
            params = {}

        # Add timestamp and signature if signed
        if signed:
            params['timestamp'] = self.get_timestamp()
            params['signature'] = sign_params(params, self.private_key)

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(method, url, params=params,timeout=3)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"请求失败 (Request Failed): {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    print(f"服务器返回错误 (Server Error): {json.dumps(error_data, indent=4)}")
                except ValueError:
                    print(f"服务器返回内容 (Server Content): {e.response.text}")
            raise
        except ValueError as e:
            print(f"JSON解析失败 (JSON Parse Failed): {e}")
            raise
        except Exception as e:
            print(f"发生未知错误 (Unknown Error): {e}")
            raise

    def get(self, endpoint, params=None, signed=False):
        return self._request('GET', endpoint, params, signed)

    def post(self, endpoint, params=None, signed=False):
        return self._request('POST', endpoint, params, signed)

    def put(self, endpoint, params=None, signed=False):
        return self._request('PUT', endpoint, params, signed)

    def delete(self, endpoint, params=None, signed=False):
        return self._request('DELETE', endpoint, params, signed)
