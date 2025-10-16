# Comandi Suggeriti per Freqtrade

## Comandi Principali del Bot
```bash
# Avviare il bot in modalità live
freqtrade trade --config user_data/config.json

# Avviare in dry-run (simulazione)
freqtrade trade --config user_data/config.json --dry-run

# Backtesting di una strategia
freqtrade backtesting --config user_data/config.json --strategy RyLoSStrategy

# Hyperopt (ottimizzazione parametri)
freqtrade hyperopt --config user_data/config.json --strategy RyLoSStrategy --hyperopt-loss SharpeHyperOptLoss --epochs 100

# Avviare WebUI
freqtrade webserver --config user_data/config.json

# Scaricare dati storici
freqtrade download-data --config user_data/config.json --timerange 20230101-20231231
```

## Comandi di Sviluppo
```bash
# Installare dipendenze di sviluppo
pip install -e .[dev]

# Pre-commit (linting completo)
pre-commit run -a

# Linting individuale
ruff check .
ruff format .
mypy freqtrade

# Test
pytest                                    # Tutti i test
pytest tests/test_strategy/              # Test strategie
pytest tests/test_backtesting.py         # Test backtesting

# Creare nuova strategia
freqtrade new-strategy --strategy MyStrategy

# Validare configurazione
freqtrade show-config --config user_data/config.json
```

## Comandi Sistema (Arch Linux)
```bash
# Gestione pacchetti
pacman -S python python-pip git
yay -S ta-lib  # TA-Lib da AUR

# Git workflow
git checkout develop
git pull origin develop
git checkout -b feature/my-feature

# Ambiente virtuale
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Comandi Utili per Strategie
```bash
# Testare strategia specifica
freqtrade backtesting --strategy RyLoSStrategy --timerange 20230101-20231231

# Analisi risultati backtesting
freqtrade backtesting-analysis --config user_data/config.json

# Plot dei risultati
freqtrade plot-dataframe --strategy RyLoSStrategy --timerange 20230101-20230201

# Listare strategie disponibili
freqtrade list-strategies
```
