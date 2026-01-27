# RyLoS Strategy MLv3 - Weighted Multi-Horizon ML

Strategia ML-driven con predizioni pesate su 3 orizzonti temporali (5m, 15m, 30m) per scalping aggressivo.

## Architettura

### Configurazione Base
```python
timeframe = "5m"
can_short = False
leverage = 4.0
stoploss = -0.22  # Fallback (overridden by custom_stoploss)
minimal_roi = {"0": 0.5}  # DISABILITATO
trailing_stop = False  # DISABILITATO
```

### Target ML (5 predizioni)
```python
"&-s_close_5m"          # Variazione % prezzo tra 1 candle (5 minuti)
"&-s_close_15m"         # Variazione % prezzo tra 3 candles (15 minuti)
"&-s_close_30m"         # Variazione % prezzo tra 6 candles (30 minuti)
"&-s_max_drawdown_1h"   # Worst drawdown previsto in 1 ora (12 candles)
"&-s_max_drawdown_2h"   # Worst drawdown previsto in 2 ore (24 candles)
```

### Weighted Prediction Formula
```python
weighted_pred = (
    pred_5m * ml_weight_5m +
    pred_15m * ml_weight_15m +
    pred_30m * ml_weight_30m
) / (ml_weight_5m + ml_weight_15m + ml_weight_30m)
```

## Parametri Ottimizzabili (20 totali)

### ML Weights (3 parametri - buy space)
```python
ml_weight_5m  = 0.1 to 3.0  (default: 0.23)   # Peso orizzonte 5m
ml_weight_15m = 0.1 to 3.0  (default: 0.45)   # Peso orizzonte 15m
ml_weight_30m = 0.1 to 3.0  (default: 1.95)   # Peso orizzonte 30m
```

**Range espanso a 3.0**: permette al 5m di dominare per scalping rapido

### ML Thresholds (2 parametri - buy space)
```python
ml_entry_threshold = -0.01 to 0.01  (default: 0.0049)  # Entry quando weighted_pred > threshold
ml_dca_threshold   = -0.02 to 0.02  (default: 0.0021)  # DCA quando weighted_pred > threshold
```

### DCA Core (3 parametri - buy space)
```python
first_order_pct    = 0.005 to 0.03  (default: 0.0134)  # % balance primo ordine
dca_multiplier     = 1.5 to 3.0     (default: 2.919)   # Moltiplicatore stake progressivo
dca_atr_multiplier = 0.5 to 3.0     (default: 0.642)   # Peso ATR su distanza DCA
```

### ML Dynamic DCA Distance (4 parametri - buy space)
```python
ml_dca_distance_tight = 0.015 to 0.025  (default: 0.0199)  # Distanza stretta (pred positivo)
ml_dca_distance_wide  = 0.035 to 0.055  (default: 0.0478)  # Distanza ampia (pred negativo)
ml_dca_pred_min       = -0.02 to 0.0    (default: -0.0128) # Pred min per mapping
ml_dca_pred_max       = 0.01 to 0.04    (default: 0.0256)  # Pred max per mapping
```

**Logica**: Predizioni positive → distanza stretta (DCA aggressivo), predizioni negative → distanza ampia (DCA conservativo)

### ML Exit (2 parametri - sell space)
```python
ml_exit_threshold      = -0.01 to 0.01  (default: -0.001)  # Exit quando pred_5m < threshold
min_profit_for_ml_exit = 0.005 to 0.03 (default: 0.01)    # Profit minimo per ML exit
```

**FOCUS 5M**: Exit basato SOLO su predizione 5m (non weighted), per reazione veloce

### Crash Detection (1 parametro - sell space)
```python
crash_detection_threshold = -0.10 to -0.03  (default: -0.06)  # Drop % in 15min per exit immediato
```

### ML Drawdown Prediction (2 parametri - sell space)
```python
ml_drawdown_1h_threshold = -0.15 to -0.05  (default: -0.10)  # Exit preventivo se pred_dd_1h < threshold
ml_drawdown_2h_threshold = -0.20 to -0.08  (default: -0.15)  # Exit preventivo se pred_dd_2h < threshold
```

