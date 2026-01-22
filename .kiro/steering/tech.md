# Technology Stack

## Language & Runtime

- **Python**: 3.11+ (supports 3.11, 3.12, 3.13, 3.14)
- **Package Manager**: pip, setuptools
- **Build System**: setuptools with pyproject.toml

## Core Dependencies

- **Exchange Integration**: ccxt (unified exchange API)
- **Data Processing**: pandas, numpy, bottleneck, numexpr
- **Technical Indicators**: TA-Lib, ft-pandas-ta, technical
- **Database**: SQLAlchemy 2.0+ (persistence via SQLite)
- **API/WebUI**: FastAPI, uvicorn, pydantic, websockets
- **Bot Interface**: python-telegram-bot
- **ML/Optimization**: scikit-learn, optuna, lightgbm, xgboost (optional)
- **Serialization**: python-rapidjson, orjson, pyarrow

## Development Tools

- **Linting/Formatting**: ruff (replaces black, flake8, isort)
- **Type Checking**: mypy, pyright
- **Testing**: pytest with plugins (pytest-cov, pytest-mock, pytest-asyncio, pytest-xdist)
- **Pre-commit**: Automated code quality checks
- **Spell Check**: codespell

## Common Commands

### Setup & Installation
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e .                    # Basic install
pip install -e .[dev]              # Development install with all extras
pip install -e .[hyperopt,plot]    # Specific features
```

### Testing
```bash
pytest                                    # Run all tests
pytest tests/test_<file>.py              # Test specific file
pytest tests/test_<file>.py::test_method # Test specific method
pytest -n auto                           # Parallel execution
```

### Code Quality
```bash
pre-commit install              # Install git hooks
pre-commit run -a              # Run all checks manually
ruff check .                   # Lint code
ruff format .                  # Format code
mypy freqtrade                 # Type checking
```

### Running the Bot
```bash
freqtrade trade --config config.json           # Live trading
freqtrade trade --config config.json --dry-run # Paper trading
freqtrade backtesting --config config.json     # Backtest strategy
freqtrade hyperopt --config config.json        # Optimize parameters
freqtrade download-data --config config.json   # Download market data
freqtrade webserver --config config.json       # Start web interface
```

### Docker
```bash
docker-compose up -d           # Start bot in container
docker-compose logs -f         # View logs
```

## Optional Features

Install with extras for additional functionality:
- `[plot]`: Plotting capabilities (plotly)
- `[hyperopt]`: Strategy optimization (scipy, optuna)
- `[freqai]`: Machine learning features
- `[freqai_rl]`: Reinforcement learning (torch, stable-baselines3)
- `[jupyter]`: Jupyter notebook support
- `[all]`: All optional features
- `[dev]`: All features + development tools
