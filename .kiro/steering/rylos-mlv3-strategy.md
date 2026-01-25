# RyLoS Strategy MLv3 - Weighted Multi-Horizon ML

Strategia ML-driven con predizioni pesate su 3 orizzonti temporali (5m, 15m, 30m).

## Architettura

### Predizioni ML (3 Target)
```python
# set_freqai_targets()
"&-s_close_5m"   # Variazione % prezzo tra 1 candle (5 minuti)
"&-s_close_15m"  # Variazione % prezzo tra 3 candles (15 minuti)
"&-s_close_30m"  # Variazione % prezzo tra 6 candles (30 minuti)
```

### Weighted Prediction Formula
```python
weighted_pred = (
    pred_5m * ml_weight_5m +
    pred_15m * ml_weight_15m +
    pred_30m * ml_weight_30m
) / (ml_weight_5m + ml_weight_15m + ml_weight_30m)
```

## Parametri Ottimizzabili (16 totali)

### ML Weights (3 parametri - buy space)
```python
ml_weight_5m    = 0.1 to 2.0  (default: 0.5)   # Peso orizzonte 5m
ml_weight_15m   = 0.1 to 2.0  (default: 1.0)   # Peso orizzonte 15m
ml_weight_30m   = 0.1 to 2.0  (default: 1.5)   # Peso orizzonte 30m
```

**Interpretazione**:
- Peso basso (0.1-0.5): orizzonte poco affidabile/rumoroso
- Peso medio (0.8-1.2): orizzonte standard
- Peso alto (1.5-2.0): orizzonte più affidabile per decisioni

### ML Thresholds (3 parametri)
```python
ml_entry_threshold = -0.01 to 0.02  (default: 0.001, buy space)
ml_dca_threshold   = -0.02 to 0.02  (default: 0.0, buy space)
ml_exit_threshold  = -0.02 to 0.005 (default: -0.001, sell space)
```

### DCA Core (3 parametri - buy space)
```python
first_order_pct     = 0.005 to 0.03  (default: 0.029)  # % balance primo ordine
dca_multiplier      = 1.5 to 3.0     (default: 1.991)  # Moltiplicatore stake
dca_atr_multiplier  = 0.5 to 3.0     (default: 2.306)  # Peso ATR su distanza
```

### ML Dynamic DCA Distance (4 parametri - buy space)
```python
ml_dca_distance_tight = 0.015 to 0.025  (default: 0.018)  # Distanza stretta
ml_dca_distance_wide  = 0.035 to 0.055  (default: 0.045)  # Distanza ampia
ml_dca_pred_min       = -0.02 to 0.0    (default: -0.01)  # Pred min mapping
ml_dca_pred_max       = 0.01 to 0.04    (default: 0.02)   # Pred max mapping
```

**Logica**: Predizioni positive → distanza tight (DCA aggressivo), predizioni negative → distanza wide (DCA conservativo)

### ML Dynamic Stoploss (5 parametri - sell space)
```python
ml_stoploss_tight           = -0.18 to -0.08  (default: -0.12)
ml_stoploss_loose           = -0.30 to -0.18  (default: -0.25)
ml_stoploss_pred_min        = -0.10 to -0.02  (default: -0.05)
ml_stoploss_pred_max        = -0.02 to 0.02   (default: 0.0)
ml_stoploss_activation_loss = -0.18 to -0.05  (default: -0.10)
```

**Attivazione**: Solo quando loss > activation_loss E DCA esaurito (no capital/max orders)

### Exit (1 parametro - sell space)
```python
min_profit_for_overbought_exit = 0.01 to 0.10  (default: 0.017)  # 1.7%
```

## Logica Entry/DCA/Exit

### First Entry
```python
# Condizione
if weighted_pred > ml_entry_threshold:
    enter_long = 1
    
# Tag esempio
"buy_ml_w0.0125_5m:0.01_15m:0.02_30m:0.005"
```

### DCA Standard
```python
# Condizioni (tutte devono essere vere)
1. Prezzo < last_order_price (solo in discesa)
2. Distanza >= dynamic_distance (basata su ML + ATR)
3. Cooldown 2 candles dall'ultimo DCA
4. weighted_pred > ml_dca_threshold (filtro ML)
5. Capital disponibile e limiti non superati

# Stake progressivo
stake = first_order_pct * (dca_multiplier ^ entry_count)

# Tag esempio
"dca_ml_w0.0089_-5.2%"
```

