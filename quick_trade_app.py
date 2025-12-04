import flet as ft
from flet import Colors
import threading
import time
import concurrent.futures
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from binance_app.um_account_api import UMAccountClient
from binance_app.um_trade_api import UMTradeClient
from binance_app.market_api import UMMarketClient

PRICE_MATCH_BUTTONS = [
    {"label": "对手价1", "match_key": "OPPONENT", "tif": "GTC"},
    {"label": "同向价1", "match_key": "QUEUE", "tif": "GTX"},
    {"label": "对手价5", "match_key": "OPPONENT_5", "tif": "GTC"},
    {"label": "同向价5", "match_key": "QUEUE_5", "tif": "GTX"},
]


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def format_price(price, tick_size):
    """Format price according to tick_size"""
    d_price = Decimal(str(price))
    d_tick = Decimal(str(tick_size))
    # Round to nearest tick
    rounded = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick
    return f"{rounded.quantize(d_tick)}"

def format_qty(qty, step_size):
    """Format quantity according to step_size"""
    d_qty = Decimal(str(qty))
    d_step = Decimal(str(step_size))
    # Round down for quantity to be safe
    rounded = (d_qty / d_step).quantize(Decimal("1"), rounding=ROUND_FLOOR) * d_step
    return f"{rounded.quantize(d_step)}"


