#!/usr/bin/env python3
import json
from binance_app.um_account_api import UMAccountClient

def main():

    # Initialize the client
    client = UMAccountClient()

    print("--- 获取账户余额 ---")
    balance = client.get_balance()
    if balance:
        print(json.dumps(balance, indent=4))
    
    print("\n--- 获取账户信息 ---")
    account_info = client.get_account_info()
    if account_info:
        # Print a summary or the whole thing
        print(json.dumps(account_info, indent=4))

    # Example of placing an order (Commented out for safety)
    # print("\n--- 下单示例 ---")
    # order = client.new_order(
    #     symbol='BTCUSDT',
    #     side='BUY',
    #     type='LIMIT',
    #     quantity=0.001,
    #     price=50000,
    #     timeInForce='GTC'
    # )
    # if order:
    #     print(json.dumps(order, indent=4))

if __name__ == "__main__":
    main()