### Exit
```python
# Condizioni (entrambe devono essere vere)
1. current_profit > min_profit_for_overbought_exit
2. weighted_pred < ml_exit_threshold

# Tag esempio
"sell_ml_w-0.0032_+8.5%"
```

## Features ML (19 totali)

### Base (14 features)
```python
"%-rsi"              # RSI(10)
"%-atr_pct"          # ATR(10) / close * 100
"%-stochrsi"         # StochRSI(10,5,3) fastk
"%-williams"         # Williams %R(10)
"%-pct_change"       # Close pct_change
"%-pct_change_vol"   # Volume pct_change
"%-bb_percent"       # BB%(20,2)
"%-macd"             # MACD(12,26,9)
"%-macd_signal"      # MACD signal
"%-macd_hist"        # MACD histogram
"%-ema_9"            # EMA(9)
"%-ema_21"           # EMA(21)
"%-cci"              # CCI(10)
"%-vwap"             # VWAP(20)
"%-obv_norm"         # OBV normalized
"%-adx"              # ADX(14)
```

### Expanded (3 features × periodo 10)
```python
"%-rsi_10"           # RSI espanso
"%-bb_width_10"      # BB width espanso
"%-volume_ratio_10"  # Volume ratio espanso
```

**Note**: Features temporali (hour, day_of_week) RIMOSSE per evitare bias temporale

## Config FreqAI

```json
{
  "freqai": {
    "enabled": true,
    "purge_old_models": 2,
    "train_period_days": 10,
    "backtest_period_days": 2,
    "identifier": "rylos_mlv3_pytorch",
    "feature_parameters": {
      "include_timeframes": ["5m"],
      "include_corr_pairlist": [],
      "label_period_candles": 12,
      "include_shifted_candles": 0,
      "DI_threshold": 0,
      "weight_factor": 0,
      "principal_component_analysis": false,
      "use_SVM_to_remove_outliers": true,
      "svm_params": {
        "shuffle": false,
        "nu": 0.05
      },
      "indicator_periods_candles": [10]
    },
    "data_split_parameters": {
      "test_size": 0.25,
      "shuffle": false
    },
    "model_training_parameters": {
      "learning_rate": 3e-4,
      "trainer_kwargs": {
        "n_steps": null,
        "batch_size": 64,
        "n_epochs": 10
      },
      "model_kwargs": {
        "hidden_dim": 64,
        "dropout_percent": 0.2,
        "n_layer": 2
      }
    }
  }
}
```

## Modello PyTorch

```python
# user_data/freqaimodels/RyLoSPyTorchModel.py
from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor
from freqtrade.freqai.torch.PyTorchDataConvertor import DefaultPyTorchDataConvertor
import torch

class RyLoSPyTorchModel(BasePyTorchRegressor):
    @property
    def data_convertor(self):
        return DefaultPyTorchDataConvertor(target_tensor_type=torch.float)
```

## Risk Management

### Limiti Globali
```python
global_limit = total_balance * leverage  # balance * 4
per_pair_limit = global_limit / max_open_trades
```

### Calcolo Max Orders Dinamico
```python
# Simula ordini fino al limite per pair
max_orders = calculate_max_orders(total_balance)
# Tipicamente 8-12 ordini con parametri default
```

### Cooldown DCA
```python
dca_cooldown_candles = 2  # FISSO - 10 minuti (2 × 5m)
```

## Hyperopt Command

```bash
ssh marco@debian.ts
cd /opt/freqtrade
source .venv/bin/activate

freqtrade hyperopt \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss CalmarRyLoSHyperOptLoss \
  --epochs 6000 \
  --spaces buy sell \
  --timerange 20241215-20260126 \
  -j 30
```

## Loss Function: CalmarRyLoSHyperOptLoss

```python
# freqtrade/optimize/hyperopt_loss/hyperopt_loss_calmar_rylos.py
calmar_ratio = total_return / max_drawdown

# Duration penalty (penalizza trade lunghi)
if avg_duration <= 2h:
    penalty = 0
elif 2h < avg_duration <= 10h:
    penalty = log(1 + normalized)  # 0 to 0.693
else:
    penalty = 0.693  # capped

result = -calmar_ratio / (1 + penalty)
```

**Obiettivo**: Massimizzare Calmar Ratio penalizzando trade con duration > 2h (scalping focus)

## Configurazione Bot

