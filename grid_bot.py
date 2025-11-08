from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Any, List, Literal, Optional, Sequence, Tuple

from binance_api import (
    BinanceAPIError,
    BinanceDeliveryTrading,
    BinanceMarketData,
    OrderRequest,
)
from binance_api.market_data import MarketType

TrendDirection = Literal["bullish", "bearish", "sideways"]


@dataclass
class TrendSignal:
    direction: TrendDirection
    slope: Decimal
    strength: Decimal


@dataclass
class GridLevel:
    price: Decimal
    side: str
    quantity: Decimal
    notional: Decimal
    order_type: str = "LIMIT"
    stop_price: Optional[Decimal] = None


@dataclass
class ExecutionResult:
    level: GridLevel
    success: bool
    response: Any = None
    error: Optional[str] = None


@dataclass
class GridPlan:
    lower_bound: Decimal
    upper_bound: Decimal
    current_price: Decimal
    trend: TrendSignal
    buy_levels: List[GridLevel] = field(default_factory=list)
    sell_levels: List[GridLevel] = field(default_factory=list)
    take_profit: Optional[GridLevel] = None
    stop_loss: Optional[GridLevel] = None

    @property
    def all_levels(self) -> List[GridLevel]:
        levels = self.buy_levels + self.sell_levels
        if self.take_profit:
            levels.append(self.take_profit)
        if self.stop_loss:
            levels.append(self.stop_loss)
        return levels


@dataclass
class GridConfig:
    symbol: str
    grid_count: int
    total_investment: Decimal
    leverage: Decimal
    long_interval: str
    long_limit: int
    short_interval: str
    short_limit: int
    market: MarketType = "usdt"
    place_orders: bool = False
    time_in_force: str = "GTC"
    price_precision: Optional[str] = None
    quantity_precision: Optional[str] = None
    position_side: Optional[str] = None
    reduce_only: bool = False
    take_profit_pct: Decimal = Decimal("0.01")
    stop_loss_pct: Decimal = Decimal("0.01")
    gtd_seconds: Optional[int] = None


@dataclass
class SymbolFilters:
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Optional[Decimal] = None


@dataclass
class PnLReport:
    total: Decimal
    trade_count: int
    start_time: Optional[int]
    end_time: Optional[int]


@dataclass
class _KlinesCacheEntry:
    data: Sequence[Sequence[Any]]
    start_time: Optional[int]
    end_time: Optional[int]
    fetched_at: float


