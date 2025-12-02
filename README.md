# QuantTools

这是一个用于Binance交易所API访问和交互的交易应用。

This is a trading application used for API access and interaction with the Binance exchange.
<img width="664" height="1150" alt="image" src="https://github.com/user-attachments/assets/6c447f43-36d1-4083-be21-804bd9adff3a" />


## 安装 Installation

确保安装了UV包管理器。然后运行：

Make sure you have the UV package manager installed. Then run:

```bash
uv sync
```

## 使用 Usage
根目录新建`.env`，填入下面的内容，`API_KEY`，`PRIVATE_KEY_PATH`。

Create a new `.env` file in the root directory and fill in the following content: `API_KEY`, `PRIVATE_KEY_PATH`.

```bash
uv run python quick_trade_app.py
```

## 主要功能 Features

- 统一账户信息查询
- UM期货交易（快速下单，平仓，自动化网格挂单）
- 市场数据获取

- Unified account information query
- UM futures trading (quick order placement, closing positions, automated grid order placement)
- Market data acquisition
