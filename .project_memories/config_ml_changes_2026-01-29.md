# Config ML Changes - 2026-01-29

## Modifiche Applicate

### 1. Multi-Timeframe Implementation

**Prima**:
```json
"include_timeframes": ["5m"]
```

**Dopo**:
```json
"include_timeframes": ["5m", "15m", "2h", "4h"]
```

**Impatto**:
- Features totali: ~32 features × 4 timeframes = **128 features**
- Cattura pattern a breve (5m), medio (15m) e lungo termine (2h, 4h)
- Migliore generalizzazione ML

### 2. Train Period Days

**Prima**:
```json
"train_period_days": 3,
"backtest_period_days": 1
```

**Dopo**:
```json
"train_period_days": 15,
"backtest_period_days": 2
```

**Rationale**:
- 15 giorni = **4,320 candles @ 5m**
- Regola ML: ~10-20 samples per feature → 128 features × 15 = 1,920 samples minimo
- 4,320 candles > 1,920 → ✅ Sufficiente per evitare overfitting
- Cattura pattern bi-settimanali (weekend + weekday cycles)
- Training time: ~10-15 min su debian-lifting (30 cores)

### 3. Identifier (rimozione _v2)

**Prima**:
```json
"identifier": "rylos_mlv3_pytorch_v2"
```

**Dopo**:
```json
"identifier": "rylos_mlv3_pytorch"
```

**Impatto**:
- Torna al vecchio identifier come richiesto
- Modelli precedenti verranno riutilizzati se esistenti

### 4. Model Training Parameters Fix

**Prima**:
```json
"model_training_parameters": {
  "n_epochs": 30,
  "learning_rate": 0.001,
  "trainer_kwargs": {
    "n_steps": null
  }
}
```

**Dopo**:
```json
"model_training_parameters": {
  "learning_rate": 0.001,
  "trainer_kwargs": {
    "n_epochs": 30,
    "n_steps": null
  }
}
```

**Rationale**:
- Secondo documentazione FreqAI, `n_epochs` deve essere in `trainer_kwargs`
- Struttura corretta per PyTorch models

### 5. Pair Format Consistency

**Prima**:
```json
"pair_whitelist": ["HYPE/USDT:USDT"],
"pairlists": [
  {
    "pairs": ["HYPE/USDT"]  // ❌ Formato inconsistente
  }
]
```

**Dopo**:
```json
"pair_whitelist": ["HYPE/USDT:USDT"],
"pairlists": [
  {
    "pairs": ["HYPE/USDT:USDT"]  // ✅ Formato consistente
  }
]
```

## Feature Count Calculation

### Base Features (expand_basic)
- RSI, ATR%, StochRSI, Williams, pct_change, pct_change_vol
- BB%, MACD (3), EMA (2), CCI, VWAP, OBV
- Early warning (7): atr_spike, volume_spike, rsi_divergence, bb_squeeze, macd_decline, distance_to_low, price_acceleration
- **Total**: ~26 features

### Expanded Features (expand_all)
- RSI, BB width, Volume ratio
- Periods: 9, 21
- **Total**: 3 × 2 = 6 features

### Total per Timeframe
26 + 6 = **32 features**

### Total Multi-Timeframe
32 × 4 timeframes = **128 features**

## Data Requirements

### Minimum Candles Needed

**Formula**:
```
startup_candle_count × max_timeframe = 50 × 4h = 200 hours = 8.3 giorni
```

**Training data**:
```
train_period_days = 15 giorni = 4,320 candles @ 5m
```

**Download data for backtest**:
```
start_date = backtest_start - train_period_days - startup_margin
           = backtest_start - 15 days - 8.3 days
           = backtest_start - 23.3 days
```

**Esempio**: Per backtest 2025-01-01 to 2025-02-01:
```bash
freqtrade download-data \
  --timerange 20241208-20250201 \
  --timeframes 5m 15m 2h 4h \
  --config user_data/config_ml.json
```

## Expected Training Time

### debian-lifting (30 cores)
- Single training: ~10-15 min
- Full backtest (30 days): ~8 trainings × 15 min = **~2 hours**

### pc-work (16 threads)
- Single training: ~20-30 min
- Full backtest (30 days): ~8 trainings × 30 min = **~4 hours**

## Next Steps

1. **Delete old models** (config changed - force retraining):
```bash
# Cancella vecchio identifier (se esiste)
rm -rf user_data/models/rylos_mlv3_pytorch_v2

# Cancella nuovo identifier (per forzare retraining con nuova config)
rm -rf user_data/models/rylos_mlv3_pytorch
```

**Rationale**: Config cambiata (1 timeframe → 4 timeframes, 3 giorni → 15 giorni).
Modelli esistenti sono incompatibili e devono essere ritrainati.

2. **Download data** (se necessario):
```bash
freqtrade download-data \
  --timerange 20241215-20260129 \
  --timeframes 5m 15m 2h 4h \
  --config user_data/config_ml.json
```

3. **Test backtest** (local):
```bash
freqtrade backtesting \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --timerange 20250115-20250129
```

4. **Sync to debian-lifting** per hyperopt:
```bash
# Strategia
scp user_data/strategies/RyLoSStrategyMLv3.py marco@192.168.0.34:/opt/freqtrade/user_data/strategies/

# Config
scp user_data/config_ml.json marco@192.168.0.34:/opt/freqtrade/user_data/

# Modello PyTorch
scp user_data/freqaimodels/RyLoSPyTorchModel.py marco@192.168.0.34:/opt/freqtrade/user_data/freqaimodels/
```

5. **Hyperopt su debian-lifting**:
```bash
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate

freqtrade hyperopt \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss ProfitDrawdownDurationHyperOptLoss \
  --epochs 6000 \
  --spaces buy sell \
  --timerange 20241215-20260129 \
  -j 30
```

## Verification Checklist

- [x] Multi-timeframe: 5m, 15m, 2h, 4h
- [x] train_period_days: 15
- [x] backtest_period_days: 2
- [x] identifier: rylos_mlv3_pytorch (no _v2)
- [x] n_epochs in trainer_kwargs
- [x] Pair format consistency
- [x] Strategia già corretta (no changes needed)
