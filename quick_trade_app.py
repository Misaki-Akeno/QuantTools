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
    page.window.height = 620
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
        }
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
    gt_interval_field = ft.TextField(label="网格间隔", value="1", expand=True, height=40, content_padding=10, text_size=14)
    gt_qty_field = ft.TextField(label="单笔数量", value="0.01", expand=True, height=40, content_padding=10, text_size=14)
    gt_auto_interval_field = ft.TextField(label="自动间隔", value="5", expand=True, height=40, content_padding=10, text_size=14)
    
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
    
    @ui_error_handler
    def gt_cancel_grid(_):
        trade_client.cancel_all_orders(state["symbol"])
        push_status("已撤销当前交易对全部订单")
        refresh_data()

    def auto_execute_grid():
        nonlocal auto_execution_running, auto_timer
        if not auto_execution_running:
            return
        
        try:
            gt_place_grid(None)
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
            interval = float(gt_interval_field.value)
            qty = float(gt_qty_field.value)
        except ValueError:
            return notify_error("输入参数无效")

        if n <= 0 or interval <= 0 or qty <= 0:
            return notify_error("参数必须大于0")

        gt_cancel_grid(None)
        refresh_data()
        if not state["ticker"]: 
            return notify_error("无法获取价格")
        
        current_price = safe_float(state["ticker"]["price"])
        strategy = gt_strategy_radio.value
        pos_amt = safe_float(state["position"].get("positionAmt")) if state["position"] else 0.0

        d_interval = Decimal(str(interval))
        d_current_price = Decimal(str(current_price))
        
        # Calculate base grid
        base_grid = (d_current_price / d_interval).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_interval
        
        orders_to_place = []
        tick_size = state["filters"]["tick_size"]
        step_size = state["filters"]["step_size"]
        formatted_qty = format_qty(qty, step_size)

        # 单向持仓模式策略逻辑
        if strategy == "LONG":
            # 看多策略：只允许BUY开仓，SELL平仓
            # Generate Lower Orders (BUY) - 开仓订单
            count = 0
            i = 1  # 从1开始，避免当前价格
            while count < n:
                p = base_grid - (Decimal(i) * d_interval)
                if p < d_current_price:
                    orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": False})
                    count += 1
                i += 1
                if i > n * 10: break
            
            # Generate Upper Orders (SELL) - 平仓订单 (只有持多仓时才下)
            if pos_amt > 0:
                count = 0
                i = 1
                max_sell_orders = min(n, int(pos_amt / qty))  # 限制平仓单数量
                while count < max_sell_orders:
                    p = base_grid + (Decimal(i) * d_interval)
                    if p > d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": True})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        elif strategy == "SHORT":
            # 看空策略：只允许SELL开仓，BUY平仓
            # Generate Upper Orders (SELL) - 开仓订单
            count = 0
            i = 1  # 从1开始，避免当前价格
            while count < n:
                p = base_grid + (Decimal(i) * d_interval)
                if p > d_current_price:
                    orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": False})
                    count += 1
                i += 1
                if i > n * 10: break
            
            # Generate Lower Orders (BUY) - 平仓订单 (只有持空仓时才下)
            if pos_amt < 0:
                count = 0
                i = 1
                max_buy_orders = min(n, int(abs(pos_amt) / qty))  # 限制平仓单数量
                while count < max_buy_orders:
                    p = base_grid - (Decimal(i) * d_interval)
                    if p < d_current_price:
                        orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": True})
                        count += 1
                    i += 1
                    if i > n * 10: break
                    
        else:  # NEUTRAL strategy - 保持原有逻辑
            # 当有持仓时，看多策略的SELL订单和看空策略的BUY订单设为reduceOnly
            # 当无持仓时，所有订单都不是reduceOnly，可以正常开仓
            sell_reduce_only = (pos_amt > 0)
            buy_reduce_only = (pos_amt < 0)

            # Generate Upper Orders (SELL)
            count = 0
            i = 1
            while count < n:
                p = base_grid + (Decimal(i) * d_interval)
                if p > d_current_price:
                    orders_to_place.append({"price": format_price(p, tick_size), "side": "SELL", "reduceOnly": sell_reduce_only})
                    count += 1
                i += 1
                if i > n * 10: break

            # Generate Lower Orders (BUY)
            count = 0
            i = 1
            while count < n:
                p = base_grid - (Decimal(i) * d_interval)
                if p < d_current_price:
                    orders_to_place.append({"price": format_price(p, tick_size), "side": "BUY", "reduceOnly": buy_reduce_only})
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
                    quantity=formatted_qty,
                    price=o['price'],
                    timeInForce="GTX",
                    reduceOnly=o["reduceOnly"],
                    newOrderRespType="ACK"
                )
                if res and "orderId" in res:
                    return True, f"下单成功: {o['side']} {formatted_qty} @ {o['price']} {'(RO)' if o['reduceOnly'] else ''}"
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

    # Set button click event
    auto_toggle_btn.on_click = toggle_auto_execution
    
    tab_grid = ft.Container(
        content=ft.Column([
            ft.Row([gt_n_field, gt_interval_field]),
            ft.Row([gt_qty_field, gt_auto_interval_field]),
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
