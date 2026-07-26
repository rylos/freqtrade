# Technology Stack (2026-07-21)

## Freqtrade
- Versione: 2026.7-dev (fork riallineato a upstream develop)
- Python >= 3.11 (pc-work 3.13, debian 3.11); install: `pip install -e '.[hyperopt,plot]'` (zsh richiede quotes)
- Docs: https://www.freqtrade.io/en/develop/
- Hyperopt: backend optuna, sampler NSGAIIISampler, loss = scalare unico (NO multi-obiettivo nativo); `-j N` per parallelismo; risultati in `.fthypt` (jsonl per epoch: loss, params, results_metrics incl. daily_profit)
- Pre-commit hook rotto nel venv → committare con `--no-verify`

## Semantiche backtest verificate (probe empirica)
- In backtest i callback (`custom_exit`, `adjust_trade_position`) vedono `iloc[-1]` = ultima candela CHIUSA e `current_rate` = open della corrente → pattern `iloc[-1]` legittimo, nessun lookahead
- `populate_exit_trend` esegue all'open della candela SUCCESSIVA (ritardo 5m) → NFI e noi lo lasciamo vuoto, tutti gli exit via callback
- `strategy_safe_wrapper` fa deepcopy del Trade a ogni callback (~40% del tempo) → patch fork con opt-out `disable_trade_deepcopy`
- Partial exit: `current_profit` è sul residuo, non sull'iniziale (NFI ricalcola dagli ordini; noi usiamo markup sul prezzo)

## Stoploss e leva
- `stoploss` = rischio sul capitale, NON movimento prezzo: trigger prezzo = stoploss/leva (4x: -0.20 → -5% prezzo)
- Rischio reale governato da TWE (esposizione/balance), non dalla leva exchange (che determina solo margine/liquidazione) — pattern passivbot

## Comandi
```bash
pytest -n auto                     # test
ruff check . && ruff format .      # lint (ruff via pip nel venv)
freqtrade backtesting -c user_data/config.json --strategy RyLoSStrategy --timerange ...
freqtrade hyperopt ... --hyperopt-loss SortinoRyLoSHyperOptLoss
freqtrade download-data -c ... --timeframe 5m --timerange 20240801-
freqtrade list-data -c ... --show-timerange
```
