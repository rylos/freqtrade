# Freqtrade - Panoramica del Progetto

## Scopo del Progetto
Freqtrade è un bot di trading di criptovalute gratuito e open source scritto in Python. È progettato per supportare tutti i principali exchange e essere controllato tramite Telegram o interfaccia web. Include backtesting, plotting e strumenti di gestione del denaro, oltre all'ottimizzazione delle strategie tramite machine learning.

## Tech Stack
- **Linguaggio**: Python 3.11+
- **Framework Web**: FastAPI, Uvicorn
- **Database**: SQLAlchemy (SQLite di default)
- **Analisi Tecnica**: TA-Lib, pandas, numpy
- **Machine Learning**: scikit-learn, optuna (per hyperopt), FreqAI
- **Interfaccia**: Telegram bot, WebUI
- **Testing**: pytest
- **Linting/Formatting**: ruff, mypy, isort
- **Pre-commit hooks**: configurati per qualità del codice

## Struttura del Codebase
- `freqtrade/` - Codice principale del bot
  - `strategy/` - Framework per strategie di trading
  - `exchange/` - Interfacce per exchange
  - `optimize/` - Backtesting e hyperopt
  - `rpc/` - API e interfacce (Telegram, WebUI)
  - `freqai/` - Machine learning per trading
- `user_data/` - Dati utente (strategie, configurazioni, dati)
  - `strategies/` - Strategie personalizzate (es. RyLoSStrategy.py)
  - `config.json` - Configurazione principale
- `tests/` - Test unitari
- `docs/` - Documentazione

## Caratteristiche Principali
- Trading automatico su exchange crypto
- Backtesting e ottimizzazione strategie
- Gestione rischio e position sizing
- Interfaccia Telegram e Web
- FreqAI per ML-based trading
- Supporto per futures e spot trading