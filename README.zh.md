# Binance 交割合约示例项目

本项目演示了如何使用 Python 调用币安交割合约下单接口（`POST /fapi/v1/order`），并对代码进行模块化拆分，便于后续拓展更多接口。
https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/general-info

## 目录结构

- `main.py`：程序入口，从 `.env.local` 读取凭据并演示下单流程。
- `binance_api/`
  - `__init__.py`：导出常用类，方便外部引用。
  - `client.py`：封装带签名的 HTTP 客户端。
  - `orders.py`：构建并校验下单请求参数。
  - `trading.py`：提供交割合约交易接口（当前支持创建订单与查询订单）。
  - `market_data.py`：行情查询模块（当前支持交割合约K线数据）。
  - `exceptions.py`：自定义 API 异常。
  - `utils.py`：通用工具函数（字符串处理等）。

## AI Coding提示
如果你需要额外的api可以咨询我。
