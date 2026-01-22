# RyLoSStrategyMLv3 - Implementazione Completata

## Architettura Finale (Opzione 2 + ML Exit)

**Obiettivo**: Mantenere strategia originale (+1009%) e aggiungere FreqAI come filtro conservativo su DCA standard E exit.

### Logica Implementata

1. **Entry**: Tradizionale multi-oscillator oversold (NO ML)
2. **DCA Emergency**: Sempre passa (NO filtro ML - protezione liquidazione)
3. **DCA Standard**: Logica tradizionale + filtro ML conservativo (predizione 1h)
4. **Exit**: Multi-oscillator overbought + ML conferma (predizione 15min) ✨ NUOVO
5. **Trailing Stop**: DISABILITATO per test ML

### Cosa Fa il ML - Spiegazione Dettagliata

**2 Target ML Diversi**:

1. **Target Long (1h)**: Per filtro DCA
```python
dataframe["&-s_close"] = (dataframe["close"].shift(-12) - dataframe["close"]) / dataframe["close"]
```

2. **Target Short (15min)**: Per conferma Exit ✨ NUOVO
```python
dataframe["&-s_close_short"] = (dataframe["close"].shift(-3) - dataframe["close"]) / dataframe["close"]
```

**Input Features (14 totali)**:
- Base: RSI(10), ATR%, StochRSI(10), Williams(10), pct_change, pct_change_vol, ADX(14)
- Espanse periodo 10: RSI_10, BB_width_10, volume_ratio_10
- Temporali: hour, day_of_week

**Modello**: PyTorch MLP
- Input: 14 features
- Output: 2 valori (predizione 1h + predizione 15min)
- Training: ogni 24h su ultimi 3 giorni (ottimizzato per VM 2 core/4GB RAM)
- Outlier detection: SVM nu=0.05

**Uso nella Strategia**:

1. **Filtro DCA Standard** (predizione 1h):
```python
ml_pred = self.get_ml_prediction(trade.pair)  # Predizione 1h
if ml_pred < self.ml_dca_block_threshold.value:  # default: -0.02
    # BLOCCA DCA se ML predice calo > 2% in 1h
    return None
```

2. **Conferma Exit** (predizione 15min) ✨ NUOVO:
```python
# Exit SOLO se:
# 1. Profit > 1.7%
# 2. ≥4 oscillatori overbought
# 3. Candela verde
# 4. ML predice < +0.5% nei prossimi 15min
ml_pred_short = self.get_ml_prediction_short(trade.pair)
if ml_pred_short < self.ml_exit_threshold.value:  # default: 0.005
    return "sell_overbought_ml"
```

**Esempi**:

**DCA (predizione 1h)**:
- ML predice +1% → DCA passa ✅
- ML predice -1% → DCA passa ✅
- ML predice -3% → DCA bloccato ❌
- Emergency DCA → ML ignorato, sempre passa ✅

**Exit (predizione 15min)** ✨ NUOVO:
- Overbought + ML predice -0.5% → Exit ✅
- Overbought + ML predice +1.5% → NO exit (lascia correre) ❌
- NO overbought + ML predice -2% → NO exit (mancano indicatori) ❌
- Profit < 1.7% → NO exit (profit insufficiente) ❌

### Risultati Backtest (20241215-20260122)

| Metrica | Originale | v3 con ML | Delta |
|---------|-----------|-----------|-------|
| Profit % | +1009% | +830.79% | -178% |
| Trades | 1681 | 1652 | -29 |
| Calmar | 130 | 107.39 | -22.61 |
| Win Rate | ~99% | 99.4% | +0.4% |
| Drawdown | ? | 36.67% | ? |
| Durata media | ~5h | 4h43m | -17m |

**DCA bloccati da ML**: 29 (1.7% del totale) - molto conservativo

### Status Attuale

1. ✅ Implementazione completata
2. ✅ Backtest iniziale eseguito (+830%)
3. 🔄 Hyperopt in corso sul server (ottimizza `ml_dca_block_threshold`)
4. ⏳ Analisi risultati hyperopt
5. ⏳ Riattivare trailing stop se risultati soddisfacenti

### Comandi

```bash
# Backtest con FreqAI
freqtrade backtesting -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --timerange 20241215-20260122

# Backtest con logging verbose
freqtrade backtesting -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --timerange 20241215-20260122 -v

# Hyperopt threshold ML
freqtrade hyperopt -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss CalmarRyLoSHyperOptLoss \
  --epochs 50 --spaces buy \
  --timerange 20241215-20260122 \
  --jobs 4
```

### File Necessari per Deploy

**Strategia e Modello**:
- `user_data/strategies/RyLoSStrategyMLv3.py` (strategia finale con dual-target ML)
- `user_data/freqaimodels/RyLoSPyTorchModel.py` (modello PyTorch)
- `user_data/config_ml.json` (config FreqAI ottimizzato per VM 2 core/4GB RAM)

**Loss Function**:
- `freqtrade/optimize/hyperopt_loss/hyperopt_loss_calmar_rylos.py`

**Dipendenze**:
```bash
pip install -e .[freqai]
```

### Note Tecniche

- **Parametri ottimizzabili**:
  - `ml_dca_block_threshold` (range: -0.05 to -0.01, default: -0.02) - Filtro DCA
  - `ml_exit_threshold` (range: -0.01 to 0.02, default: 0.005) - Conferma Exit ✨ NUOVO

- **Dual-Target ML**:
  - `&-s_close`: Predizione 1h (12 candele) per DCA
  - `&-s_close_short`: Predizione 15min (3 candele) per Exit ✨ NUOVO

- **Config ottimizzato per VM**:
  - `train_period_days: 3` (ridotto da 5)
  - `batch_size: 512` (ridotto da 1024)
  - `hidden_dim: 64` (ridotto da 128)
  - `n_layer: 2` (ridotto da 3)
  - `n_epochs: 30` (ridotto da 50)
  - `data_kitchen_thread_count: 1` (ridotto da 2)

- **Loss Function**: Calmar Ratio con penalty logaritmica durata
  - Soglia attuale: 5h (nessuna penalty fino a 5h)
  - Suggerimento: abbassare a 2h per incentivare exit rapidi

### File Obsoleti da Ignorare

- `user_data/strategies/RyLoSStrategyML.py` (v1 - abbandonata)
- `user_data/strategies/RyLoSStrategyMLv2.py` (v2 - abbandonata, ML-driven stake fallito)
