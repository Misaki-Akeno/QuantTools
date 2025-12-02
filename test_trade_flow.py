#!/usr/bin/env python3
import time
import json
from binance_app.um_api import UMFuturesClient
from binance_app.market_api import UMMarketClient

def main():
    # Initialize clients
    market_client = UMMarketClient()
    trade_client = UMFuturesClient()
    
    # Sync time to avoid timestamp errors
    print("--- 同步服务器时间 ---")
    trade_client.sync_time()

    symbol = 'ETHUSDC'

    # 1. Get Market Price
    print(f"--- 获取 {symbol} 当前价格 ---")
    price_info = market_client.get_ticker_price(symbol)
    if not price_info:
        print("无法获取价格，退出。")
        return
    
    current_price = float(price_info['price'])
    print(f"当前价格: {current_price}")

    # 2. Calculate Safe Price (e.g., 50% of current price for BUY)
    # Ensure price precision (tick size). For ETHUSDC it's usually 0.01 or 0.1. 
    # We use 2 decimal places to be safe for USDC pairs.
    safe_price = round(current_price * 0.5, 2)
    print(f"下单价格 (安全价格): {safe_price}")

    # 3. Place Limit Order
    print(f"\n--- 尝试在 {safe_price} 下单买入 {symbol} ---")
    # Quantity: Ensure step size. 0.01 is usually safe for ETH.
    quantity = 0.02
    
    order = trade_client.new_order(
        symbol=symbol,
        side='BUY',
        type='LIMIT',
        quantity=quantity,
        price=safe_price,
        positionSide='LONG',
        timeInForce='GTC'
    )
    
    if not order:
        print("下单失败，退出。")
        return

    print("下单成功:")
    print(json.dumps(order, indent=4))
    
    order_id = order.get('orderId')
    if not order_id:
        print("未获取到订单ID，无法撤单。")
        return

    # 4. Cancel Order
    print(f"\n--- 撤销订单 {order_id} ---")
    # Sleep briefly to ensure order is processed
    time.sleep(1)
    
    cancel_result = trade_client.cancel_order(symbol=symbol, orderId=order_id)
    if cancel_result:
        print("撤单成功:")
        print(json.dumps(cancel_result, indent=4))
    else:
        print("撤单失败，请手动检查！")

if __name__ == "__main__":
    main()
