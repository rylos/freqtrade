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

## ✅ Allineamento librerie debian+amazon (2026-08-07)
Entrambe portate alle `requirements` del commit corrente: **ccxt 4.5.71, pandas 3.0.5, numpy 2.4.6, TA-Lib 0.7.1, technical 1.7.0, SQLAlchemy 2.0.51**. `pip check` pulito su entrambe.
- **Wheel TA-Lib 0.7.1 disponibile sia per x86_64 sia per aarch64** → nessuna compilazione, la libreria C di sistema (`libta_lib.so` vecchio stile su amazon) non serve più: il wheel la incorpora
- 🪤 **Avviso spurio `freqtrade requires TA-Lib<0.7`**: viene dai metadati di un'installazione vecchia (2026.7.dev0); il `pyproject` attuale consente `TA-Lib<0.8`. Si risolve con **`pip install -e . --no-deps`**, che rinfresca i metadati senza toccare le dipendenze
- ⭐ **REGRESSIONE T4V BIT-PERFETTA dopo l'aggiornamento**: 810 trade, **+17.008,01%** con `--dry-run-wallet 7353` su `20241205-20260807`, identica cifra per cifra al pre-aggiornamento. **TA-Lib 0.7.1 e pandas 3 non spostano di un centesimo i valori degli indicatori**
- ⚠️ **La differenza residua a 1e-15 nel `tmf_z` fra le due macchine è ARCHITETTURALE, non di versione**: con pandas e numpy ora identici il divario sull'ultima cifra resta (x86_64 contro aarch64, percorsi SIMD/FMA diversi). È irriducibile e non sparirà con nessun allineamento — ma è 15 ordini di grandezza sotto qualunque soglia decisionale. **Non inseguirla.**

## Costo di `startup_candle_count` alto in live (verificato 2026-08-07)
Domanda di Marco sul TMF a 1500 candele: il bot **non aspetta**, scarica lo storico all'avvio e poi opera subito. Misurato con chiamate pubbliche: **bybit 1.501 candele 5m in 2 chiamate = 2,80s; hyperliquid 1.502 in 1 chiamata = 0,76s**.
- Limiti in `Exchange.validate_required_startup_candles` (`exchange.py:888`): **bybit** 1.000 candele/chiamata, `ohlcv_has_history=True` → max 5 chiamate = tetto **4.999**; **hyperliquid** 5.000/chiamata ma **`ohlcv_has_history=False`** → niente paginazione, tetto **4.999 in una sola chiamata**. Oltre il tetto freqtrade solleva `ConfigurationError` e non parte
- Con 1500 siamo sotto un terzo del tetto su entrambi. Unico effetto: warning `Using 2 calls to get OHLCV` su bybit
- ⚠️ **Su una coin appena listata (<5,2 giorni) le 1500 candele non esisterebbero** e il `tmf_z` resterebbe parzialmente non scaldato
- ⚠️ **BUG ccxt 4.5.33/4.5.34 su hyperliquid**: `load_markets()` solleva `TypeError` in `fetch_spot_markets` (`mappedBase` None). L'endpoint candele funziona, ma freqtrade chiama `load_markets` all'avvio → **oggi il bot su hyperliquid non partirebbe**, indipendentemente dal TMF. Verificare con un ccxt più recente prima di considerare quella strada

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
