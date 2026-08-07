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

## ⚠️ Il backtest è sensibile al WALLET DI PARTENZA (scoperta 2026-07-31)
Confrontando il live col backtest sulla stessa finestra, **col wallet sbagliato si legge un profilo di rischio diverso da quello reale**:
- Stessa finestra 27-31/07, stessi dati: con `dry_run_wallet` 10000 (default config) il backtest ferma la griglia a **2 entry e zero clip unstuck** (esposizione 0.35, sotto la soglia 0.681); con `--dry-run-wallet 8200` (saldo live reale) riproduce il live quasi ordine per ordine: **3 entry + 7 clip**, entry a 58.928/57.905/56.647 contro 58.866/57.955/56.547 del live (scarti 0.1-0.2% = slippage)
- Causa: TWE, `first_order_pct` e le soglie di esposizione sono tutte proporzioni del balance, ma i gate (`next_stake > available_balance`, clip al `remaining_per_pair`, `exposure_ratio >= unstuck_threshold`) scattano su valori assoluti → a saldi diversi la griglia si carica a profondità diverse
- **Regola: in OGNI confronto live-vs-backtest passare `--dry-run-wallet <saldo reale>`**, altrimenti la conclusione sul rischio è falsata. Vale anche per lo spezzatino e per gli health check mensili
- Corollario positivo: **drift check 2026-07-31 SUPERATO** — con wallet allineato, backtest e live coincidono su timestamp di entry/exit, tag e numero di clip dei 3 trade live (vedi `mem:rylos-strategy`)

## ⚠️ Warmup: gli indicatori ricorsivi dentro finestre mobili divergono fra live e backtest (2026-08-07)
Scoperto implementando il TMF (EWM di Wilder annidato dentro uno z-score rolling). `startup_candle_count` va dimensionato su **finestra mobile + convergenza del ricorsivo**, non solo sulla finestra:
- Con warmup = 750 e rolling(576), la finestra rolling **inizia** dove l'EWM ha solo ~174 candele di storia; quel residuo contamina media e deviazione standard → l'ultimo valore differiva fino a 1,5e-1 fra dataframe corto (live) e serie intera (backtest), pari al 9,3% di errore sul fattore di stake
- Convergenza misurata: 750 → 9,3% | 1000 → 0,084% | 1200 → 0,001% | **1500 → 3e-8**
- **Test da rifare per ogni indicatore nuovo di questo tipo**: calcolare l'indicatore su N finestre casuali di lunghezza `startup_candle_count` e confrontare l'ultimo valore con quello della serie completa (`live_equivalence.py` nello scratchpad). È invisibile in backtest, si vedrebbe solo in live
- ⚠️ Corollario operativo: **alzare `startup_candle_count` sposta lo start del backtest** (freqtrade avvisa "Moving start-date by N candles"), quindi ogni confronto A/B va rifatto sulla stessa baseline — i numeri storici del T4G non sono confrontabili con quelli di un warmup diverso

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