### ML Confidence Stake Sizing (2 parametri - buy space - OPZIONALE)
```python
ml_stake_confidence_enabled = False  # Set to True per abilitare
ml_confidence_min = -0.02 to 0.0   (default: -0.0192)  # Pred min → stake 0.5x
ml_confidence_max = 0.01 to 0.05   (default: 0.0275)   # Pred max → stake 1.5x
```

### Fixed Parameters
```python
dca_cooldown_candles = 2  # FISSO - 10 minuti (2 × 5m)
fixed_stoploss = -0.20    # Fallback stoploss
```

## Logica Entry

### First Entry
```python
# Condizione
weighted_pred > ml_entry_threshold

# Calcolo weighted_pred
weighted_pred = (pred_5m * w_5m + pred_15m * w_15m + pred_30m * w_30m) / (w_5m + w_15m + w_30m)

# Tag esempio
"buy_ml_w0.0125_5m:0.01_15m:0.02_30m:0.005"
```

### Stake Amount
```python
# Base stake
base_stake = total_balance * first_order_pct

# Optional: ML confidence multiplier (se abilitato)
if ml_stake_confidence_enabled:
    avg_pred = (pred_5m + pred_15m + pred_30m) / 3
    confidence_multiplier = 0.5 to 1.5  # Linear mapping da ml_confidence_min a ml_confidence_max
    base_stake = base_stake * confidence_multiplier

# Limiti
max_allowed_stake = min(remaining_global / 4, per_pair_limit / 4)
final_stake = min(base_stake, max_allowed_stake, max_stake)
```

## Logica DCA

### Condizioni (tutte devono essere vere)
```python
1. No ordini aperti (trade.has_open_orders == False)
2. Cooldown rispettato (2 candles dall'ultimo DCA)
3. Max orders non superato (calcolato dinamicamente)
4. Limite globale non superato (< 95% del limite)
5. Available balance sufficiente
6. Prezzo < last_order_rate (solo in discesa)
7. Distanza >= dynamic_distance
8. weighted_pred > ml_dca_threshold (filtro ML)
```

### Dynamic Distance Calculation
```python
# Step 1: Base distance da ML confidence
avg_prediction = (pred_5m + pred_15m + pred_30m) / 3
clamped_pred = clamp(avg_prediction, ml_dca_pred_min, ml_dca_pred_max)

# Linear interpolation: [min_pred, max_pred] → [wide, tight]
# INVERTED: positive predictions → TIGHT distance
distance_ratio = 1.0 - (clamped_pred - min_pred) / (max_pred - min_pred)
base_distance = tight + distance_ratio * (wide - tight)

# Step 2: Apply ATR multiplier
atr_pct = atr / current_rate
dynamic_distance = base_distance * (1 + atr_pct * dca_atr_multiplier)
```

### Stake Progressivo
```python
entry_count = trade.nr_of_successful_entries
next_stake_pct = first_order_pct * (dca_multiplier ** entry_count)
next_stake = total_balance * next_stake_pct

# Limiti per pair e globali
if next_stake > limits:
    next_stake = remaining_limit / 4
    if next_stake < min_stake:
        return None  # Blocca DCA
```

### Tag
```python
"dca_ml_w0.0089_-5.2%"  # weighted_pred + current_profit
```

## Logica Exit

### ML Exit (Focus 5m)
```python
# Condizioni (entrambe devono essere vere)
1. current_profit > min_profit_for_ml_exit  # default: 1%
2. pred_5m < ml_exit_threshold              # default: -0.001

# Comportamento
→ Exit immediato quando predizione 5m è negativa
→ Focus su orizzonte immediato per scalping veloce

# Tag
"sell_ml_5m-0.0032_+8.5%"
```

**Vantaggi**:
- ✅ Exit veloce basato su predizione 5m (non weighted)
- ✅ Ottimizzato per scalping rapido
- ✅ Hyperoptabile: trova soglia ottimale (-0.01 a +0.01)

## Logica Stoploss (5 Livelli)

