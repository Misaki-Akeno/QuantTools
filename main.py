import time
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, List, Optional, Sequence, Tuple, cast

import click
import typer
import typer.core as typer_core

from binance_api import BinanceDeliveryTrading, BinanceMarketData, build_client_from_env
from binance_api.market_data import MarketType
from grid_bot import ExecutionResult, GridBot, GridConfig, GridLevel, GridPlan, PnLReport

typer_core.rich = None  # 点击帮助时禁用 Rich，避免 Click 8 上的兼容问题

_original_make_metavar = typer_core.TyperOption.make_metavar


def _safe_make_metavar(self, ctx: Optional[click.Context] = None) -> str:
    dummy_ctx = ctx or click.Context(click.Command(name="grid-bot"))
    return _original_make_metavar(self, dummy_ctx)


typer_core.TyperOption.make_metavar = _safe_make_metavar

app = typer.Typer(help="币安", rich_markup_mode=None)
SCRIPT_START_TIME_MS = int(time.time() * 1000)


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        typer.echo(f"{name} 格式错误: {value}")
        raise typer.Exit(code=1) from exc


def _parse_utc_timestamp(value: str, name: str) -> int:
    normalized = value.strip()
    if not normalized:
        typer.echo(f"{name} 不能为空。")
        raise typer.Exit(code=1)
    if normalized.lower().endswith("z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        typer.echo(f"{name} 需使用 UTC ISO8601 格式，例如 2024-01-01T00:00:00Z。")
        raise typer.Exit(code=1) from exc
    if dt.tzinfo is None:
        typer.echo(f"{name} 需包含时区信息（UTC）。")
        raise typer.Exit(code=1)
    utc_dt = dt.astimezone(timezone.utc)
    return int(utc_dt.timestamp() * 1000)


def _format_decimal(value: Decimal, digits: int = 4) -> str:
    return format(value, f".{digits}f")


PROTECTIVE_ORDER_TYPES = {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}


def _format_order_value(value: Any, digits: int = 4) -> str:
    if value is None:
        return "?"
    try:
        return _format_decimal(Decimal(str(value)), digits)
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _echo_levels(title: str, levels: Sequence[GridLevel]) -> None:
    typer.echo(f"{title}（{len(levels)}）:")
    if not levels:
        typer.echo("  无")
        return
    for level in levels:
        typer.echo(
            "  "
            f"{level.side:<4} "
            f"price={_format_decimal(level.price)} "
            f"qty={_format_decimal(level.quantity, 6)} "
            f"notional={_format_decimal(level.notional)}"
        )


def _echo_plan(plan: GridPlan) -> None:
    typer.echo("=== 趋势与网格 ===")
    typer.echo(
        f"趋势: {plan.trend.direction} "
        f"(slope={_format_decimal(plan.trend.slope, 6)}, "
        f"strength={_format_decimal(plan.trend.strength, 6)})"
    )
    typer.echo(
        "价格区间: "
        f"{_format_decimal(plan.lower_bound)} - {_format_decimal(plan.upper_bound)}"
    )
    typer.echo(f"当前价格: {_format_decimal(plan.current_price)}")
    _echo_levels("买入挂单", plan.buy_levels)
    _echo_levels("卖出挂单", plan.sell_levels)
    if plan.take_profit:
        typer.echo(
            "止盈单: "
            f"{plan.take_profit.side} "
            f"price={_format_decimal(plan.take_profit.price)} "
            f"qty={_format_decimal(plan.take_profit.quantity, 6)}"
        )
    if plan.stop_loss:
        typer.echo(
            "止损单: "
            f"{plan.stop_loss.side} "
            f"price={_format_decimal(plan.stop_loss.price)} "
            f"qty={_format_decimal(plan.stop_loss.quantity, 6)}"
        )


def _echo_open_orders(title: str, orders: Sequence[dict[str, Any]], *, protective: bool = False) -> None:
    typer.echo(f"{title}（{len(orders)}）:")
    if not orders:
        typer.echo("  无")
        return
    for item in orders:
        side = str(item.get("side", "?"))
        order_type = str(item.get("type", "?")).upper()
        price = _format_order_value(item.get("price", "?"))
        stop_price = _format_order_value(item.get("stopPrice", "?"))
        qty_source = (
            item.get("origQty") or item.get("quantity") or item.get("origQuantity") or 0
        )
        qty = _format_order_value(qty_source, 6)
        if protective or order_type in PROTECTIVE_ORDER_TYPES:
            price_text = f"stop={stop_price}"
            if price not in {"0", "0.0", "0.0000", "?"}:
                price_text += f" price={price}"
        else:
            price_text = f"price={price}"
        typer.echo(
            "  "
            f"{side:<4} "
            f"type={order_type or '?'} "
            f"{price_text} "
            f"qty={qty} "
            f"status={item.get('status', 'NEW')}"
        )


def _echo_new_orders(executions: Sequence[ExecutionResult]) -> None:
    typer.echo("=== 新增挂单 ===")
    if not executions:
        typer.echo("  无")
        return
    for item in executions:
        status = "成功" if item.success else "失败"
        order_type = getattr(item.level, "order_type", "LIMIT").upper()
        trigger_price = item.level.stop_price or item.level.price
        if order_type in PROTECTIVE_ORDER_TYPES:
            if trigger_price is not None:
                price_text = f"stop={_format_decimal(trigger_price)}"
            else:
                price_text = "stop=?"
        else:
            price_text = f"price={_format_decimal(item.level.price)}"
        typer.echo(
            f"  [{status}] {item.level.side} {order_type} "
            f"{price_text} "
            f"qty={_format_decimal(item.level.quantity, 6)}"
        )
        if not item.success:
            typer.echo(f"    错误: {item.error}")


def _echo_pnl(report: Optional[PnLReport]) -> None:
    typer.echo("=== 累计盈亏 ===")
    if report is None:
        typer.echo("  暂无数据（需要 --place-orders）。")
        return
    typer.echo(f"成交笔数: {report.trade_count}")
    typer.echo(f"实现盈亏: {_format_decimal(report.total, 6)}")
    if report.start_time:
        start_str = _format_ts(report.start_time)
        end_str = _format_ts(report.end_time) if report.end_time else "未知"
        typer.echo(f"时间区间: {start_str} -> {end_str}")


def _categorize_existing_orders(
    orders: Sequence[dict[str, Any]]
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]], List[dict[str, Any]]]:
    grid_orders: List[dict[str, Any]] = []
    tp_orders: List[dict[str, Any]] = []
    sl_orders: List[dict[str, Any]] = []
    for order in orders:
        order_type = str(order.get("type", "")).upper()
        side = str(order.get("side", "")).upper()
        if order_type in PROTECTIVE_ORDER_TYPES:
            if side == "SELL":
                tp_orders.append(order)
            else:
                sl_orders.append(order)
        else:
            grid_orders.append(order)
    return grid_orders, tp_orders, sl_orders


