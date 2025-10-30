# Freqtrade Project Overview

## Description
Open-source crypto trading bot in Python 3.11+. Supports major exchanges, Telegram/WebUI control, backtesting, hyperopt, and FreqAI ML.

## Tech Stack
- **Core**: Python, FastAPI, SQLAlchemy, TA-Lib
- **ML**: scikit-learn, optuna, FreqAI
- **Tools**: pytest, ruff, mypy, pre-commit

## Structure
```
freqtrade/
├── strategy/          # Trading strategies framework
├── exchange/          # Exchange interfaces  
├── optimize/          # Backtesting & hyperopt
├── rpc/              # Telegram & WebUI
└── freqai/           # ML trading

user_data/
├── strategies/       # Custom strategies (RyLoSStrategy.py)
└── config.json      # Main config
```

## Key Features
- Automated crypto trading
- Strategy backtesting & optimization
- Risk management & position sizing
- Telegram/Web interfaces
- ML-based trading (FreqAI)