class GridBot:
    """基于 K 线数据的自动网格策略。"""

    def __init__(
        self,
        market_data: BinanceMarketData,
        trading: Optional[BinanceDeliveryTrading] = None,
    ) -> None:
        self.market_data = market_data
        self.trading = trading
        self._klines_cache: OrderedDict[
            Tuple[str, str, Optional[int], Optional[int], MarketType, int],
            _KlinesCacheEntry,
        ] = OrderedDict()
        self._klines_cache_size = 16
        self._klines_cache_ttl = 2.0
        self._default_gtd_seconds = 3600

    def run(self, config: GridConfig) -> Tuple[GridPlan, List[ExecutionResult]]:
        if config.grid_count < 2:
            raise ValueError("grid_count 至少为 2。")
        if config.total_investment <= 0 or config.leverage <= 0:
            raise ValueError("total_investment 与 leverage 必须为正数。")

        long_klines = self._fetch_klines(
            symbol=config.symbol,
            interval=config.long_interval,
            limit=config.long_limit,
            market=config.market,
        )
        short_klines = self._fetch_klines(
            symbol=config.symbol,
            interval=config.short_interval,
            limit=config.short_limit,
            market=config.market,
        )

        trend = self._detect_trend(long_klines)
        lower_bound, upper_bound = self._derive_bounds(short_klines, trend)
        try:
            current_price = self._fetch_current_price(config.symbol, config.market)
        except Exception:
            current_price = self._extract_price(short_klines[-1][4])

        symbol_filters = self._get_symbol_filters(
            symbol=config.symbol,
            market=config.market,
        )
        price_precision = config.price_precision or self._decimal_to_str(symbol_filters.tick_size)
        quantity_precision = (
            config.quantity_precision or self._decimal_to_str(symbol_filters.step_size)
        )

        plan = self._build_plan(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            current_price=current_price,
            config=config,
            trend=trend,
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_qty=symbol_filters.min_qty,
            min_notional=symbol_filters.min_notional,
        )

        executions: List[ExecutionResult] = []
        if config.place_orders:
            if not self.trading:
                raise RuntimeError("place_orders=True 需要提供交易客户端。")
            executions = self._execute_orders(plan, config)
        return plan, executions

    def _fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int,
        market: MarketType,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Sequence[Sequence[Any]]:
        cache_key = (symbol, interval, start_time, end_time, market, limit)
        cache_entry = self._klines_cache.get(cache_key)
        if cache_entry and self._cache_entry_valid(cache_entry, start_time, end_time):
            self._klines_cache.move_to_end(cache_key)
            return cache_entry.data

        klines = self.market_data.get_klines(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            market=market,
        )
        if not isinstance(klines, Sequence) or len(klines) < 2:
            raise ValueError(f"{interval} 周期返回的数据不足以计算趋势/网格。")
        normalized = tuple(tuple(item) for item in klines)
        cache_entry = _KlinesCacheEntry(
            data=normalized,
            start_time=self._extract_kline_start(normalized),
            end_time=self._extract_kline_end(normalized),
            fetched_at=time.time(),
        )
        self._klines_cache[cache_key] = cache_entry
        if len(self._klines_cache) > self._klines_cache_size:
            self._klines_cache.popitem(last=False)
        return cache_entry.data

    def _cache_entry_valid(
        self,
        entry: _KlinesCacheEntry,
        start_time: Optional[int],
        end_time: Optional[int],
    ) -> bool:
        if start_time is not None:
            if entry.start_time is None or entry.start_time > start_time:
                return False
        if end_time is not None:
            if entry.end_time is None or entry.end_time < end_time:
                return False
        if start_time is None and end_time is None:
            if (time.time() - entry.fetched_at) > self._klines_cache_ttl:
                return False
        return True

    def _extract_kline_start(self, klines: Sequence[Sequence[Any]]) -> Optional[int]:
        if not klines:
            return None
        first = klines[0]
        if len(first) < 1:
            return None
        try:
            return int(first[0])
        except (TypeError, ValueError):
            return None

    def _extract_kline_end(self, klines: Sequence[Sequence[Any]]) -> Optional[int]:
        if not klines:
            return None
        last = klines[-1]
        if len(last) < 7:
            return None
        try:
            return int(last[6])
        except (TypeError, ValueError):
            return None

    def _detect_trend(self, klines: Sequence[Sequence[Any]]) -> TrendSignal:
        closes = [self._extract_price(item[4]) for item in klines if len(item) > 4]
        if len(closes) < 3:
            raise ValueError("无法根据不足的 K 线数据计算趋势。")
        slope, strength = self._linear_regression(closes)
        threshold = Decimal("0.0015")
        if strength > threshold:
            direction: TrendDirection = "bullish"
        elif strength < -threshold:
            direction = "bearish"
        else:
            direction = "sideways"
        return TrendSignal(direction=direction, slope=slope, strength=strength)

    def _derive_bounds(
        self,
        klines: Sequence[Sequence[Any]],
        trend: TrendSignal,
    ) -> Tuple[Decimal, Decimal]:
        highs = [self._extract_price(item[2]) for item in klines if len(item) > 3]
        lows = [self._extract_price(item[3]) for item in klines if len(item) > 3]
        if not highs or not lows:
            raise ValueError("短周期数据缺少高低价。")
        recent_high = max(highs)
        recent_low = min(lows)
        if recent_high == recent_low:
            padding = recent_high * Decimal("0.01") or Decimal("1")
            return recent_low - padding, recent_high + padding

        volatility = (recent_high - recent_low) / recent_high
        padding_pct = min(Decimal("0.05"), max(Decimal("0.01"), volatility / 2))
        lower = recent_low * (Decimal("1") - padding_pct)
        upper = recent_high * (Decimal("1") + padding_pct)

        bias = min(Decimal("0.12"), abs(trend.strength) * Decimal("12"))
        if trend.direction == "bullish":
            upper *= Decimal("1") + bias
        elif trend.direction == "bearish":
            lower *= Decimal("1") - bias
        return lower, upper

    def _build_plan(
        self,
        *,
        lower_bound: Decimal,
        upper_bound: Decimal,
        current_price: Decimal,
        config: GridConfig,
        trend: TrendSignal,
        price_precision: str,
        quantity_precision: str,
        min_qty: Decimal,
        min_notional: Optional[Decimal],
    ) -> GridPlan:
        grid_prices = self._build_grid_prices(lower_bound, upper_bound, config.grid_count)
        buy_prices = [price for price in grid_prices if price < current_price]
        sell_prices = [price for price in grid_prices if price > current_price]

        if not buy_prices and not sell_prices:
            raise ValueError("网格价格与当前价格重合，无法构建买卖订单。")

        effective_capital = config.total_investment * config.leverage
        buy_ratio, sell_ratio = self._allocation_by_trend(trend.direction)
        if not buy_prices:
            buy_ratio = Decimal("0")
            sell_ratio = Decimal("1")
        if not sell_prices:
            buy_ratio = Decimal("1")
            sell_ratio = Decimal("0")
        total_ratio = buy_ratio + sell_ratio
        if total_ratio == 0:
            raise ValueError("资金分配比例为 0，参数可能不合法。")

        normalized_buy_ratio = buy_ratio / total_ratio
        normalized_sell_ratio = sell_ratio / total_ratio
        buy_budget = effective_capital * normalized_buy_ratio
        sell_budget = effective_capital * normalized_sell_ratio

        buy_levels = self._build_levels(
            prices=buy_prices,
            side="BUY",
            budget=buy_budget,
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        sell_levels = self._build_levels(
            prices=sell_prices,
            side="SELL",
            budget=sell_budget,
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_qty=min_qty,
            min_notional=min_notional,
        )
        take_profit_level = self._build_protective_level(
            side="SELL",
            price=upper_bound * (Decimal("1") + config.take_profit_pct),
            quantity=sum(level.quantity for level in buy_levels),
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_qty=min_qty,
            min_notional=min_notional,
            order_type="TAKE_PROFIT_MARKET",
        )
        stop_loss_level = self._build_protective_level(
            side="BUY",
            price=lower_bound * (Decimal("1") - config.stop_loss_pct),
            quantity=sum(level.quantity for level in sell_levels),
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            min_qty=min_qty,
            min_notional=min_notional,
            order_type="TAKE_PROFIT_MARKET",
        )
        return GridPlan(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            current_price=current_price,
            trend=trend,
            buy_levels=buy_levels,
            sell_levels=sell_levels,
            take_profit=take_profit_level,
            stop_loss=stop_loss_level,
        )

    def _build_levels(
        self,
        *,
        prices: Sequence[Decimal],
        side: str,
        budget: Decimal,
        price_precision: str,
        quantity_precision: str,
        min_qty: Decimal,
        min_notional: Optional[Decimal],
    ) -> List[GridLevel]:
        if not prices or budget <= 0:
            return []
        per_level = budget / len(prices)
        ordered_prices = sorted(prices, reverse=(side == "SELL"))
        levels: List[GridLevel] = []
        for price in ordered_prices:
            quantized_price = self._quantize(price, price_precision)
            if quantized_price <= 0:
                continue
            raw_quantity = per_level / quantized_price
            quantity = self._quantize(raw_quantity, quantity_precision)
            if quantity <= 0:
                continue
            if quantity < min_qty:
                continue
            notional = quantity * quantized_price
            if min_notional and notional < min_notional:
                continue
            levels.append(
                GridLevel(
                    price=quantized_price,
                    side=side,
                    quantity=quantity,
                    notional=notional,
                )
            )
        return levels

    def _build_protective_level(
        self,
        *,
        side: str,
        price: Decimal,
        quantity: Decimal,
        price_precision: str,
        quantity_precision: str,
        min_qty: Decimal,
        min_notional: Optional[Decimal],
        order_type: str,
    ) -> Optional[GridLevel]:
        if quantity <= 0 or price <= 0:
            return None
        quantized_price = self._quantize(price, price_precision)
        quantized_qty = self._quantize(quantity, quantity_precision)
        if quantized_qty <= 0 or quantized_qty < min_qty:
            return None
        notional = quantized_qty * quantized_price
        if min_notional and notional < min_notional:
            return None
        stop_price = quantized_price if order_type.upper().endswith("MARKET") else None
        return GridLevel(
            price=quantized_price,
            side=side,
            quantity=quantized_qty,
            notional=notional,
            order_type=order_type,
            stop_price=stop_price,
        )

    def sync_orders(self, plan: GridPlan, config: GridConfig) -> List[ExecutionResult]:
        if not self.trading:
            raise RuntimeError("sync_orders 需要交易客户端。")
        try:
            open_orders = self.trading.get_open_orders(symbol=config.symbol)
        except BinanceAPIError as exc:
            return [
                ExecutionResult(
                    level=GridLevel(price=Decimal("0"), side="SYNC", quantity=Decimal("0"), notional=Decimal("0")),
                    success=False,
                    error=str(exc),
                )
            ]

        existing = {
            (
                str(order.get("side")),
                str(order.get("type", "")).upper(),
                self._extract_optional_price(order.get("price")),
                self._extract_optional_price(order.get("stopPrice")),
            )
            for order in open_orders
            if order.get("side")
        }

        active_levels = self._select_active_levels(plan)
        missing_levels = [
            level for level in active_levels if self._level_identity(level) not in existing
        ]
        if not missing_levels:
            return []
        return self._submit_levels(missing_levels, config)

    def get_realized_pnl(
        self,
        *,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> PnLReport:
        if not self.trading:
            raise RuntimeError("获取盈亏需要交易客户端。")
        trades = self._fetch_all_trades(symbol=symbol, start_time=start_time, end_time=end_time)
        if not trades:
            return PnLReport(total=Decimal("0"), trade_count=0, start_time=None, end_time=None)
        total = sum(
            self._parse_decimal(item.get("realizedPnl", "0"), field="realizedPnl")
            for item in trades
        )
        times = [int(item.get("time")) for item in trades if item.get("time") is not None]
        start_ts = min(times) if times else None
        end_ts = max(times) if times else None
        return PnLReport(total=total, trade_count=len(trades), start_time=start_ts, end_time=end_ts)

    def _submit_levels(self, levels: Sequence[GridLevel], config: GridConfig) -> List[ExecutionResult]:
        filtered_levels, skipped_results = self._filter_cross_book(levels, config)
        executions: List[ExecutionResult] = list(skipped_results)
        gtd_expiration_ms: Optional[int] = None
        for level in filtered_levels:
            order_type = getattr(level, "order_type", "LIMIT").upper()
            is_limit = order_type == "LIMIT"
            price = level.price if is_limit else None
            stop_price = level.stop_price if level.stop_price is not None else (None if is_limit else level.price)
            tif = config.time_in_force if is_limit else None
            extra_params: dict[str, Any] = {}
            if tif and tif.upper() == "GTD":
                if gtd_expiration_ms is None:
                    try:
                        gtd_expiration_ms = self._compute_good_till_date(config)
                    except ValueError as exc:
                        executions.append(
                            ExecutionResult(
                                level=level,
                                success=False,
                                error=str(exc),
                            )
                        )
                        continue
                extra_params["goodTillDate"] = gtd_expiration_ms
            order = OrderRequest(
                symbol=config.symbol,
                side=level.side,
                order_type=order_type,
                quantity=level.quantity,
                price=price,
                stop_price=stop_price,
                time_in_force=tif,
                position_side=config.position_side,
                reduce_only=config.reduce_only,
                extra_params=extra_params,
            )
            try:
                response = self.trading.create_order(order)  # type: ignore[union-attr]
                executions.append(ExecutionResult(level=level, success=True, response=response))
            except (BinanceAPIError, ValueError) as exc:
                executions.append(
                    ExecutionResult(
                        level=level,
                        success=False,
                        error=str(exc),
                    )
                )
        return executions

    def _compute_good_till_date(self, config: GridConfig) -> int:
        seconds_value = config.gtd_seconds if config.gtd_seconds is not None else self._default_gtd_seconds
        seconds = int(seconds_value)
        if seconds < 600:
            seconds = 600
        now_seconds = int(time.time())
        expiry_seconds = now_seconds + seconds
        max_ms = 253402300799000
        expiry_ms = expiry_seconds * 1000
        if expiry_ms >= max_ms:
            raise ValueError("goodTillDate 超出 Binance 限制。")
        return expiry_ms

    def _filter_cross_book(
        self,
        levels: Sequence[GridLevel],
        config: GridConfig,
    ) -> Tuple[List[GridLevel], List[ExecutionResult]]:
        if not levels:
            return [], []
        try:
            book_ticker = self.market_data.get_book_ticker(
                symbol=config.symbol,
                market=config.market,
            )
        except Exception:
            return list(levels), []

        if not isinstance(book_ticker, dict):
            return list(levels), []

        best_bid = self._extract_optional_price(book_ticker.get("bidPrice"))
        best_ask = self._extract_optional_price(book_ticker.get("askPrice"))

        filtered: List[GridLevel] = []
        skipped: List[ExecutionResult] = []
        for level in levels:
            order_type = getattr(level, "order_type", "LIMIT").upper()
            side = level.side.upper()
            if order_type != "LIMIT":
                filtered.append(level)
                continue
            if side == "BUY" and best_ask is not None and level.price >= best_ask:
                skipped.append(
                    ExecutionResult(
                        level=level,
                        success=False,
                        error=(
                            "跳过补单：买单价格不应高于当前最优卖价"
                            f"（price={level.price} >= ask={best_ask}）"
                        ),
                    )
                )
                continue
            if side == "SELL" and best_bid is not None and level.price <= best_bid:
                skipped.append(
                    ExecutionResult(
                        level=level,
                        success=False,
                        error=(
                            "跳过补单：卖单价格不应低于当前最优买价"
                            f"（price={level.price} <= bid={best_bid}）"
                        ),
                    )
                )
                continue
            filtered.append(level)
        return filtered, skipped

    def _select_active_levels(self, plan: GridPlan) -> List[GridLevel]:
        active: List[GridLevel] = []
        # 选择最近的2个买入级别（价格最高的2个）
        if plan.buy_levels:
            sorted_buy = sorted(plan.buy_levels, key=lambda level: level.price, reverse=True)
            active.extend(sorted_buy[:2])
        # 选择最近的2个卖出级别（价格最低的2个）
        if plan.sell_levels:
            sorted_sell = sorted(plan.sell_levels, key=lambda level: level.price)
            active.extend(sorted_sell[:2])
        if plan.take_profit:
            active.append(plan.take_profit)
        if plan.stop_loss:
            active.append(plan.stop_loss)
        return active

    def _level_identity(self, level: GridLevel) -> Tuple[str, str, Optional[Decimal], Optional[Decimal]]:
        order_type = getattr(level, "order_type", "LIMIT").upper()
        if order_type == "LIMIT":
            price_key: Optional[Decimal] = level.price
            stop_key: Optional[Decimal] = None
        else:
            price_key = None
            stop_key = level.stop_price or level.price
        return (level.side, order_type, price_key, stop_key)

    def _execute_orders(self, plan: GridPlan, config: GridConfig) -> List[ExecutionResult]:
        levels = self._select_active_levels(plan)
        return self._submit_levels(levels, config)

    def _get_symbol_filters(self, *, symbol: str, market: MarketType) -> SymbolFilters:
        exchange_info = self.market_data.get_exchange_info(symbol=symbol, market=market)
        entry = self._select_symbol_entry(exchange_info, symbol)
        filters = entry.get("filters")
        if not isinstance(filters, Sequence):
            raise ValueError(f"{symbol} 缺少交易规则 filters。")
        price_filter = self._find_filter(filters, "PRICE_FILTER")
        lot_size_filter = self._find_filter(filters, "LOT_SIZE")
        if not price_filter or not lot_size_filter:
            raise ValueError(f"{symbol} 缺少 PRICE_FILTER 或 LOT_SIZE。")
        tick_size = self._parse_decimal(price_filter.get("tickSize"), field="tickSize")
        step_size = self._parse_decimal(lot_size_filter.get("stepSize"), field="stepSize")
        min_qty = self._parse_decimal(lot_size_filter.get("minQty"), field="minQty")
        min_notional_filter = self._find_filter(filters, "MIN_NOTIONAL")
        min_notional = (
            self._parse_decimal(min_notional_filter.get("notional"), field="notional")
            if min_notional_filter and min_notional_filter.get("notional") is not None
            else None
        )
        if tick_size <= 0 or step_size <= 0:
            raise ValueError(f"{symbol} 的 tickSize/stepSize 非法。")
        return SymbolFilters(
            tick_size=tick_size,
            step_size=step_size,
            min_qty=min_qty,
            min_notional=min_notional,
        )

    def _select_symbol_entry(self, data: Any, symbol: str) -> dict[str, Any]:
        if isinstance(data, dict):
            if data.get("symbol") == symbol:
                return data
            symbols = data.get("symbols")
            if isinstance(symbols, Sequence):
                for item in symbols:
                    if isinstance(item, dict) and item.get("symbol") == symbol:
                        return item
        raise ValueError(f"exchangeInfo 未返回 {symbol} 的交易规则。")

    def _find_filter(
        self,
        filters: Sequence[Any],
        filter_type: str,
    ) -> Optional[dict[str, Any]]:
        for item in filters:
            if isinstance(item, dict) and item.get("filterType") == filter_type:
                return item
        return None

    def _linear_regression(self, prices: Sequence[Decimal]) -> Tuple[Decimal, Decimal]:
        n = len(prices)
        x_mean = Decimal(n - 1) / 2
        y_mean = sum(prices) / n
        numerator = sum(
            (Decimal(i) - x_mean) * (price - y_mean) for i, price in enumerate(prices)
        )
        denominator = sum((Decimal(i) - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            denominator = Decimal("1")
        slope = numerator / denominator
        strength = slope / y_mean if y_mean != 0 else Decimal("0")
        return slope, strength

    def _build_grid_prices(
        self,
        lower_bound: Decimal,
        upper_bound: Decimal,
        count: int,
    ) -> List[Decimal]:
        if upper_bound <= lower_bound:
            raise ValueError("upper_bound 必须大于 lower_bound。")
        if count < 2:
            raise ValueError("网格数量至少为 2。")
        if count == 2:
            return [lower_bound, upper_bound]
        step = (upper_bound - lower_bound) / (count - 1)
        return [lower_bound + step * i for i in range(count)]

    def _allocation_by_trend(self, direction: TrendDirection) -> Tuple[Decimal, Decimal]:
        if direction == "bullish":
            return Decimal("0.65"), Decimal("0.35")
        if direction == "bearish":
            return Decimal("0.4"), Decimal("0.6")
        return Decimal("0.5"), Decimal("0.5")

    def _quantize(self, value: Decimal, precision: Optional[str]) -> Decimal:
        if precision is None:
            return value
        try:
            quantum = Decimal(precision)
        except (InvalidOperation, ValueError) as exc:  # pragma: no cover - 防御
            raise ValueError(f"非法精度值: {precision}") from exc
        return value.quantize(quantum, rounding=ROUND_DOWN)

    def _extract_price(self, value: Any) -> Decimal:
        return self._parse_decimal(value, field="价格")

    def _extract_optional_price(self, value: Any) -> Optional[Decimal]:
        if value in (None, "", 0, "0", "0.0", "0.00"):
            return None
        return self._extract_price(value)

    def _fetch_current_price(self, symbol: str, market: MarketType) -> Decimal:
        ticker = self.market_data.get_price_ticker(symbol=symbol, market=market)
        target: Optional[dict[str, Any]] = None
        if isinstance(ticker, dict):
            target = ticker
        elif isinstance(ticker, (list, tuple)):
            for item in ticker:
                if isinstance(item, dict) and item.get("symbol") == symbol:
                    target = item
                    break
        if not target:
            raise ValueError("未能获取价格ticker。")
        price_value = target.get("price") or target.get("lastPrice") or target.get("markPrice")
        if price_value is None:
            raise ValueError("价格ticker缺少 price 字段。")
        return self._extract_price(price_value)

    def _parse_decimal(self, value: Any, *, field: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"无法解析{field}: {value}") from exc

    def _decimal_to_str(self, value: Decimal) -> str:
        normalized = value.normalize()
        as_str = format(normalized, "f")
        return as_str if as_str else "0"

    def _fetch_all_trades(
        self,
        *,
        symbol: str,
        start_time: Optional[int],
        end_time: Optional[int],
    ) -> List[dict[str, Any]]:
        if not self.trading:
            return []
        trades: List[dict[str, Any]] = []
        from_id: Optional[int] = None
        max_loops = 50
        for _ in range(max_loops):
            batch = self.trading.get_user_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                from_id=from_id,
                limit=1000,
            )
            if not batch:
                break
            trades.extend(batch)
            if len(batch) < 1000:
                break
            last_id = batch[-1].get("id")
            if last_id is None:
                break
            try:
                from_id = int(last_id) + 1
            except (TypeError, ValueError):
                break
        return trades