def _fetch_margin_usage(
    trading: BinanceDeliveryTrading,
    symbol: str,
) -> Tuple[Optional[Decimal], Optional[str]]:
    try:
        positions = trading.get_position_risk(symbol=symbol)
    except Exception as exc:
        return None, str(exc)

    if not isinstance(positions, Sequence):
        return None, "positionRisk 返回结果格式异常"

    total = Decimal("0")
    matched = False
    for item in positions:
        if not isinstance(item, dict):
            continue
        if item.get("symbol") != symbol:
            continue
        matched = True
        for field in ("positionInitialMargin", "openOrderInitialMargin"):
            raw_value = item.get(field)
            if raw_value in (None, ""):
                continue
            try:
                total += abs(Decimal(str(raw_value)))
            except (InvalidOperation, ValueError):
                return None, f"无法解析 {field}: {raw_value}"

    if not matched:
        return Decimal("0"), None
    return total, None


def _echo_runtime_status(
    *,
    current_price: Decimal,
    existing_orders: Sequence[dict[str, Any]],
    new_orders: Sequence[ExecutionResult],
    pnl_report: Optional[PnLReport],
    margin_usage: Optional[Decimal],
    margin_limit: Optional[Decimal],
    margin_exceeded: bool,
    margin_error: Optional[str],
) -> None:
    typer.echo("=== 实时状态 ===")
    typer.echo(f"当前价格: {_format_decimal(current_price)}")
    grid_orders, tp_orders, sl_orders = _categorize_existing_orders(existing_orders)
    _echo_open_orders("网格挂单", grid_orders)
    _echo_open_orders("止盈挂单", tp_orders, protective=True)
    _echo_open_orders("止损挂单", sl_orders, protective=True)
    _echo_new_orders(new_orders)
    _echo_pnl(pnl_report)
    typer.echo("=== 保证金 ===")
    if margin_error:
        typer.echo(f"  获取失败: {margin_error}")
        return
    limit_text = _format_decimal(margin_limit) if margin_limit is not None else "?"
    if margin_usage is None:
        typer.echo(f"  当前占用: 未知 (阈值: {limit_text})")
        return
    typer.echo(
        f"  当前占用: {_format_decimal(margin_usage, 6)} (阈值: {limit_text})"
    )
    if margin_exceeded:
        typer.echo("  警告: 占用已超过阈值，暂停开仓。")


