import os
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Literal, Dict, Tuple, Optional

from binance_api import build_client_from_env, BinanceMarketData, BinanceTrading, OrderRequest

# --- 配置区域 ---
SYMBOL = "ETHUSDC"
QUANTITY = Decimal("0.02")  # 单笔数量
GRID_STEP = Decimal("2")    # 网格间距 (整数)
ORDER_COUNT = 3            # 单侧挂单数量
# 策略方向: 
# "LONG": 下方买入开仓，上方卖出平仓(ReduceOnly)
# "SHORT": 上方卖出开仓，下方买入平仓(ReduceOnly)
# "NEUTRAL": 下方买入开仓，上方卖出开仓
DIRECTION: Literal["LONG", "SHORT", "NEUTRAL"] = "SHORT" 
LOOP_INTERVAL = 10

# 止盈止损配置 (百分比)
# 止盈: Limit Order (ReduceOnly)
# 止损: Stop Market Order (ReduceOnly)
TP_PERCENT = Decimal("0.02")  # 2% 止盈
SL_PERCENT = Decimal("0.01")  # 1% 止损
# ----------------

class SimpleGrid:
    def __init__(self):
        # prod=True/False 取决于你的 .env.local 配置，这里默认 False (测试网) 或根据实际情况调整
        # 假设用户在 .env.local 里配置的是实盘 key，或者想用实盘，这里需要注意。
        # 既然用户提到 ETH 价格 3000，应该是实盘。
        # build_client_from_env(prod=True) 会读取 PROD 环境变量。
        # 为了安全，先尝试读取默认环境，用户需自行确保 .env.local 正确。
        # 如果用户之前用的是测试网，这里可能需要调整。
        # 观察之前的 client.py，build_client_from_env 默认 prod=False。
        # 我们先假设用户配置在默认变量里，或者我们提供一个开关。
        # 鉴于用户之前的上下文，我们默认使用 prod=True 尝试连接实盘，或者让用户确认。
        # 但为了脚本通用性，我先用 prod=True，因为 3000 价格肯定是主网。
        self.client = build_client_from_env(prod=False)
            
        self.market = BinanceMarketData(self.client)
        self.trade = BinanceTrading(self.client)

    def start_loop(self):
        print(f"启动网格策略循环: {SYMBOL}, 方向: {DIRECTION}")
        print(f"止盈: {TP_PERCENT*100}%, 止损: {SL_PERCENT*100}%")
        
        while True:
            try:
                should_continue = self.run()
                if not should_continue:
                    print("策略停止条件触发，退出循环。")
                    break
            except Exception as e:
                print(f"运行出错: {e}")
            
            print("=============")
            time.sleep(LOOP_INTERVAL)

    def run(self) -> bool:
        """
        执行一次策略逻辑。
        Returns:
            bool: True 继续运行, False 停止运行
        """
        # 1. 获取当前价格
        try:
            ticker = self.market.get_price_ticker(symbol=SYMBOL)
            current_price = Decimal(ticker["price"])
        except Exception as e:
            print(f"获取价格失败: {e}")
            return True

        # 中心价格对齐到网格 (全局对齐)
        # 这样无论当前价格是多少，网格线总是落在 GRID_STEP 的倍数上
        center_price = (current_price / GRID_STEP).quantize(Decimal("1."), rounding=ROUND_HALF_UP) * GRID_STEP
        print(f"当前市价: {current_price}, 网格中心: {center_price}")

        # 2. 获取当前持仓 (用于单侧平仓检查 & 止盈止损)
        position_amt = Decimal("0")
        entry_price = Decimal("0")
        try:
            positions = self.trade.get_position_risk(symbol=SYMBOL)
            # 接口可能返回列表
            if isinstance(positions, list):
                for pos in positions:
                    if pos["symbol"] == SYMBOL:
                        position_amt = Decimal(pos["positionAmt"])
                        entry_price = Decimal(pos["entryPrice"])
                        break
            elif isinstance(positions, dict):
                 if positions.get("symbol") == SYMBOL:
                    position_amt = Decimal(positions["positionAmt"])
                    entry_price = Decimal(positions["entryPrice"])
        except Exception as e:
            print(f"获取持仓失败: {e}")
            return True
        
        print(f"当前持仓: {position_amt} {SYMBOL}, 均价: {entry_price}")

        # 3. 检查是否触发止盈止损 (停止条件)
        # 如果持仓不为0，检查价格是否越界
        if position_amt != 0 and entry_price > 0:
            if DIRECTION == "LONG":
                tp_price = entry_price * (1 + TP_PERCENT)
                sl_price = entry_price * (1 - SL_PERCENT)
                if current_price >= tp_price:
                    print(f"触发止盈! 当前价 {current_price} >= {tp_price}")
                    return False
                if current_price <= sl_price:
                    print(f"触发止损! 当前价 {current_price} <= {sl_price}")
                    return False
            elif DIRECTION == "SHORT":
                tp_price = entry_price * (1 - TP_PERCENT)
                sl_price = entry_price * (1 + SL_PERCENT)
                if current_price <= tp_price:
                    print(f"触发止盈! 当前价 {current_price} <= {tp_price}")
                    return False
                if current_price >= sl_price:
                    print(f"触发止损! 当前价 {current_price} >= {sl_price}")
                    return False

        # 4. 获取当前挂单
        open_orders = self.trade.get_open_orders(symbol=SYMBOL)
        # 建立查找表: {(price, side): order_id}
        existing_orders: Dict[Tuple[Decimal, str], int] = {}
        
        # 统计已挂出的平仓单数量，用于额度控制
        pending_close_qty = Decimal("0")

        for o in open_orders:
            p = Decimal(o["price"]).normalize() if "price" in o else Decimal("0")
            s = o["side"]
            o_type = o["type"]
            
            # 记录 Limit 单
            if o_type == "LIMIT":
                existing_orders[(p, s)] = o["orderId"]
            
            # 统计 ReduceOnly 单量 (用于网格平仓额度控制，不包含止盈止损单)
            # 只统计 LIMIT 单，忽略 STOP_MARKET / TAKE_PROFIT_MARKET 等条件单
            if o.get("reduceOnly") is True and o_type == "LIMIT":
                if DIRECTION == "LONG" and s == "SELL":
                    pending_close_qty += Decimal(o["origQty"])
                elif DIRECTION == "SHORT" and s == "BUY":
                    pending_close_qty += Decimal(o["origQty"])

        print(f"当前挂单数: {len(open_orders)}")

        # 5. 管理止盈止损单 (TP/SL)
        tpsl_order_ids = set()
        if position_amt != 0:
            tpsl_order_ids = self._manage_tpsl(position_amt, entry_price, open_orders)

        # 6. 撤销远处的挂单 (回收保证金 & 释放仓位)
        self._cancel_distant_orders(open_orders, center_price, tpsl_order_ids)

        # 计算剩余可平仓额度 (用于网格)
        available_close_qty = Decimal("0")
        if DIRECTION == "LONG":
            if position_amt > 0:
                available_close_qty = position_amt - pending_close_qty
        elif DIRECTION == "SHORT":
            if position_amt < 0:
                available_close_qty = abs(position_amt) - pending_close_qty
        
        if available_close_qty < 0:
            available_close_qty = Decimal("0")

        print(f"剩余可挂平仓额度: {available_close_qty}")

        orders_to_place: List[OrderRequest] = []

        # --- 生成网格 ---
        
        # 下方网格 (Price < Center)
        for i in range(1, ORDER_COUNT + 1):
            price = center_price - (i * GRID_STEP)
            side = "BUY"
            reduce_only = False
            
            # 逻辑判断
            if DIRECTION == "LONG":
                # 做多：下方买入开仓
                pass 
            elif DIRECTION == "SHORT":
                # 做空：下方买入平仓
                reduce_only = True
                if available_close_qty < QUANTITY:
                    # 额度不足，跳过
                    continue
            elif DIRECTION == "NEUTRAL":
                # 中性：下方买入开仓
                pass

            # 检查是否已存在
            if (price, side) in existing_orders:
                continue
            
            # 如果是平仓单，扣除额度
            if reduce_only:
                available_close_qty -= QUANTITY

            orders_to_place.append(self._create_order_req(price, side, reduce_only))

        # 上方网格 (Price > Center)
        for i in range(1, ORDER_COUNT + 1):
            price = center_price + (i * GRID_STEP)
            side = "SELL"
            reduce_only = False

            # 逻辑判断
            if DIRECTION == "LONG":
                # 做多：上方卖出平仓
                reduce_only = True
                if available_close_qty < QUANTITY:
                    continue
            elif DIRECTION == "SHORT":
                # 做空：上方卖出开仓
                pass
            elif DIRECTION == "NEUTRAL":
                # 中性：上方卖出开仓
                pass

            if (price, side) in existing_orders:
                continue

            if reduce_only:
                available_close_qty -= QUANTITY

            orders_to_place.append(self._create_order_req(price, side, reduce_only))

        # --- 执行下单 ---
        if not orders_to_place:
            print("没有需要新增的挂单。")
            return True

        print(f"计划新增挂单: {len(orders_to_place)} 个")
        
        # 批量下单，每批 5 个
        batch = []
        for req in orders_to_place:
            batch.append(req)
            if len(batch) == 5:
                self._send_batch(batch)
                batch = []
        
        if batch:
            self._send_batch(batch)
            
        return True

    def _manage_tpsl(self, position_amt: Decimal, entry_price: Decimal, open_orders: List[Dict]) -> set:
        """
        检查并挂出止盈止损单。
        Returns:
            set: 识别到的 TP/SL 订单 ID 集合
        """
        # 计算目标价格
        tp_price = Decimal("0")
        sl_price = Decimal("0")
        tp_side = ""
        sl_side = ""
        
        if position_amt > 0: # Long
            tp_price = (entry_price * (1 + TP_PERCENT)).quantize(Decimal("0.01"))
            sl_price = (entry_price * (1 - SL_PERCENT)).quantize(Decimal("0.01"))
            tp_side = "SELL"
            sl_side = "SELL"
        elif position_amt < 0: # Short
            tp_price = (entry_price * (1 - TP_PERCENT)).quantize(Decimal("0.01"))
            sl_price = (entry_price * (1 + SL_PERCENT)).quantize(Decimal("0.01"))
            tp_side = "BUY"
            sl_side = "BUY"
        
        # 检查是否已存在 TP/SL
        has_tp = False
        has_sl = False
        tpsl_ids = set()
        
        for o in open_orders:
            o_side = o["side"]
            o_type = o["type"]
            o_id = o["orderId"]
            
            # 检查止盈 (TAKE_PROFIT_MARKET)
            if o_type == "TAKE_PROFIT_MARKET" and o_side == tp_side:
                sp = Decimal(o["stopPrice"])
                if abs(sp - tp_price) / tp_price < Decimal("0.001"):
                    has_tp = True
                    tpsl_ids.add(o_id)
            
            # 检查止损 (STOP_MARKET)
            if o_type == "STOP_MARKET" and o_side == sl_side:
                sp = Decimal(o["stopPrice"])
                if abs(sp - sl_price) / sl_price < Decimal("0.001"):
                    has_sl = True
                    tpsl_ids.add(o_id)

        # 挂单
        # 挂单
        if not has_tp:
            print(f"挂出止盈单: {tp_side} {tp_price}")
            try:
                res = self.trade.create_order(OrderRequest(
                    symbol=SYMBOL,
                    side=tp_side,
                    order_type="TAKE_PROFIT_MARKET",
                    quantity=abs(position_amt),
                    stop_price=tp_price,
                    reduce_only=True
                ))
                if "orderId" in res:
                    tpsl_ids.add(res["orderId"])
            except Exception as e:
                print(f"挂止盈失败: {e}")
        if not has_sl:
            print(f"挂出止损单: {sl_side} {sl_price}")
            try:
                res = self.trade.create_order(OrderRequest(
                    symbol=SYMBOL,
                    side=sl_side,
                    order_type="STOP_MARKET",
                    quantity=abs(position_amt),
                    stop_price=sl_price,
                    reduce_only=True
                ))
                if "orderId" in res:
                    tpsl_ids.add(res["orderId"])
            except Exception as e:
                print(f"挂止损失败: {e}")
        
        return tpsl_ids

    def _cancel_distant_orders(self, open_orders: List[Dict], center_price: Decimal, exclude_ids: set):
        """
        撤销超出网格范围的订单。
        """
        # 定义保留范围 (ORDER_COUNT + 2)
        buffer = 1
        max_dist = (ORDER_COUNT + buffer) * GRID_STEP
        
        min_valid_price = center_price - max_dist
        max_valid_price = center_price + max_dist
        
        cancel_list = []
        
        for o in open_orders:
            o_id = o["orderId"]
            if o_id in exclude_ids:
                continue
            
            # 仅处理 LIMIT 单 (网格单)
            if o["type"] != "LIMIT":
                continue
                
            price = Decimal(o["price"])
            side = o["side"]
            
            should_cancel = False
            
            # 逻辑:
            # LONG 策略: 
            #   - 撤销 Price < min_valid 的 BUY 单 (回收保证金)
            #   - 撤销 Price > max_valid 的 SELL 单 (释放仓位额度)
            # SHORT 策略:
            #   - 撤销 Price > max_valid 的 SELL 单 (回收保证金)
            #   - 撤销 Price < min_valid 的 BUY 单 (释放仓位额度)
            
            if price < min_valid_price:
                # 价格过低
                if DIRECTION == "LONG" and side == "BUY":
                    should_cancel = True
                elif DIRECTION == "SHORT" and side == "BUY":
                    should_cancel = True
                elif DIRECTION == "NEUTRAL" and side == "BUY":
                    should_cancel = True
                    
            elif price > max_valid_price:
                # 价格过高
                if DIRECTION == "LONG" and side == "SELL":
                    should_cancel = True
                elif DIRECTION == "SHORT" and side == "SELL":
                    should_cancel = True
                elif DIRECTION == "NEUTRAL" and side == "SELL":
                    should_cancel = True
            
            if should_cancel:
                cancel_list.append(o_id)
        
        if cancel_list:
            print(f"发现 {len(cancel_list)} 个远端订单，准备撤销...")
            # 批量撤销，每批 10 个
            for i in range(0, len(cancel_list), 10):
                batch_ids = cancel_list[i:i+10]
                try:
                    self.trade.cancel_batch_orders(symbol=SYMBOL, order_id_list=batch_ids)
                    print(f"已撤销批次: {batch_ids}")
                except Exception as e:
                    print(f"撤单失败: {e}")

    def _send_batch(self, batch):
        try:
            res = self.trade.create_batch_orders(batch)
            # 简单的结果检查
            success_cnt = 0
            if isinstance(res, list):
                for r in res:
                    if "orderId" in r:
                        success_cnt += 1
                    else:
                        print(f"单笔下单错误: {r}")
            print(f"批量提交完成，成功: {success_cnt}/{len(batch)}")
        except Exception as e:
            print(f"批量下单请求失败: {e}")

    def _create_order_req(self, price: Decimal, side: str, reduce_only: bool) -> OrderRequest:
        return OrderRequest(
            symbol=SYMBOL,
            side=side,
            order_type="LIMIT",
            quantity=QUANTITY,
            price=price,
            time_in_force="GTX", # Post Only (Maker Only)
            reduce_only=reduce_only
        )

if __name__ == "__main__":
    SimpleGrid().start_loop()