### LIVELLO 0: ML Drawdown Prediction (Preventive Exit - Massima Priorità)
```python
# Condizioni (una delle due)
pred_drawdown_1h < ml_drawdown_1h_threshold  # default: -10%
pred_drawdown_2h < ml_drawdown_2h_threshold  # default: -15%

# Comportamento
return current_profit + 0.005  # Exit con buffer +0.5%
```

**Vantaggi**:
- ✅ Exit preventivo PRIMA che il drawdown si verifichi
- ✅ Anticipa crash basandosi su predizioni ML
- ✅ Hyperoptabile: trova soglie ottimali

### LIVELLO 1: Crash Detection (Reactive Exit)
```python
# Condizioni (entrambe)
drop_3_candles < crash_detection_threshold  # default: -6% in 15min
drop_sustained = (price < price_2_ago AND price < price_1_ago)  # Conferma 2 candele

# Comportamento
return current_profit + 0.01  # Exit immediato con buffer
```

**Vantaggi**:
- ✅ Protegge da flash crash e dump improvvisi
- ✅ Anti-wick: richiede conferma su 2 candele
- ✅ Hyperoptabile: trova soglia ottimale (-10% a -3%)

### LIVELLO 2: Breakeven Move
```python
# Condizione
if current_profit > 0.02:  # +2% profit
    return 0.005  # Stoploss a breakeven (+0.5%)
```

**Vantaggi**:
- ✅ Protegge capital dopo primi profit
- ✅ Garantisce piccolo profit minimo

### LIVELLO 3: Trailing Stop
```python
# Condizione
if current_profit > 0:
    trailing_stoploss = current_profit - 0.03  # Trail 3% dietro
    return max(trailing_stoploss, fixed_stoploss)
```

**Vantaggi**:
- ✅ Protegge guadagni quando in profit
- ✅ Trail 3% dietro current profit

### LIVELLO 4: Fixed Stoploss (Fallback)
```python
return fixed_stoploss  # -20%
```

### Priorità
1. ML Drawdown Prediction (preventivo)
2. Crash Detection (reattivo)
3. Breakeven Move (se profit > 2%)
4. Trailing Stop (se profit > 0)
5. Fixed Stoploss (fallback)

## Features ML (26 totali)

### Base (16 features)
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

### Early Warning (7 features per drawdown prediction)
```python
"%-atr_spike"           # ATR spike (volatility increase)
"%-volume_spike"        # Volume spike (panic selling/buying)
"%-rsi_divergence"      # RSI divergence (momentum reversal)
"%-bb_squeeze"          # Bollinger Band squeeze (pre-breakout)
"%-macd_decline"        # MACD histogram decline (momentum loss)
"%-distance_to_low"     # Distance to recent low (support proximity)
"%-price_acceleration"  # Price acceleration (rate of change)
```

### Expanded (3 features × periodo 10)
```python
"%-rsi_10"           # RSI espanso
"%-bb_width_10"      # BB width espanso
"%-volume_ratio_10"  # Volume ratio espanso
```

**Note**: Features temporali (hour, day_of_week) RIMOSSE per evitare bias temporale

## Risk Management

### Limiti Globali
```python
global_limit = total_balance * leverage  # balance * 4
per_pair_limit = global_limit / max_open_trades
```

### Calcolo Max Orders Dinamico
```python
# Simula ordini fino al limite per pair
cumulative_stake = 0
for i in range(20):
    stake = total_balance * first_order_pct * (dca_multiplier ** i)
    position_value = stake * 4
    if cumulative_stake + position_value > per_pair_limit:
        break
    cumulative_stake += position_value
    order_count += 1

max_orders = order_count - 1  # -1 perché primo ordine non conta
```

**Tipicamente**: 8-12 ordini con parametri default

### Cooldown DCA
```python
dca_cooldown_candles = 2  # FISSO - 10 minuti (2 × 5m)
```

## Config FreqAI