def _format_ts(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _trading_prefix(market: MarketType) -> str:
    return "/dapi/v1" if market == "coin" else "/fapi/v1"


@app.command("grid-bot")
def grid_trader(
    symbol: str = typer.Option("BTCUSDC", "--symbol", "-s", help="交易对"),
    grid_count: int = typer.Option(32, "--grid-count", "-g", help="网格数量"),
    total_investment: str = typer.Option(
        "3000",
        "--total",
        "-t",
        help="总投入（计价货币，例如 USD 或 USDT）。",
    ),
    leverage: str = typer.Option("3", "--leverage", "-l", help="杠杆倍数"),
    long_interval: str = typer.Option("1d", help="长期趋势使用的 K 线周期"),
    long_limit: int = typer.Option(240, help="长期趋势使用的 K 线条数"),
    short_interval: str = typer.Option("15m", help="网格上下限使用的 K 线周期"),
    short_limit: int = typer.Option(60, help="短周期 K 线条数，用于确定网格边界"),
    market: str = typer.Option(
        "usdt",
        "--market",
        help="合约品种市场：coin (币本位) 或 usdt (U 本位)。",
    ),
    place_orders: bool = typer.Option(
        False,
        "--place-orders/--dry-run",
        help="是否立刻在币安下单，默认仅输出网格计划。",
    ),
    price_precision: Optional[str] = typer.Option(
        None,
        help="价格精度，例如 0.1。",
    ),
    quantity_precision: Optional[str] = typer.Option(
        None,
        help="数量精度，例如 0.001。",
    ),
    position_side: Optional[str] = typer.Option(
        None,
        help="双向持仓模式下的 positionSide，可选 LONG/SHORT/BOTH。",
    ),
    reduce_only: bool = typer.Option(False, help="是否只允许减仓订单。"),
    time_in_force: str = typer.Option("GTD", help="限价单 timeInForce。"),
    gtd_seconds: Optional[int] = typer.Option(
        1200,
        "--gtd-seconds",
        help="timeInForce=GTD 时订单自动取消时间（秒），需 >= 600，未指定时默认 3600 秒。",
    ),
    take_profit_pct: str = typer.Option(
        "0.001",
        "--take-profit-pct",
        help="止盈价格偏移百分比（例如 0.01 表示高于上限 1%）。",
    ),
    stop_loss_pct: str = typer.Option(
        "0.001",
        "--stop-loss-pct",
        help="止损价格偏移百分比（例如 0.01 表示低于下限 1%）。",
    ),
    loop_seconds: Optional[float] = typer.Option(
        None,
        "--loop-seconds",
        help="开启后机器人将持续运行。",
    ),
    max_cycles: Optional[int] = typer.Option(
        None,
        "--max-cycles",
        help="与 --loop-seconds 配合使用，限制循环次数。",
    ),
    pnl_start_time: Optional[str] = typer.Option(
        None,
        "--pnl-start-time",
        help="盈亏统计起始 UTC 时间，例如 2024-01-01T00:00:00Z；默认使用脚本启动时间。",
    ),
) -> None:
    """按照“长周期判趋势 + 短周期定网格”生成/执行自动网格。"""

    total_investment_decimal = _parse_decimal(total_investment, "total")
    leverage_decimal = _parse_decimal(leverage, "leverage")
    take_profit_decimal = _parse_decimal(take_profit_pct, "take-profit-pct")
    stop_loss_decimal = _parse_decimal(stop_loss_pct, "stop-loss-pct")
    if leverage_decimal <= 0:
        typer.echo("leverage 需大于 0。")
        raise typer.Exit(code=1)
    leverage_integral = leverage_decimal.to_integral_value()
    if leverage_decimal != leverage_integral:
        typer.echo("leverage 需为整数。")
        raise typer.Exit(code=1)
    leverage_int = int(leverage_integral)
    if leverage_int < 1 or leverage_int > 125:
        typer.echo("leverage 需在 1~125 之间。")
        raise typer.Exit(code=1)
    if grid_count < 2:
        typer.echo("grid-count 至少为 2。")
        raise typer.Exit(code=1)
    if long_limit < 2 or short_limit < 2:
        typer.echo("long_limit 与 short_limit 需不小于 2。")
        raise typer.Exit(code=1)
    if loop_seconds is not None and loop_seconds <= 0:
        typer.echo("loop-seconds 需大于 0。")
        raise typer.Exit(code=1)
    if max_cycles is not None and max_cycles <= 0:
        typer.echo("max-cycles 需为正整数。")
        raise typer.Exit(code=1)
    if take_profit_decimal <= 0:
        typer.echo("take-profit-pct 需大于 0。")
        raise typer.Exit(code=1)
    if stop_loss_decimal <= 0:
        typer.echo("stop-loss-pct 需大于 0。")
        raise typer.Exit(code=1)

    time_in_force = time_in_force.upper()
    gtd_seconds_value: Optional[int] = gtd_seconds
    if time_in_force == "GTD":
        if gtd_seconds_value is None:
            gtd_seconds_value = 3600
        if gtd_seconds_value < 600:
            typer.echo("timeInForce=GTD 时，--gtd-seconds 需至少 600 秒。")
            raise typer.Exit(code=1)
        max_gtd_ms = 253402300799000
        if (int(time.time()) + gtd_seconds_value) * 1000 >= max_gtd_ms:
            typer.echo("--gtd-seconds 超出 Binance 限制。")
            raise typer.Exit(code=1)
    else:
        gtd_seconds_value = None

    pnl_start_time_ms = SCRIPT_START_TIME_MS
    if pnl_start_time:
        pnl_start_time_ms = _parse_utc_timestamp(pnl_start_time, "pnl-start-time")

    market_value = market.lower()
    if market_value not in {"coin", "usdt"}:
        typer.echo("market 仅支持 coin 或 usdt。")
        raise typer.Exit(code=1)
    market_type = cast(MarketType, market_value)

    client = build_client_from_env()
    market_data = BinanceMarketData(client)
    loop_interval_seconds: Optional[float] = loop_seconds
    continuous = loop_interval_seconds is not None
    if continuous and not place_orders:
        typer.echo("开启循环补单需同时使用 --place-orders。")
        raise typer.Exit(code=1)
    trading = None
    if place_orders:
        trading = BinanceDeliveryTrading(client, version_prefix=_trading_prefix(market_type))
        try:
            typer.echo(f"设置杠杆为 {leverage_int}x ...")
            trading.set_leverage(symbol=symbol, leverage=leverage_int)
        except Exception as exc:
            typer.echo(f"设置杠杆失败: {exc}")
            raise typer.Exit(code=1)
        try:
            typer.echo(f"撤销 {symbol} 的全部挂单 ...")
            trading.cancel_all_orders(symbol=symbol)
        except Exception as exc:
            typer.echo(f"撤销挂单失败: {exc}")
    bot = GridBot(market_data, trading)

    config = GridConfig(
        symbol=symbol,
        grid_count=grid_count,
        total_investment=total_investment_decimal,
        leverage=leverage_decimal,
        long_interval=long_interval,
        long_limit=long_limit,
        short_interval=short_interval,
        short_limit=short_limit,
        market=market_type,
        place_orders=place_orders,
        time_in_force=time_in_force,
        price_precision=price_precision,
        quantity_precision=quantity_precision,
        position_side=position_side,
        reduce_only=reduce_only,
        take_profit_pct=take_profit_decimal,
        stop_loss_pct=stop_loss_decimal,
        gtd_seconds=gtd_seconds_value,
    )

    cycles = 0
    plan_printed = False
    max_run_retries = 3
    retry_delay_seconds = 5.0
    while True:
        effective_config = replace(config, place_orders=False)
        plan: Optional[GridPlan] = None
        executions: List[ExecutionResult] = []
        for attempt in range(1, max_run_retries + 1):
            try:
                plan, executions = bot.run(effective_config)
                break
            except Exception as exc:
                typer.echo(f"网格生成失败 (第 {attempt} 次): {exc}")
                if attempt >= max_run_retries:
                    if not continuous:
                        typer.echo("重试仍失败，退出。")
                        raise typer.Exit(code=1) from exc
                    typer.echo("达到重试上限，等待后继续...")
                time.sleep(retry_delay_seconds * attempt)
        if plan is None:
            continue

        if not plan_printed:
            _echo_plan(plan)
            plan_printed = True

        margin_usage: Optional[Decimal] = None
        margin_error: Optional[str] = None
        margin_exceeded = False
        margin_limit: Optional[Decimal] = config.total_investment

        if trading:
            margin_usage, margin_error = _fetch_margin_usage(trading, config.symbol)
            if margin_error is None and margin_usage is not None and margin_limit is not None:
                if margin_usage > margin_limit:
                    margin_exceeded = True

        existing_orders: Sequence[dict[str, Any]] = []
        new_orders: Sequence[ExecutionResult] = list(executions)
        pnl_report: Optional[PnLReport] = None

        if place_orders and trading:
            if margin_exceeded:
                typer.echo("保证金占用超过总投入，跳过补单。")
                new_orders = []
            else:
                new_orders = bot.sync_orders(plan, config)
            try:
                existing_orders = trading.get_open_orders(symbol=config.symbol)
            except Exception as exc:
                typer.echo(f"获取已有挂单失败: {exc}")
                existing_orders = []
            try:
                pnl_report = bot.get_realized_pnl(
                    symbol=config.symbol,
                    start_time=pnl_start_time_ms,
                )
            except Exception as exc:
                typer.echo(f"盈亏统计失败: {exc}")
            updated_usage, updated_error = _fetch_margin_usage(trading, config.symbol)
            if updated_error:
                margin_error = updated_error
            elif updated_usage is not None:
                margin_usage = updated_usage
                if margin_limit is not None and margin_usage > margin_limit:
                    margin_exceeded = True
        else:
            new_orders = executions

        _echo_runtime_status(
            current_price=plan.current_price,
            existing_orders=existing_orders,
            new_orders=new_orders,
            pnl_report=pnl_report,
            margin_usage=margin_usage,
            margin_limit=margin_limit,
            margin_exceeded=margin_exceeded,
            margin_error=margin_error,
        )

        cycles += 1
        if not continuous:
            break
        if max_cycles and cycles >= max_cycles:
            break
        time.sleep(loop_interval_seconds)

if __name__ == "__main__":
    app()