def main(page: ft.Page):
    page.title = "ETHUSDC 交易终端"
    page.horizontal_alignment = "stretch"
    page.window.always_on_top = True
    page.window.width = 335
    page.window.height = 700
    page.theme_mode = ft.ThemeMode.DARK
    page.fonts = {
        "Maple": "fonts/MapleMono-NF-CN-Regular.ttf",
        "noto": "https://raw.githubusercontent.com/notofonts/noto-cjk/refs/heads/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
    }

    page.theme = ft.Theme(font_family="Maple")
    page.padding = 10
    page.update()

    auto_execution_running = False
    auto_timer = None

    # Cleanup on close
    def on_close(_):
        nonlocal auto_execution_running, auto_timer
        auto_execution_running = False
        if auto_timer:
            auto_timer.cancel()
    
    page.on_close = on_close

    account_client = UMAccountClient()
    trade_client = UMTradeClient()
    market_client = UMMarketClient()

    # --- Shared State ---
    state = {
        "symbol": "ETHUSDC",
        "last_order": {"order_id": None, "client_id": None},
        "position": None,   # Current position data
        "ticker": None,     # Current ticker data
        "filters": {
            "tick_size": "0.01",
            "step_size": "0.001"
        },
        "stop_loss": {"order_id": None, "trigger_price": None},
        "loop_count": 0
    }

    # --- UI Components ---
    status_text = ft.Text("", size=12)

    def push_status(message: str, success: bool = True):
        status_text.value = f"[{time.strftime('%H:%M:%S')}] {message}"
        status_text.color = Colors.GREEN if success else Colors.RED
        status_text.update()

    def notify_error(message: str):
        push_status(message, success=False)

    def update_filters():
        try:
            info = market_client.get_exchange_info()
            if not info: return
            
            target_symbol = state["symbol"]
            symbol_info = next((s for s in info.get("symbols", []) if s["symbol"] == target_symbol), None)
            
            if symbol_info:
                # Extract filters
                price_filter = next((f for f in symbol_info["filters"] if f["filterType"] == "PRICE_FILTER"), None)
                lot_size = next((f for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE"), None)
                
                if price_filter:
                    state["filters"]["tick_size"] = price_filter["tickSize"]
                if lot_size:
                    state["filters"]["step_size"] = lot_size["stepSize"]
                
                push_status(f"{target_symbol}: {state['filters']['tick_size']}, {state['filters']['step_size']}")
        except Exception as e:
            print(f"Failed to update filters: {e}")

    def ui_error_handler(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if "insufficient balance" in error_msg.lower():
                     error_msg = "余额不足"
                elif "timeout" in error_msg.lower():
                     error_msg = "请求超时"
                print(f"UI Exception: {e}")
                notify_error(f"Error: {error_msg}")
        return wrapper

    # --- Shared Controls ---
    symbol_input = ft.TextField(
        label="交易对",
        value="ETHUSDC",
        text_size=14,
        content_padding=10,
        expand=True,
        on_submit=lambda e: [state.update({"symbol": e.control.value.upper()}), update_filters(), refresh_data()]
    )

    # Info Display
    balance_text = ft.Text("权益: --/--", size=13)
    ticker_price_text = ft.Text("现价: --", size=13, weight=ft.FontWeight.BOLD, color=Colors.YELLOW)
    position_info_text = ft.Text("持仓: --", size=13)
    
    @ui_error_handler
    def refresh_data(_=None):
        # 1. Get Account Info
        account_info = account_client.get_account_info()
        if account_info:
            state["account"] = account_info
            equity = safe_float(account_info.get("accountEquity"))
            avail = safe_float(account_info.get("totalAvailableBalance"))
            balance_text.value = f"权益: {avail:.2f}/{equity:.2f}"

        # 2. Get UM Account Info (Positions)
        um_account_info = account_client.get_um_account_info()
        if um_account_info:
            # Find Position
            positions = um_account_info.get("positions") or []
            pos = next((p for p in positions if p.get("symbol") == state["symbol"]), None)
            state["position"] = pos
            if pos:
                amt = safe_float(pos.get("positionAmt"))
                entry = safe_float(pos.get("entryPrice"))
                pnl = safe_float(pos.get("unrealizedProfit"))
                position_info_text.value = f"持仓: {amt} @ {entry:.2f} (PnL: {pnl:.2f})"
                position_info_text.color = Colors.GREEN if pnl >= 0 else Colors.RED
            else:
                position_info_text.value = "持仓: 无"
                position_info_text.color = Colors.WHITE

        # 2. Get Ticker
        ticker = market_client.get_ticker_price(state["symbol"])
        if ticker:
            state["ticker"] = ticker
            price = safe_float(ticker.get("price"))
            ticker_price_text.value = f"现价: {price:.2f}"

        balance_text.update()
        ticker_price_text.update()
        position_info_text.update()
    
    refresh_btn = ft.TextButton("刷新", on_click=lambda e: [state.update({"symbol": symbol_input.value.upper()}), update_filters(), refresh_data()], style=ft.ButtonStyle(color=ft.Colors.GREEN_300))

    # --- Tab 1: Quick Trade ---
    qt_qty_field = ft.TextField(label="数量", value="0.01", width=100, height=40, content_padding=10, text_size=14)
    qt_side_switch = ft.Switch(label="买入/卖出", value=True, active_color=Colors.GREEN,inactive_thumb_color=Colors.RED)
    qt_reduce_checkbox = ft.Checkbox(label="只减仓", value=False)
    qt_last_order_text = ft.Text("上次: --", size=12)

    @ui_error_handler
    def qt_place_order(match_key, tif):
        qty = safe_float(qt_qty_field.value)
        if qty <= 0: return notify_error("数量无效")
        
        step_size = state["filters"]["step_size"]
        formatted_qty = format_qty(qty, step_size)
        
        side = "BUY" if qt_side_switch.value else "SELL"
        
        res = trade_client.new_order(
            symbol=state["symbol"],
            side=side,
            type="LIMIT",
            quantity=formatted_qty,
            timeInForce=tif,
            priceMatch=match_key,
            reduceOnly=qt_reduce_checkbox.value,
            newOrderRespType="RESULT"
        )
        if res:
            state["last_order"] = {"order_id": res.get("orderId"), "client_id": res.get("clientOrderId")}
            qt_last_order_text.value = f"上次: {side} {formatted_qty} @ {match_key}"
            push_status("快速下单成功")
            refresh_data()

    @ui_error_handler
    def qt_cancel_all(_):
        trade_client.cancel_all_orders(state["symbol"])
        push_status("撤销全部订单成功")
        refresh_data()

    qt_buttons = [
        ft.ElevatedButton(
            text=cfg["label"], 
            on_click=lambda _, k=cfg["match_key"], t=cfg["tif"]: qt_place_order(k, t),
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5)),
            width=100
        ) for cfg in PRICE_MATCH_BUTTONS
    ]

    tab_quick = ft.Container(
        content=ft.Column([
            ft.Row([qt_qty_field, qt_side_switch, qt_reduce_checkbox], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text("价格匹配下单 (GTC/GTX)", size=14, weight=ft.FontWeight.BOLD),
            ft.Row(qt_buttons[:2], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row(qt_buttons[2:], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            qt_last_order_text
        ], spacing=15),
        padding=10
    )

    # --- Tab 2: Grid Trade ---
    gt_n_field = ft.TextField(label="单边数量", value="2", expand=True, height=40, content_padding=10, text_size=14)
    gt_buy_interval_field = ft.TextField(label="买入网格间隔", value="1", expand=True, height=40, content_padding=10, text_size=14)
    gt_sell_interval_field = ft.TextField(label="卖出网格间隔", value="1", expand=True, height=40, content_padding=10, text_size=14)
    gt_buy_qty_field = ft.TextField(label="买入数量", value="0.008", expand=True, height=40, content_padding=10, text_size=14)
    gt_sell_qty_field = ft.TextField(label="卖出数量", value="0.008", expand=True, height=40, content_padding=10, text_size=14)
    gt_base_price_field = ft.TextField(label="基准价格", value="", expand=True, height=40, content_padding=10, text_size=14, hint_text="留空=动态基准")
    gt_stop_loss_field = ft.TextField(label="止损(%)", value="1", expand=True, height=40, content_padding=10, text_size=14)
    gt_auto_interval_field = ft.TextField(label="自动间隔", value="0.5", expand=True, height=40, content_padding=10, text_size=14)
    
    gt_strategy_radio = ft.RadioGroup(
        content=ft.Row([
            ft.Radio(value="LONG", label="看多"),
            ft.Radio(value="SHORT", label="看空"),
            ft.Radio(value="NEUTRAL", label="中性"),
        ]),
        value="NEUTRAL"
    )
    
    # Auto execution state variables are declared at the top of main()
    
    # Create auto execution toggle button
    auto_toggle_btn = ft.ElevatedButton(
        "开始自动执行",
        expand=True,
        color=Colors.WHITE,
        bgcolor=Colors.GREEN_700
    )
    
    def manage_stop_loss():
        """Manage stop loss orders: place, update (trailing), or cancel"""
        sl_pct_str = gt_stop_loss_field.value.strip()
        if not sl_pct_str:
            return

        try:
            sl_pct = float(sl_pct_str)
        except ValueError:
            return # Invalid input, ignore

        if sl_pct <= 0:
            return

        # Check if we have a position
        if not state.get("position"):
            return
        
        pos_amt = safe_float(state["position"].get("positionAmt"))
        if pos_amt == 0:
            # No position, cancel existing stop loss if any
            if state["stop_loss"]["order_id"]:
                try:
                    trade_client.cancel_conditional_order(state["symbol"], strategyId=state["stop_loss"]["order_id"])
                    push_status("空仓，已撤销止损单")
                except Exception as e:
                    print(f"Failed to cancel SL: {e}")
                state["stop_loss"] = {"order_id": None, "trigger_price": None}
            return

        entry_price = safe_float(state["position"].get("entryPrice"))
        tick_size = state["filters"]["tick_size"]
        
        # Calculate new stop price
        if pos_amt > 0: # LONG
            new_stop_price = entry_price * (1 - sl_pct / 100)
            side = "SELL"
        else: # SHORT
            new_stop_price = entry_price * (1 + sl_pct / 100)
            side = "BUY"
            
        formatted_stop_price = format_price(new_stop_price, tick_size)
        
        # Check if we need to update (every 10 cycles or if no order)
        should_update = False
        current_sl_price = state["stop_loss"]["trigger_price"]
        
        if not state["stop_loss"]["order_id"]:
            should_update = True
        elif state["loop_count"] % 10 == 0:
            # Trailing logic: only update if new price is better
            if current_sl_price:
                if pos_amt > 0 and float(formatted_stop_price) > float(current_sl_price):
                    should_update = True
                elif pos_amt < 0 and float(formatted_stop_price) < float(current_sl_price):
                    should_update = True
        
        if should_update:
            # Cancel old if exists
            if state["stop_loss"]["order_id"]:
                try:
                    trade_client.cancel_conditional_order(state["symbol"], strategyId=state["stop_loss"]["order_id"])
                except Exception:
                    pass # Ignore cancel errors
            
            # Place new
            try:
                # Use a large quantity for reduceOnly to ensure full close
                huge_qty = 999999 
                res = trade_client.new_conditional_order(
                    symbol=state["symbol"],
                    side=side,
                    strategyType="STOP_MARKET",
                    stopPrice=formatted_stop_price,
                    reduceOnly=True,
                    quantity=huge_qty
                )
                if res:
                    state["stop_loss"]["order_id"] = res.get("strategyId") or res.get("orderId") # strategyId for conditional
                    state["stop_loss"]["trigger_price"] = formatted_stop_price
                    push_status(f"止损单已更新: {formatted_stop_price}")
            except Exception as e:
                print(f"Failed to place SL: {e}")
                notify_error(f"止损下单失败: {e}")

    def check_stop_loss_termination():
        """Check if price hit stop loss level, if so, stop auto execution"""
        if not state["stop_loss"]["trigger_price"]:
            return False
            
        current_price = safe_float(state["ticker"]["price"]) if state["ticker"] else 0
        if current_price == 0: return False
        
        sl_price = float(state["stop_loss"]["trigger_price"])
        pos_amt = safe_float(state["position"].get("positionAmt")) if state["position"] else 0
        
        triggered = False
        if pos_amt > 0 and current_price <= sl_price:
            triggered = True
        elif pos_amt < 0 and current_price >= sl_price:
            triggered = True
            
        if triggered:
            nonlocal auto_execution_running, auto_timer
            auto_execution_running = False
            if auto_timer:
                auto_timer.cancel()
                auto_timer = None
            auto_toggle_btn.text = "开始自动执行"
            auto_toggle_btn.bgcolor = Colors.GREEN_700
            auto_toggle_btn.update()
            push_status(f"触发止损价格 {sl_price}，自动执行已停止", success=False)
            return True
        return False

    @ui_error_handler
    def gt_cancel_grid(_):
        trade_client.cancel_all_orders(state["symbol"])
        push_status("已撤销当前交易对全部订单")
        refresh_data()

    def auto_execute_grid():
        nonlocal auto_execution_running, auto_timer
        if not auto_execution_running:
            return
        
        state["loop_count"] += 1
        
        try:
            # Manage Stop Loss
            manage_stop_loss()
            
            # Check Termination
            if check_stop_loss_termination():
                return

            gt_place_grid_auto()  # 使用专用的自动网格函数
        except Exception as e:
            print(f"Auto grid execution error: {e}")
            push_status(f"自动网格执行错误: {str(e)}", success=False)
        
        # Schedule next execution
        if auto_execution_running:
            interval = safe_float(gt_auto_interval_field.value)
            if interval <= 0:
                interval = 60  # default to 60 seconds
            auto_timer = threading.Timer(interval, auto_execute_grid)
            auto_timer.start()

    @ui_error_handler
    def toggle_auto_execution(_):
        nonlocal auto_execution_running, auto_timer
        
        if auto_execution_running:
            # 停止自动执行
            auto_execution_running = False
            if auto_timer:
                auto_timer.cancel()
                auto_timer = None
            auto_toggle_btn.text = "开始自动执行"
            auto_toggle_btn.bgcolor = Colors.GREEN_700
            push_status("已停止自动网格执行")
        else:
            # 开始自动执行
            interval = safe_float(gt_auto_interval_field.value)
            if interval <= 0:
                return notify_error("间隔秒数必须大于0")
            
            auto_execution_running = True
            auto_toggle_btn.text = "停止自动执行"
            auto_toggle_btn.bgcolor = Colors.RED_700
            push_status(f"开始自动网格执行，每{interval}秒执行一次")
            auto_execute_grid()
        
        auto_toggle_btn.update()

    @ui_error_handler
    def gt_place_grid(_):
        # 1. Validate Inputs
        try:
            n = int(gt_n_field.value)
            interval_buy = float(gt_buy_interval_field.value)
            interval_sell = float(gt_sell_interval_field.value)
            buy_qty = float(gt_buy_qty_field.value)
            sell_qty = float(gt_sell_qty_field.value)
        except ValueError:
            return notify_error("输入参数无效")

        if n <= 0 or interval_buy <= 0 or interval_sell <= 0 or buy_qty < 0 or sell_qty < 0:
            return notify_error("参数不能为负数，单边数量和网格间隔必须大于0")

        gt_cancel_grid(None)
        
        # 获取基准价格（如果指定了固定价格就不需要刷新市场数据）
        base_price_str = gt_base_price_field.value.strip()
        if base_price_str:
            try:
                current_price = float(base_price_str)
            except ValueError:
                return notify_error("基准价格格式无效")
        else:
            refresh_data()
            if not state["ticker"]: 
                return notify_error("无法获取价格")
            current_price = safe_float(state["ticker"]["price"])
        strategy = gt_strategy_radio.value
        pos_amt = safe_float(state["position"].get("positionAmt")) if state["position"] else 0.0

        d_interval_buy = Decimal(str(interval_buy))
        d_interval_sell = Decimal(str(interval_sell))
        d_current_price = Decimal(str(current_price))
        
        # Calculate base grid using buy interval for consistency
        base_grid = (d_current_price / d_interval_buy).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_interval_buy
        
        orders_to_place = []
        tick_size = state["filters"]["tick_size"]
        step_size = state["filters"]["step_size"]

        # 单向持仓模式策略逻辑
        if strategy == "LONG":
            # 看多策略：只允许BUY开仓，SELL平仓
            # Generate Lower Orders (BUY) - 开仓订单
            if buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1  # 从1开始，避免当前价格
                formatted_buy_qty = format_qty(buy_qty, step_size)
                while count < n:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    if p < d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": False, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
            
            # Generate Upper Orders (SELL) - 平仓订单 (只有持多仓时才下)
            if pos_amt > 0 and sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1
                formatted_sell_qty = format_qty(sell_qty, step_size)
                max_sell_orders = min(n, int(pos_amt / sell_qty))  # 限制平仓单数量
                while count < max_sell_orders:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    if p > d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": True, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        elif strategy == "SHORT":
            # 看空策略：只允许SELL开仓，BUY平仓
            # Generate Upper Orders (SELL) - 开仓订单
            if sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1  # 从1开始，避免当前价格
                formatted_sell_qty = format_qty(sell_qty, step_size)
                while count < n:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    if p > d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": False, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
            
            # Generate Lower Orders (BUY) - 平仓订单 (只有持空仓时才下)
            if pos_amt < 0 and buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1
                formatted_buy_qty = format_qty(buy_qty, step_size)
                max_buy_orders = min(n, int(abs(pos_amt) / buy_qty))  # 限制平仓单数量
                while count < max_buy_orders:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    if p < d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": True, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        else:  # NEUTRAL strategy - 保持原有逻辑
            # 当有持仓时，看多策略的SELL订单和看空策略的BUY订单设为reduceOnly
            # 当无持仓时，所有订单都不是reduceOnly，可以正常开仓
            sell_reduce_only = (pos_amt > 0)
            buy_reduce_only = (pos_amt < 0)
            formatted_sell_qty = format_qty(sell_qty, step_size)
            formatted_buy_qty = format_qty(buy_qty, step_size)

            # Generate Upper Orders (SELL)
            if sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1
                while count < n:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    if p > d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": sell_reduce_only, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break

            # Generate Lower Orders (BUY)
            if buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1
                while count < n:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    if p < d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": buy_reduce_only, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
        
        # 验证订单数量不为空
        if not orders_to_place:
            return notify_error(f"当前策略和持仓状态下没有可下的订单")
        
        def place_one(o):
            try:
                res = trade_client.new_order(
                    symbol=state["symbol"],
                    side=o["side"],
                    type="LIMIT",
                    quantity=o["qty"],
                    price=o['price'],
                    timeInForce="GTX",
                    reduceOnly=o["reduceOnly"],
                    newOrderRespType="ACK"
                )
                if res and "orderId" in res:
                    return True, f"下单成功: {o['side']} {o['qty']} @ {o['price']} {'(RO)' if o['reduceOnly'] else ''}"
            except Exception as e:
                return False, f"下单失败: {o['side']} @ {o['price']} - {str(e)}"
            return False, "下单未知错误"

        success_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place_one, o) for o in orders_to_place]
            for future in concurrent.futures.as_completed(futures):
                success, msg = future.result()
                if success:
                    success_count += 1
        
        push_status(f"网格挂单完成: {success_count} 笔")
        refresh_data()

    @ui_error_handler
    def gt_place_grid_auto():
        """自动网格专用函数，会智能检查现有订单避免重复下单"""
        # 1. Validate Inputs
        try:
            n = int(gt_n_field.value)
            interval_buy = float(gt_buy_interval_field.value)
            interval_sell = float(gt_sell_interval_field.value)
            buy_qty = float(gt_buy_qty_field.value)
            sell_qty = float(gt_sell_qty_field.value)
        except ValueError:
            return notify_error("输入参数无效")

        if n <= 0 or interval_buy <= 0 or interval_sell <= 0 or buy_qty < 0 or sell_qty < 0:
            return notify_error("参数不能为负数，单边数量和网格间隔必须大于0")

        # 获取基准价格（如果指定了固定价格就不需要刷新市场数据）
        base_price_str = gt_base_price_field.value.strip()
        if base_price_str:
            try:
                current_price = float(base_price_str)
            except ValueError:
                return notify_error("基准价格格式无效")
        else:
            refresh_data()
            if not state["ticker"]: 
                return notify_error("无法获取价格")
            current_price = safe_float(state["ticker"]["price"])
        strategy = gt_strategy_radio.value
        pos_amt = safe_float(state["position"].get("positionAmt")) if state["position"] else 0.0

        d_interval_buy = Decimal(str(interval_buy))
        d_interval_sell = Decimal(str(interval_sell))
        d_current_price = Decimal(str(current_price))
        
        # Calculate base grid using buy interval for consistency
        base_grid = (d_current_price / d_interval_buy).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_interval_buy
        
        tick_size = state["filters"]["tick_size"]
        step_size = state["filters"]["step_size"]
        
        # Stop Loss Filter
        sl_price = float(state["stop_loss"]["trigger_price"]) if state["stop_loss"]["trigger_price"] else None

        # 计算期望的订单列表 (使用与gt_place_grid相同的逻辑)
        expected_orders = []
        
        if strategy == "LONG":
            # 看多策略：只允许BUY开仓，SELL平仓
            # Generate Lower Orders (BUY) - 开仓订单
            if buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1
                formatted_buy_qty = format_qty(buy_qty, step_size)
                while count < n:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    
                    # Filter: Don't buy below stop loss (for LONG)
                    if sl_price and float(p) <= sl_price:
                         i += 1
                         continue
                         
                    if p < d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": False, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
            
            # Generate Upper Orders (SELL) - 平仓订单 (只有持多仓时才下)
            if pos_amt > 0 and sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1
                formatted_sell_qty = format_qty(sell_qty, step_size)
                max_sell_orders = min(n, int(pos_amt / sell_qty))
                while count < max_sell_orders:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    if p > d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": True, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        elif strategy == "SHORT":
            # 看空策略：只允许SELL开仓，BUY平仓
            # Generate Upper Orders (SELL) - 开仓订单
            if sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1
                formatted_sell_qty = format_qty(sell_qty, step_size)
                while count < n:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    
                    # Filter: Don't sell above stop loss (for SHORT)
                    if sl_price and float(p) >= sl_price:
                         i += 1
                         continue

                    if p > d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": False, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
            
            # Generate Lower Orders (BUY) - 平仓订单 (只有持空仓时才下)
            if pos_amt < 0 and buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1
                formatted_buy_qty = format_qty(buy_qty, step_size)
                max_buy_orders = min(n, int(abs(pos_amt) / buy_qty))
                while count < max_buy_orders:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    if p < d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": True, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        else:  # NEUTRAL strategy
            sell_reduce_only = (pos_amt > 0)
            buy_reduce_only = (pos_amt < 0)
            formatted_sell_qty = format_qty(sell_qty, step_size)
            formatted_buy_qty = format_qty(buy_qty, step_size)

            # Generate Upper Orders (SELL)
            if sell_qty > 0:  # 只有卖出数量大于0时才生成卖出订单
                count = 0
                i = 1
                while count < n:
                    p = base_grid + (Decimal(i) * d_interval_sell)
                    
                    # Filter: Don't sell above stop loss (if SHORT bias or just safety)
                    # For Neutral, if we have position, we might want to respect stop loss too.
                    # If pos_amt < 0 (Short), stop loss is above.
                    if pos_amt < 0 and sl_price and float(p) >= sl_price:
                        i += 1
                        continue
                    
                    if p > d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": sell_reduce_only, "qty": formatted_sell_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break

            # Generate Lower Orders (BUY)
            if buy_qty > 0:  # 只有买入数量大于0时才生成买入订单
                count = 0
                i = 1
                while count < n:
                    p = base_grid - (Decimal(i) * d_interval_buy)
                    
                    # Filter: Don't buy below stop loss (if LONG bias or just safety)
                    # If pos_amt > 0 (Long), stop loss is below.
                    if pos_amt > 0 and sl_price and float(p) <= sl_price:
                        i += 1
                        continue

                    if p < d_current_price:
                        expected_orders.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": buy_reduce_only, "qty": formatted_buy_qty})
                        count += 1
                    i += 1
                    if i > n * 10: break

        if not expected_orders:
            return  # 静默返回，不显示错误信息
        
        # 获取当前挂单
        try:
            current_orders = trade_client.get_open_orders(state["symbol"])
            if not current_orders:
                current_orders = []
        except Exception as e:
            print(f"获取挂单失败: {e}")
            current_orders = []
        
        # 检查哪些订单需要操作
        orders_to_cancel, orders_to_place = check_order_differences(current_orders, expected_orders, max(interval_buy, interval_sell))
        
        if not orders_to_cancel and not orders_to_place:
            # push_status("网格订单已是最新状态，无需调整")
            return

        # 先撤销不需要的订单
        canceled_count = 0
        if orders_to_cancel:
            canceled_count = cancel_specific_orders(orders_to_cancel)

        # 下新订单
        success_count = 0
        if orders_to_place:
            success_count = place_orders_batch(orders_to_place)
            
        if canceled_count > 0 or success_count > 0:
            push_status(f"自动调整: 撤销 {canceled_count} 笔, 新增 {success_count} 笔")
        refresh_data()

    def check_order_differences(current_orders, expected_orders, max_interval):
        """基于价格范围的检查机制，包含去重逻辑"""
        if not expected_orders:
            return current_orders, []  # 没有期望订单，撤销所有当前订单
        
        # 获取期望订单的价格范围
        expected_prices = [Decimal(str(order["price"])) for order in expected_orders]
        min_expected_price = min(expected_prices)
        max_expected_price = max(expected_prices)
        
        # 扩展容忍范围：向两边各扩展一个网格间隔
        price_range_min = min_expected_price - Decimal(str(max_interval))
        price_range_max = max_expected_price + Decimal(str(max_interval))
        
        # 获取当前的买入和卖出数量设置（用于识别网格单）
        step_size = state["filters"]["step_size"]
        buy_qty_setting = format_qty(float(gt_buy_qty_field.value), step_size) if float(gt_buy_qty_field.value) > 0 else ""
        sell_qty_setting = format_qty(float(gt_sell_qty_field.value), step_size) if float(gt_sell_qty_field.value) > 0 else ""

        # 1. 找出超出范围的订单，直接撤销
        # 只有当订单数量与设置的网格数量一致时，才认为是网格单并允许撤销
        # 如果数量不一致，视为手动单，不撤销，也不参与去重（即允许网格单和手动单共存）
        orders_to_cancel = []
        valid_grid_orders = []  # 仅包含在范围内的网格单
        
        for order in current_orders:
            order_price = Decimal(str(order.get("price", "0")))
            order_side = order.get("side")
            order_qty = order.get("origQty")
            
            # 判断是否为网格单（数量匹配）
            is_grid_order = False
            if order_side == "BUY" and buy_qty_setting and str(order_qty) == str(buy_qty_setting):
                is_grid_order = True
            elif order_side == "SELL" and sell_qty_setting and str(order_qty) == str(sell_qty_setting):
                is_grid_order = True
            
            if not is_grid_order:
                # 手动单：不撤销，不参与去重
                continue
                
            # 网格单：检查价格范围
            if order_price < price_range_min or order_price > price_range_max:
                orders_to_cancel.append(order)
            else:
                valid_grid_orders.append(order)
        
        # 2. 对在范围内的订单进行精确匹配去重
        orders_to_place = []
        
        for expected_order in expected_orders:
            exp_price = Decimal(str(expected_order["price"]))
            exp_side = expected_order["side"]
            exp_reduce_only = expected_order["reduceOnly"]
            expected_qty = expected_order.get("qty", "0")
            
            # 检查是否已有相同的订单
            found_match = False
            for current_order in valid_grid_orders:
                cur_price = Decimal(str(current_order.get("price", "0")))
                cur_side = current_order.get("side")
                cur_reduce_only = current_order.get("reduceOnly", False)
                cur_qty = current_order.get("origQty")
                
                # 精确匹配：价格、方向、reduceOnly标志、数量都必须一致
                if (cur_price == exp_price and 
                    cur_side == exp_side and 
                    cur_reduce_only == exp_reduce_only and
                    str(cur_qty) == str(expected_qty)):
                    found_match = True
                    break
            
            # 如果没找到匹配的订单，需要新增
            if not found_match:
                orders_to_place.append(expected_order)
        
        return orders_to_cancel, orders_to_place

    def cancel_specific_orders(orders_to_cancel):
        """撤销指定订单，返回成功撤销的订单数量"""
        if not orders_to_cancel:
            return 0
            
        def cancel_one(order):
            try:
                result = trade_client.cancel_order(
                    symbol=state["symbol"],
                    orderId=order.get("orderId")
                )
                if result:
                    return True, f"撤销成功: {order.get('orderId')}"
            except Exception as e:
                return False, f"撤销失败 {order.get('orderId')}: {str(e)}"
            return False, "撤销未知错误"
        
        success_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cancel_one, order) for order in orders_to_cancel]
            for future in concurrent.futures.as_completed(futures):
                success, msg = future.result()
                if success:
                    success_count += 1
                else:
                    print(msg)
        return success_count

    def place_orders_batch(orders_to_place, _unused_qty_param=None):
        """批量下单"""
        def place_one(o):
            try:
                res = trade_client.new_order(
                    symbol=state["symbol"],
                    side=o["side"],
                    type="LIMIT",
                    quantity=o["qty"],
                    price=o['price'],
                    timeInForce="GTX",
                    reduceOnly=o["reduceOnly"],
                    newOrderRespType="ACK"
                )
                return res and "orderId" in res
            except Exception as e:
                print(f"下单失败: {o['side']} @ {o['price']} - {str(e)}")
                return False

        success_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place_one, o) for o in orders_to_place]
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    success_count += 1
        
        return success_count

    # Set button click event
    auto_toggle_btn.on_click = toggle_auto_execution
    
    tab_grid = ft.Container(
        content=ft.Column([
            ft.Row([gt_buy_interval_field, gt_sell_interval_field]),
            ft.Row([gt_buy_qty_field, gt_sell_qty_field]),
            ft.Row([gt_n_field, gt_base_price_field]),
            ft.Row([gt_stop_loss_field, gt_auto_interval_field]),
            ft.Container(content=gt_strategy_radio, padding=ft.padding.only(bottom=5)),
            ft.Row([
                ft.ElevatedButton("执行网格挂单", on_click=gt_place_grid, expand=True, color=Colors.WHITE, bgcolor=Colors.BLUE_700),
                ft.OutlinedButton("撤销网格", on_click=gt_cancel_grid, expand=True),
            ]),
            ft.Row([auto_toggle_btn]),
        ], spacing=10),
        padding=20
    )

    # --- Main Layout ---
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="网格挂单", content=tab_grid),
            ft.Tab(text="快速交易", content=tab_quick),
        ],
        expand=True,
    )

    # --- Close Position Controls ---
    @ui_error_handler
    def close_position(strategy: str):
        if not state.get("position"):
            return notify_error("未获取到持仓信息，请先刷新")
        
        amt = safe_float(state["position"].get("positionAmt"))
        if amt == 0:
            return notify_error("当前无持仓")
        
        # 先撤销所有挂单
        try:
            trade_client.cancel_all_orders(state["symbol"])
            push_status("已撤销所有挂单，准备平仓...")
        except Exception as e:
            print(f"撤单失败: {e}")
            # 即使撤单失败也继续尝试平仓
        
        side = "SELL" if amt > 0 else "BUY"
        abs_qty = abs(amt)
        
        step_size = state["filters"]["step_size"]
        formatted_qty = format_qty(abs_qty, step_size)
        
        params = {
            "symbol": state["symbol"],
            "side": side,
            "quantity": formatted_qty,
            "reduceOnly": True,
            "newOrderRespType": "RESULT"
        }

        if strategy == "MARKET":
            params["type"] = "MARKET"
        elif strategy == "QUEUE":
            params["type"] = "LIMIT"
            params["priceMatch"] = "QUEUE"
            params["timeInForce"] = "GTX"
        
        res = trade_client.new_order(**params)
        if res:
            push_status(f"已提交平仓: {strategy} {side} {formatted_qty}")
            refresh_data()

    close_buttons = ft.Row([
        ft.ElevatedButton("市价全平", on_click=lambda _: close_position("MARKET"), 
                          style=ft.ButtonStyle(bgcolor=Colors.RED_900, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
        ft.ElevatedButton("同向1全平", on_click=lambda _: close_position("QUEUE"), 
                          style=ft.ButtonStyle(bgcolor=Colors.ORANGE_900, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
        ft.ElevatedButton("撤销全部", on_click=qt_cancel_all, 
                          style=ft.ButtonStyle(bgcolor=Colors.GREY_800, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
    ], spacing=10)

    page.add(
        ft.Column([
            ft.Row([symbol_input, refresh_btn]),
            ft.Container(
                content=ft.Column([
                    ft.Row([ticker_price_text, balance_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([position_info_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ]),
                padding=5,
                bgcolor=ft.Colors.with_opacity(0.1, Colors.WHITE),
                border_radius=5
            ),
            tabs,
            ft.Divider(),
            close_buttons,
            ft.Divider(),
            status_text
        ], expand=True)
    )

    # Initialize
    update_filters()
    refresh_data()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
