from typing import Any, Literal, Optional

from .client import BinanceClient

MarketType = Literal["coin", "usdt"]
_DEPTH_ALLOWED_LIMITS = (5, 10, 20, 50, 100, 500, 1000)
_RATIO_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


class BinanceMarketData:
    """行情查询接口封装，目前支持交割合约K线数据。
    """

    def __init__(
        self,
        client: BinanceClient,
        *,
        version_prefix: str = "/fapi/v1",
        linear_version_prefix: str = "/fapi/v1",
    ) -> None:
        self.client = client
        self.version_prefix = version_prefix.rstrip("/")
        self.linear_version_prefix = linear_version_prefix.rstrip("/")

    def get_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        获取标准合约 Kline 数据，支持币本位(/fapi) 与 U 本位(/fapi)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Kline-Candlestick-Data
        
        ### 请求参数:
            symbol (str) -- 交易对，必需（示例: "BTCUSDT"）。
            interval (str) -- 时间间隔，必需。支持的间隔有:
                "1m", "3m", "5m", "15m", "30m",
                "1h", "2h", "4h", "6h", "8h", "12h",
                "1d", "3d",
                "1w",
                "1M"
            start_time (int | None) -- 起始时间，非必需。以毫秒为单位的 Unix 时间戳（ms）。
            end_time (int | None) -- 结束时间，非必需。以毫秒为单位的 Unix 时间戳（ms）。
            limit (int | None) -- 返回的 Kline 条数，非必需。默认值: 500，取值范围: 1-1500，最大 1500。
        ### 返回:
            Any -- 来自服务器的原始响应（通常为列表，每项为一个 kline 数组）。单个 kline 数组格式（Binance 风格）通常为：
                [
                    1499040000000,      # Open time
                    "0.01634790",       # Open
                    "0.80000000",       # High
                    "0.01575800",       # Low
                    "0.01577100",       # Close
                    "148976.11427815",  # Volume
                    1499644799999,      # Close time
                    "2434.19055334",    # Quote asset volume
                    308,                # Number of trades
                    "1756.87402397",    # Taker buy base asset volume
                    "28.46694368",      # Taker buy quote asset volume
                    "17928899.62484339" # Ignore (可忽略字段)
                ]
        ### 信息：
        startTime 与 endTime 之间最多只可以相差200天
        默认返回 startTime 与 endTime 之间最接近 endTime的 limit 条数据:
            startTime, endTime 均未提供的, 将会使用当前时间为 endTime, 200天前为 startTime
            仅提供 startTime 的, 将会使用 startTime 之后200天作为默认 endTime (至多为当前时间)
            仅提供 endTime 的, 将会使用endTime 之前200天作为默认 startTime
        """
        
        prefix = self._resolve_prefix(market)
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request_klines(f"{prefix}/klines", params)

    def get_mark_price_klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        获取标记价格 Kline 序列 (/markPriceKlines)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Mark-Price-Kline-Data
        """

        prefix = self._resolve_prefix(market)
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request_klines(f"{prefix}/markPriceKlines", params)

    def get_index_price_klines(
        self,
        *,
        pair: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        获取价格指数 Kline 序列 (/indexPriceKlines)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Index-Price-Kline-Data
        """

        prefix = self._resolve_prefix(market)
        params = {
            "pair": pair,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request_klines(f"{prefix}/indexPriceKlines", params)

    def get_continuous_klines(
        self,
        *,
        pair: str,
        contract_type: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        获取连续合约 Kline 序列 (/continuousKlines)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Continuous-Contract-Kline-Data
        """

        prefix = self._resolve_prefix(market)
        params = {
            "pair": pair,
            "contractType": contract_type,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
        }
        return self._request_klines(f"{prefix}/continuousKlines", params)

    def get_depth(
        self,
        *,
        symbol: str,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        查询交易对深度 (/depth)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Order-Book
        """

        if limit is not None and limit not in _DEPTH_ALLOWED_LIMITS:
            raise ValueError(f"limit 仅支持 {_DEPTH_ALLOWED_LIMITS}。")
        params = {
            "symbol": symbol,
            "limit": limit,
        }
        path = self._make_market_path("depth", market)
        return self.client.public_request("GET", path, params=params)

    def get_recent_trades(
        self,
        *,
        symbol: str,
        limit: Optional[int] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        获取近期成交 (归集) (/trades)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Recent-Trades-List
        """

        self._validate_limit(limit, max_value=1000)
        params = {
            "symbol": symbol,
            "limit": limit,
        }
        path = self._make_market_path("trades", market)
        return self.client.public_request("GET", path, params=params)

    def get_24hr_ticker(
        self,
        *,
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        查询 24 小时价格变动情况 (/ticker/24hr)。
        symbol 与 pair 不能同时提交，均为空时返回所有交易对的 24h 数据（权重较高）。
        """

        self._validate_symbol_or_pair(symbol, pair)
        params = self._build_symbol_pair_params(symbol, pair)
        path = self._make_market_path("ticker/24hr", market)
        return self.client.public_request("GET", path, params=params)

    def get_price_ticker(
        self,
        *,
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        查询最新价格 (/ticker/price)。
        symbol 与 pair 不能同时提交，均为空时返回所有交易对价格。
        """

        self._validate_symbol_or_pair(symbol, pair)
        params = self._build_symbol_pair_params(symbol, pair)
        path = self._make_market_path("ticker/price", market)
        return self.client.public_request("GET", path, params=params)

    def get_book_ticker(
        self,
        *,
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
        market: MarketType = "usdt",
    ) -> Any:
        """
        查询当前最优挂单 (/ticker/bookTicker)。
        symbol 与 pair 不能同时提交，均为空时返回所有交易对的最优买卖价。
        """

        self._validate_symbol_or_pair(symbol, pair)
        params = self._build_symbol_pair_params(symbol, pair)
        path = self._make_market_path("ticker/bookTicker", market)
        return self.client.public_request("GET", path, params=params)

    def get_exchange_info(
        self,
        *,
        market: MarketType = "usdt",
        symbol: Optional[str] = None,
        pair: Optional[str] = None,
    ) -> Any:
        """
        获取交易规则与交易对详情 (/exchangeInfo)。
        """

        self._validate_symbol_or_pair(symbol, pair)
        params = self._build_symbol_pair_params(symbol, pair)
        path = self._make_market_path("exchangeInfo", market)
        return self.client.public_request("GET", path, params=params)

    def get_top_long_short_position_ratio(
        self,
        *,
        pair: str,
        period: str,
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Any:
        """
        获取大户持仓量多空比 (/futures/data/topLongShortPositionRatio)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Top-Trader-Long-Short-Position-Ratio
        """

        self._validate_ratio_period(period)
        self._validate_limit(limit, min_value=1, max_value=500)
        params = {
            "pair": pair,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self.client.public_request(
            "GET",
            "/futures/data/topLongShortPositionRatio",
            params=params,
        )

    def get_global_long_short_account_ratio(
        self,
        *,
        pair: str,
        period: str,
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Any:
        """
        获取多空持仓人数比 (/futures/data/globalLongShortAccountRatio)。
        https://developers.binance.com/docs/zh-CN/derivatives/coin-margined-futures/market-data/rest-api/Global-Long-Short-Account-Ratio
        """

        self._validate_ratio_period(period)
        self._validate_limit(limit, min_value=1, max_value=500)
        params = {
            "pair": pair,
            "period": period,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self.client.public_request(
            "GET",
            "/futures/data/globalLongShortAccountRatio",
            params=params,
        )

    def _resolve_prefix(self, market: MarketType) -> str:
        if market == "coin":
            return self.version_prefix
        if market == "usdt":
            return self.linear_version_prefix
        raise ValueError("market 仅支持 'coin' 或 'usdt'")

    def _request_klines(self, path: str, params: dict[str, Any]) -> Any:
        self._validate_limit(params.get("limit"))
        return self.client.public_request(
            "GET",
            path,
            params=params,
        )

    def _make_market_path(self, endpoint: str, market: MarketType) -> str:
        prefix = self._resolve_prefix(market)
        endpoint = endpoint.lstrip("/")
        return f"{prefix}/{endpoint}"

    def _validate_limit(
        self,
        limit: Optional[int],
        *,
        min_value: int = 1,
        max_value: int = 1500,
    ) -> None:
        if limit is None:
            return
        if not (min_value <= limit <= max_value):
            raise ValueError(f"limit 取值范围为 {min_value}-{max_value}。")

    def _validate_symbol_or_pair(self, symbol: Optional[str], pair: Optional[str]) -> None:
        if symbol and pair:
            raise ValueError("symbol 与 pair 不能同时提供。")

    def _build_symbol_pair_params(self, symbol: Optional[str], pair: Optional[str]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        if pair:
            params["pair"] = pair
        return params

    def _validate_ratio_period(self, period: str) -> None:
        if period not in _RATIO_PERIODS:
            raise ValueError(f"period 仅支持 {_RATIO_PERIODS}。")