```json
{
  "max_open_trades": 1,
  "stake_amount": "unlimited",
  "tradable_balance_ratio": 1.0,
  "trading_mode": "futures",
  "margin_mode": "isolated",
  "entry_pricing": {
    "price_side": "other",
    "use_order_book": true,
    "order_book_top": 2
  },
  "exit_pricing": {
    "price_side": "other",
    "use_order_book": true,
    "order_book_top": 2
  }
}
```

## Note Implementazione

### Trailing Stop
```python
trailing_stop = False  # DISABILITATO per test ML
```

### Auto-Reduce
```python
auto_reduce_enabled = False  # DISABILITATO - causava loss
```

### Stoploss
```python
stoploss = -0.22  # Fallback, overridden da custom_stoploss ML-driven
```

### ROI
```python
minimal_roi = {"0": 0.5}  # DISABILITATO - usa solo custom_exit
```

## Workflow Sviluppo

1. **Training modelli**: Automatico durante backtest/hyperopt
2. **Hyperopt**: Ottimizza 16 parametri su debian.ts (30 jobs paralleli)
3. **Validazione**: Analizza risultati, verifica overfitting
4. **Deploy**: 
   - Dry-run su AWS (test con dati live)
   - Live trading dopo conferma stabilità

## File Principali

```
user_data/
├── strategies/
│   └── RyLoSStrategyMLv3.py           # Strategia principale
├── freqaimodels/
│   └── RyLoSPyTorchModel.py           # Modello PyTorch
├── config_ml.json                      # Config FreqAI
└── models/
    └── rylos_mlv3_pytorch/             # Modelli trainati

freqtrade/optimize/hyperopt_loss/
└── hyperopt_loss_calmar_rylos.py      # Loss function
```

## Sync Files to Servers

```bash
# debian.ts (hyperopt)
scp user_data/strategies/RyLoSStrategyMLv3.py marco@debian.ts:/opt/freqtrade/user_data/strategies/
scp user_data/freqaimodels/RyLoSPyTorchModel.py marco@debian.ts:/opt/freqtrade/user_data/freqaimodels/
scp user_data/config_ml.json marco@debian.ts:/opt/freqtrade/user_data/

# AWS (live trading)
scp user_data/strategies/RyLoSStrategyMLv3.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/strategies/
scp user_data/freqaimodels/RyLoSPyTorchModel.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/freqaimodels/
scp user_data/config_ml.json admin@amazon.ziliani.net:/opt/freqtrade/user_data/
```

## Differenze vs RyLoS Classic (Indicator-Based)

| Feature | RyLoS Classic | RyLoS MLv3 |
|---------|---------------|------------|
| **Entry Logic** | Multi-oscillator oversold (≥2/4) | Weighted ML prediction > threshold |
| **DCA Logic** | Distanza fissa + ATR | ML-driven dynamic distance + filtro weighted |
| **Exit Logic** | Multi-oscillator overbought (≥4/5) | Weighted ML prediction < threshold |
| **Parametri** | 20 (10 buy + 7 sell + 3 trailing) | 16 (13 buy + 3 sell) |
| **Indicatori** | RSI, BB%, StochRSI, Williams, ATR | 19 features ML (RSI, MACD, EMA, CCI, VWAP, OBV, etc.) |
| **Trailing Stop** | Attivo (22.7% dopo +31.5%) | Disabilitato (ML-driven exit) |
| **Stoploss** | Disabilitato (-1) | ML-driven dinamico (solo se DCA esaurito) |
| **Emergency DCA** | Trigger -12.4%, critical -14.6% | Rimosso (sostituito da ML stoploss) |

## Vantaggi MLv3

1. **Predizioni multi-orizzonte**: Cattura trend a breve (5m), medio (15m) e lungo (30m) termine
2. **Pesi ottimizzabili**: L'hyperopt trova automaticamente l'importanza relativa di ogni orizzonte
3. **Meno parametri**: 16 vs 20 (più efficiente da ottimizzare)
4. **Exit più intelligente**: Non aspetta overbought, usa predizioni ML
5. **DCA dinamico**: Distanza basata su confidence ML (tight se positivo, wide se negativo)
6. **Stoploss adattivo**: Si stringe solo quando ML prevede forte downtrend E DCA esaurito

## Svantaggi MLv3

1. **Complessità**: Richiede training modelli, più difficile da debuggare
2. **Overfitting risk**: Modelli ML possono overfit su dati storici
3. **Latenza**: Training richiede tempo (10-20 min per 10 giorni di dati)
4. **Dipendenza dati**: Performance dipende dalla qualità dei dati di training
5. **Black box**: Decisioni ML meno interpretabili rispetto a indicatori classici
