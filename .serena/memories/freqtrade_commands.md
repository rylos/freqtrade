# Freqtrade Commands

## Core Commands
```bash
# Trading
freqtrade trade --config user_data/config.json --dry-run
freqtrade webserver --config user_data/config.json

# Strategy Testing
freqtrade backtesting --strategy RyLoSStrategy --timerange 20240101-20241231
freqtrade hyperopt --strategy RyLoSStrategy --hyperopt-loss CalmarRyLoSHyperOptLoss --epochs 100

# Data
freqtrade download-data --timerange 20240101-20241231
freqtrade list-strategies
```

## Development
```bash
# Setup
pip install -e .[dev]
pre-commit run -a

# Linting
ruff check . && ruff format .
mypy freqtrade

# Testing
pytest tests/test_strategy/
```

## System (Arch)
```bash
pacman -S python python-pip git
yay -S ta-lib
```