```json
{
  "freqai": {
    "enabled": true,
    "purge_old_models": 2,
    "train_period_days": 3,
    "backtest_period_days": 1,
    "identifier": "rylos_mlv3_pytorch",
    "feature_parameters": {
      "include_timeframes": ["5m"],
      "include_corr_pairlist": [],
      "label_period_candles": 12,
      "include_shifted_candles": 0,
      "DI_threshold": 0.9,
      "weight_factor": 0.9,
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
      "learning_rate": 0.001,
      "n_epochs": 30,
      "batch_size": 512,
      "model_kwargs": {
        "hidden_dim": 64,
        "dropout_percent": 0.2,
        "n_layer": 2
      },
      "trainer_kwargs": {
        "n_steps": null,
        "drop_last_batch": true
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

## Hyperopt

### Command
```bash
ssh marco@debian.ts
cd /opt/freqtrade
source .venv/bin/activate

freqtrade hyperopt \
  -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss ProfitDrawdownDurationHyperOptLoss \
  --epochs 6000 \
  --spaces buy sell \
  --timerange 20241215-20260126 \
  -j 30
```

### Loss Function: ProfitDrawdownDurationHyperOptLoss (RECOMMENDED)

```python
total_profit = results["profit_abs"].sum()
trade_duration = results["trade_duration"].mean()

# Drawdown penalty (progressiva sopra 20%)
if max_drawdown > 30%:
    drawdown_penalty = base + (excess * profit * 4)  # Aggressiva
elif max_drawdown > 20%:
    drawdown_penalty = (excess * profit * 2)  # Moderata
else:
    drawdown_penalty = 0

# Duration penalty (percentuale logaritmica sopra 5h)
if duration <= 5h:
    duration_penalty = 0
else:
    hours_over = (duration - 5h) / 60
    penalty_pct = log(1 + hours_over) / 10
    duration_penalty = penalty_pct * profit

result = -profit + drawdown_penalty + duration_penalty
```

**Obiettivo**: Massimizzare profit totale con penalità drawdown (>20%) e duration (>5h)

**Esempi**:
- 10,000 profit, 15% drawdown, 3h → result = -10,000 (best)
- 10,000 profit, 25% drawdown, 3h → result = -9,000 (5% penalty)
- 10,000 profit, 15% drawdown, 24h → result = -7,000 (30% penalty)

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
└── hyperopt_loss_profit_drawdown_duration.py  # Loss function
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

## Differenze vs RyLoS Classic

| Feature | RyLoS Classic | RyLoS MLv3 |
|---------|---------------|------------|
| **Entry** | Multi-oscillator oversold (≥2/4) | Weighted ML prediction > threshold |
| **DCA** | Distanza fissa + ATR | ML-driven dynamic distance + filtro weighted |
| **Exit** | Multi-oscillator overbought (≥4/5) | ML prediction 5m < threshold |
| **Parametri** | 20 (10 buy + 7 sell + 3 trailing) | 20 (15 buy + 5 sell) |
| **Indicatori** | RSI, BB%, StochRSI, Williams, ATR | 26 features ML |
| **Trailing** | Attivo (22.7% dopo +31.5%) | In custom_stoploss (3% trail) |
| **Stoploss** | Disabilitato (-1) | ML-driven 5 livelli |

## Vantaggi MLv3

1. **Predizioni multi-orizzonte**: Cattura trend a breve (5m), medio (15m) e lungo (30m) termine
2. **Pesi ottimizzabili**: Hyperopt trova automaticamente l'importanza relativa di ogni orizzonte
3. **Exit intelligente**: Basato su predizione 5m per reazione veloce
4. **DCA dinamico**: Distanza basata su confidence ML (tight se positivo, wide se negativo)
5. **Stoploss preventivo**: ML drawdown prediction anticipa crash prima che si verifichino
6. **Crash detection**: Anti-wick con conferma su 2 candele

## Svantaggi MLv3

1. **Complessità**: Richiede training modelli, più difficile da debuggare
2. **Overfitting risk**: Modelli ML possono overfit su dati storici
3. **Latenza**: Training richiede tempo (10-20 min per 10 giorni di dati)
4. **Dipendenza dati**: Performance dipende dalla qualità dei dati di training
5. **Black box**: Decisioni ML meno interpretabili rispetto a indicatori classici
