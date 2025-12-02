import flet as ft
from flet import Colors
import math
import threading
import time
import concurrent.futures
from binance_app.um_account_api import UMAccountClient
from binance_app.um_trade_api import UMTradeClient
from binance_app.market_api import UMMarketClient

SUPPORTED_SYMBOLS = ["ETHUSDC"]
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


def format_number(value, precision=4):
    return f"{safe_float(value):,.{precision}f}"


def main(page: ft.Page):
    page.title = "ETHUSDC 交易终端"
    page.horizontal_alignment = "stretch"
    page.window.width = 400
    page.window.height = 700
    page.theme_mode = ft.ThemeMode.DARK
    page.fonts = {
        "Maple": "fonts/MapleMono-NF-CN-Regular.ttf",
        "noto": "https://raw.githubusercontent.com/notofonts/noto-cjk/refs/heads/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf",
    }

    page.theme = ft.Theme(font_family="Maple")
    page.padding = 10

    account_client = UMAccountClient()
    trade_client = UMTradeClient()
    market_client = UMMarketClient()

    # --- Shared State ---
    state = {
        "symbol": SUPPORTED_SYMBOLS[0],
        "last_order": {"order_id": None, "client_id": None},
        "grid_orders": [],  # List of orderIds placed by grid
        "position": None,   # Current position data
        "ticker": None,     # Current ticker data
    }

    # --- UI Components ---
    status_text = ft.Text("", size=12)

    def push_status(message: str, success: bool = True):
        status_text.value = f"[{time.strftime('%H:%M:%S')}] {message}"
        status_text.color = Colors.GREEN if success else Colors.RED
        status_text.update()
        # page.snack_bar = ft.SnackBar(ft.Text(message), open=True)
        # page.update()

    def notify_error(message: str):
        push_status(message, success=False)

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
    symbol_dropdown = ft.Dropdown(
        label="交易对",
        value=SUPPORTED_SYMBOLS[0],
        options=[ft.dropdown.Option(symbol) for symbol in SUPPORTED_SYMBOLS],
        text_size=14,
        content_padding=10,
        expand=True
    )

    # Info Display
    margin_balance_text = ft.Text("权益: --", size=13)
    available_balance_text = ft.Text("可用: --", size=13)
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
            margin_balance_text.value = f"权益: {equity:.2f}"
            available_balance_text.value = f"可用: {avail:.2f}"

            # Find Position
            positions = account_info.get("positions") or []
            pos = next((p for p in positions if p.get("symbol") == state["symbol"]), None)
            state["position"] = pos
            if pos:
                amt = safe_float(pos.get("positionAmt"))
                entry = safe_float(pos.get("entryPrice"))
                pnl = safe_float(pos.get("unRealizedProfit"))
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

        page.update()

    symbol_dropdown.on_change = lambda e: [state.update({"symbol": e.control.value}), refresh_data()]
    
    refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH,icon_color=ft.Colors.GREEN_300, on_click=refresh_data, tooltip="刷新数据")

    # --- Tab 1: Quick Trade ---
    qt_qty_field = ft.TextField(label="数量", value="0.01", width=100, height=40, content_padding=10, text_size=14)
    qt_side_switch = ft.Switch(label="买入/卖出", value=True, active_color=Colors.GREEN,inactive_thumb_color=Colors.RED)
    qt_reduce_checkbox = ft.Checkbox(label="只减仓", value=False)
    qt_last_order_text = ft.Text("上次: --", size=12)

    @ui_error_handler
    def qt_place_order(match_key, tif):
        qty = safe_float(qt_qty_field.value)
        if qty <= 0: return notify_error("数量无效")
        
        side = "BUY" if qt_side_switch.value else "SELL"
        
        res = trade_client.new_order(
            symbol=state["symbol"],
            side=side,
            type="LIMIT",
            quantity=qty,
            timeInForce=tif,
            priceMatch=match_key,
            reduceOnly=qt_reduce_checkbox.value,
            newOrderRespType="RESULT"
        )
        if res:
            state["last_order"] = {"order_id": res.get("orderId"), "client_id": res.get("clientOrderId")}
            qt_last_order_text.value = f"上次: {side} {qty} @ {match_key}"
            push_status("快速下单成功")
            refresh_data()

    @ui_error_handler
    def qt_cancel_last(_):
        if not state["last_order"]["order_id"]: return notify_error("无上次订单")
        trade_client.cancel_order(state["symbol"], orderId=state["last_order"]["order_id"])
        push_status("撤销上次订单成功")
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
            ft.Divider(),
            ft.Row([
                ft.OutlinedButton("撤销上次", on_click=qt_cancel_last, expand=True),
                ft.OutlinedButton("撤销全部", on_click=qt_cancel_all, expand=True),
            ]),
            qt_last_order_text
        ], spacing=15),
        padding=20
    )

    # --- Tab 2: Grid Trade ---
    gt_n_field = ft.TextField(label="单边数量", value="2", width=100, height=40, content_padding=10, text_size=14)
    gt_interval_field = ft.TextField(label="网格间隔", value="1", width=100, height=40, content_padding=10, text_size=14)
    gt_qty_field = ft.TextField(label="单笔数量", value="0.01", width=100, height=40, content_padding=10, text_size=14)
    gt_direction_switch = ft.Switch(label="看多/看空", value=True, active_color=Colors.GREEN, inactive_thumb_color=Colors.RED)
    gt_reduce_checkbox = ft.Checkbox(label="只减仓模式", value=False)
    
    gt_log_lv = ft.ListView(expand=True, spacing=2, auto_scroll=True)
    gt_log_container = ft.Container(
        content=gt_log_lv,
        height=150,
        border=ft.border.all(1, ft.Colors.with_opacity(0.2, Colors.WHITE)),
        border_radius=5,
        padding=5,
    )

    def log_grid(msg: str):
        gt_log_lv.controls.append(ft.Text(f"[{time.strftime('%H:%M:%S')}] {msg}", size=11, font_family="Maple"))
        gt_log_lv.update()

    @ui_error_handler
    def gt_cancel_grid(_, refresh=True):
        if not state["grid_orders"]:
            push_status("无记录的网格订单")
            return
        
        # Cancel tracked orders
        # Note: Ideally we use batch cancel or cancel all, but to be safe we cancel specific IDs or just cancel all if user prefers.
        # Here we try to cancel specific IDs.
        
        def cancel_one(oid):
            try:
                trade_client.cancel_order(state["symbol"], orderId=oid)
                return True, f"撤单成功: {oid}"
            except Exception as e:
                return False, f"撤单失败 {oid}: {str(e)}"

        count = 0
        logs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(cancel_one, oid) for oid in state["grid_orders"]]
            for future in concurrent.futures.as_completed(futures):
                success, msg = future.result()
                if success:
                    count += 1
                logs.append(msg)
        
        # Batch update logs to UI
        for msg in logs:
            gt_log_lv.controls.append(ft.Text(f"[{time.strftime('%H:%M:%S')}] {msg}", size=11, font_family="Maple"))
        gt_log_lv.update()

        state["grid_orders"] = []
        push_status(f"已尝试撤销 {count} 个网格订单")
        log_grid(f"已清理网格订单: {count} 个")
        if refresh:
            refresh_data()

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

        # 2. Get Context (Moved up for speed optimization: Calculate -> Cancel -> Place)
        refresh_data(None) # Update price and position
        if not state["ticker"]: return notify_error("无法获取价格")
        
        current_price = safe_float(state["ticker"]["price"])
        is_long_view = gt_direction_switch.value
        is_reduce_mode = gt_reduce_checkbox.value
        
        # Position Check for Reduce Only
        pos_amt = safe_float(state["position"].get("positionAmt")) if state["position"] else 0.0
        # pos_amt > 0 (Long), pos_amt < 0 (Short)

        # 3. Calculate Grid Levels
        # Grid lines: k * interval
        base_grid = round(current_price / interval) * interval
        
        orders_to_place = []

        # Generate Upper Orders (Price > Current) -> SELL
        # If View=Long: Sell is Close (ReduceOnly if mode on).
        # If View=Short: Sell is Open (Normal).
        p = base_grid
        count = 0
        while count < n:
            if p > current_price:
                # Determine params
                side = "SELL"
                ro = False
                if is_reduce_mode:
                    if is_long_view: # View Long, Sell is Opposite -> ReduceOnly
                        ro = True
                    else: # View Short, Sell is Same -> Normal
                        ro = False
                
                # If RO, check position
                if ro:
                    # Can only place if we have Long position
                    if pos_amt <= 0: 
                        p += interval
                        continue # Cannot close if no position
                    # Optional: Check if we have enough position? 
                    # For now, we just place. API might reject if total > position.
                
                orders_to_place.append({"price": p, "side": side, "reduceOnly": ro})
                count += 1
            p += interval

        # Generate Lower Orders (Price < Current) -> BUY
        # If View=Long: Buy is Open (Normal).
        # If View=Short: Buy is Close (ReduceOnly if mode on).
        p = base_grid
        count = 0
        while count < n:
            if p < current_price:
                side = "BUY"
                ro = False
                if is_reduce_mode:
                    if is_long_view: # View Long, Buy is Same -> Normal
                        ro = False
                    else: # View Short, Buy is Opposite -> ReduceOnly
                        ro = True
                
                if ro:
                    if pos_amt >= 0: # Cannot close short if no short position
                        p -= interval
                        continue

                orders_to_place.append({"price": p, "side": side, "reduceOnly": ro})
                count += 1
            p -= interval

        # 4. Place Orders (Cancel old ones first)
        # Check position size limit for ReduceOnly orders?
        # User said: "需要检查自己的单量"
        # Let's count how many RO orders we have and total qty
        ro_orders = [o for o in orders_to_place if o["reduceOnly"]]
        if ro_orders:
            total_ro_qty = len(ro_orders) * qty
            abs_pos = abs(pos_amt)
            if total_ro_qty > abs_pos:
                # Prune orders? Or just warn?
                # User said "只能是平空... 需要检查自己的单量"
                # Let's limit the number of RO orders to match position
                max_ro_orders = int(abs_pos / qty)
                if max_ro_orders < len(ro_orders):
                    # Keep only the ones closest to price?
                    # Sort by proximity to current_price
                    ro_orders.sort(key=lambda x: abs(x["price"] - current_price))
                    kept_ro = ro_orders[:max_ro_orders]
                    
                    # Rebuild orders_to_place
                    new_orders = [o for o in orders_to_place if not o["reduceOnly"]]
                    new_orders.extend(kept_ro)
                    orders_to_place = new_orders
                    push_status(f"只减仓单量限制: 调整为 {len(kept_ro)} 单")

        # Cancel previous grid orders NOW (Minimize downtime)
        if state["grid_orders"]:
            gt_cancel_grid(None, refresh=False)

        placed_ids = []
        
        def place_one(o):
            try:
                res = trade_client.new_order(
                    symbol=state["symbol"],
                    side=o["side"],
                    type="LIMIT",
                    quantity=qty,
                    price=f"{o['price']:.2f}", # Adjust precision dynamically ideally
                    timeInForce="GTX", # Post Only
                    reduceOnly=o["reduceOnly"],
                    newOrderRespType="ACK"
                )
                if res and "orderId" in res:
                    msg = f"下单成功: {o['side']} {qty} @ {o['price']:.2f} {'(RO)' if o['reduceOnly'] else ''}"
                    return res["orderId"], msg
            except Exception as e:
                msg = f"下单失败: {o['side']} @ {o['price']:.2f} - {str(e)}"
                return None, msg
            return None, "下单未知错误"

        logs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place_one, o) for o in orders_to_place]
            for future in concurrent.futures.as_completed(futures):
                oid, msg = future.result()
                if oid:
                    placed_ids.append(oid)
                if msg:
                    logs.append(msg)
        
        # Batch update logs
        for msg in logs:
            gt_log_lv.controls.append(ft.Text(f"[{time.strftime('%H:%M:%S')}] {msg}", size=11, font_family="Maple"))
        gt_log_lv.update()
        
        state["grid_orders"] = placed_ids
        push_status(f"网格挂单完成: {len(placed_ids)} 笔")
        refresh_data()

    tab_grid = ft.Container(
        content=ft.Column([
            ft.Row([gt_n_field, gt_interval_field, gt_qty_field], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([gt_direction_switch, gt_reduce_checkbox], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([
                ft.ElevatedButton("执行网格挂单", on_click=gt_place_grid, expand=True, color=Colors.WHITE, bgcolor=Colors.BLUE_700),
                ft.OutlinedButton("撤销网格", on_click=gt_cancel_grid, expand=True),
            ]),
            ft.Text("执行日志:", size=12, weight=ft.FontWeight.BOLD),
            gt_log_container
        ], spacing=10),
        padding=20
    )

    # --- Main Layout ---
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="快速交易", content=tab_quick),
            ft.Tab(text="网格挂单", content=tab_grid),
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
        
        side = "SELL" if amt > 0 else "BUY"
        abs_qty = abs(amt)
        
        params = {
            "symbol": state["symbol"],
            "side": side,
            "quantity": abs_qty,
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
            push_status(f"已提交平仓: {strategy} {side} {abs_qty}")
            refresh_data()

    close_buttons = ft.Row([
        ft.ElevatedButton("市价全平", on_click=lambda _: close_position("MARKET"), 
                          style=ft.ButtonStyle(bgcolor=Colors.RED_900, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
        ft.ElevatedButton("同向价1全平", on_click=lambda _: close_position("QUEUE"), 
                          style=ft.ButtonStyle(bgcolor=Colors.ORANGE_900, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
        ft.ElevatedButton("撤销全部", on_click=qt_cancel_all, 
                          style=ft.ButtonStyle(bgcolor=Colors.GREY_800, color=Colors.WHITE, shape=ft.RoundedRectangleBorder(radius=5)), expand=True),
    ], spacing=10)

    page.add(
        ft.Column([
            ft.Row([symbol_dropdown, refresh_btn]),
            ft.Container(
                content=ft.Column([
                    ft.Row([ticker_price_text, margin_balance_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([position_info_text, available_balance_text], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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

    refresh_data()

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
