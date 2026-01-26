# RyLoS Strategy MLv3 - Weighted Multi-Horizon ML

Strategia ML-driven con predizioni pesate su 3 orizzonti temporali (5m, 15m, 30m).

## Ultimo Hyperopt (2026-01-26)

**Risultati**: 184 trade, 98.9% win rate, +1,375% profit, 33.49% max drawdown, 20h 35m avg duration

**Analisi**:
- ✅ Win rate eccellente (182/184)
- ✅ Profit assoluto molto alto (137k USDT)
- ⚠️ Duration troppo alta (20h vs target 5h) → penalty logaritmica pesante
- ⚠️ Drawdown elevato (33.49% > 20%) → penalty attiva con nuova loss function
- ⚠️ Exit molto conservativo (9.51% profit minimo) → trade lunghi

## Modifiche per Scalping (2026-01-26)

### Range Espansi
- `ml_entry_threshold`: -0.01 to 0.01 (era -0.01 to 0.02) → entry più facile
- `ml_exit_threshold`: -0.01 to 0.01 (era -0.03 to 0.02) → exit più reattivo
- `min_profit_for_overbought_exit`: 0.005 to 0.10 (era 0.01 to 0.10) → da 0.5%
- `ml_weight_*`: 0.1 to 3.0 (era 0.1 to 2.0) → 5m può dominare

### ROI Table Attivata
```python
minimal_roi = {
    "0": 0.10, "30": 0.05, "60": 0.03, "120": 0.02, "240": 0.01
}
```

### Trailing Stop Attivato
```python
trailing_stop = True
trailing_stop_positive = 0.01  # 1%
trailing_stop_positive_offset = 0.02  # +2%
```

### Loss Function Aggiornata
- Drawdown penalty **esponenziale continua** dal 20%: formula `(excess^1.5) * 6`
- Duration penalty da **5h** (invariato)

**Prossimi step**:
1. Copiare file su debian.ts
2. Lanciare hyperopt con `--spaces buy sell roi trailing`
3. Aspettarsi: 500-1000 trade, profit medio 2-3%, duration 1-3h

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

## Parametri Ottimizzabili (18 totali) - RANGE ESPANSI PER SCALPING (2026-01-26)

### ML Weights (3 parametri - buy space) - RANGE ESPANSO
```python
ml_weight_5m    = 0.1 to 3.0  (default: 0.23)   # Peso orizzonte 5m - ESPANSO per scalping
ml_weight_15m   = 0.1 to 3.0  (default: 0.45)   # Peso orizzonte 15m - ESPANSO
ml_weight_30m   = 0.1 to 3.0  (default: 1.95)   # Peso orizzonte 30m - ESPANSO
```

**Interpretazione**:
- Range espanso a 3.0 permette al 5m di dominare per scalping rapido
- Hyperopt può trovare configurazioni aggressive (es. 5m=2.5, 15m=1.0, 30m=0.5)

### ML Thresholds (3 parametri) - RANGE ESPANSO
```python
ml_entry_threshold = -0.01 to 0.01  (default: 0.0049, buy space)   # ESPANSO: entry più facile
ml_dca_threshold   = -0.02 to 0.02  (default: 0.0021, buy space)   # Invariato
ml_exit_threshold  = -0.01 to 0.01  (default: -0.001, sell space)  # REINTEGRATO: exit ML-driven
```

**Cambiamenti**:
- `ml_entry_threshold`: ora può scendere a -0.01 (entry anche con predizioni negative)
- `ml_exit_threshold`: **REINTEGRATO** - exit quando weighted_pred < threshold
- Range ±0.01 per exit più reattivo

### DCA Core (3 parametri - buy space)
```python
first_order_pct     = 0.005 to 0.03  (default: 0.0134)  # % balance primo ordine
dca_multiplier      = 1.5 to 3.0     (default: 2.919)   # Moltiplicatore stake
dca_atr_multiplier  = 0.5 to 3.0     (default: 0.642)   # Peso ATR su distanza
```

### ML Dynamic DCA Distance (4 parametri - buy space)
```python
ml_dca_distance_tight = 0.015 to 0.025  (default: 0.0199)  # Distanza stretta
ml_dca_distance_wide  = 0.035 to 0.055  (default: 0.0478)  # Distanza ampia
ml_dca_pred_min       = -0.02 to 0.0    (default: -0.0128) # Pred min mapping
ml_dca_pred_max       = 0.01 to 0.04    (default: 0.0256)  # Pred max mapping
```

### ML Dynamic Stoploss (5 parametri - sell space)
```python
ml_stoploss_tight           = -0.18 to -0.08  (default: -0.112)
ml_stoploss_loose           = -0.30 to -0.18  (default: -0.219)
ml_stoploss_pred_min        = -0.10 to -0.02  (default: -0.0918)
ml_stoploss_pred_max        = -0.02 to 0.02   (default: -0.0066)
ml_stoploss_activation_loss = -0.18 to -0.05  (default: -0.12)
```

### Crash Detection (1 parametro - sell space)
```python
crash_detection_threshold = -0.10 to -0.03  (default: -0.06)  # Drop % in 15min per exit immediato
```

**CRITICO**: Hyperopt trova la soglia ottimale per crash detection (da -10% a -3%)

### Exit Multi-Oscillator (7 parametri - sell space)
```python
min_profit_for_overbought_exit = 0.005 to 0.10  (default: 0.017)  # ESPANSO: da 0.5% a 10%
rsi_overbought_threshold       = 60 to 85       (default: 63.146)
bb_overbought_threshold        = 0.7 to 0.9     (default: 0.871)
atr_overbought_multiplier      = 0.5 to 2.0     (default: 0.556)
stochrsi_overbought_threshold  = 70 to 100      (default: 94.809)
williams_overbought_threshold  = -30 to -10     (default: -24.965)
min_overbought_count           = 3 to 5         (default: 4)
```

**CRITICO**: Range espanso permette exit da 0.5% (scalping aggressivo) a 10% (conservativo)

### ROI Table (5 parametri - roi space) - NUOVO
```python
minimal_roi = {
    "0": 0.10,    # 10% immediate profit target
    "30": 0.05,   # 5% after 30 minutes
    "60": 0.03,   # 3% after 1 hour
    "120": 0.02,  # 2% after 2 hours
    "240": 0.01   # 1% after 4 hours (force exit)
}
```

**Ottimizzabile con**: `--spaces roi`

### Trailing Stop (3 parametri - trailing space) - NUOVO
```python
trailing_stop = True
trailing_stop_positive = 0.01  # 1% trailing distance
trailing_stop_positive_offset = 0.02  # Activate at +2% profit
trailing_only_offset_is_reached = True
```

**Ottimizzabile con**: `--spaces trailing`

## Logica Entry/DCA/Exit/Stoploss

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

### Exit (Dual Strategy) - REINTEGRATO ML EXIT

#### EXIT 1: ML-Driven (Priorità)
```python
# Condizioni (entrambe devono essere vere)
1. current_profit > min_profit_for_overbought_exit  # default: 1.7%
2. weighted_pred < ml_exit_threshold                # default: -0.001

# Comportamento
→ Exit immediato quando ML prevede downtrend

# Tag esempio
"sell_ml_w-0.0032_+8.5%"
```

**Vantaggi**:
- ✅ Exit proattivo basato su ML predictions
- ✅ Non aspetta overbought, usa confidence ML
- ✅ Hyperoptabile: trova soglia ottimale (-0.01 a +0.01)

#### EXIT 2: Multi-Oscillator Overbought (Fallback)
```python
# Condizioni (tutte devono essere vere)
1. current_profit > min_profit_for_overbought_exit  # default: 1.7%
2. overbought_count >= min_overbought_count         # default: 4/5 oscillatori
3. current_candle["close"] > current_candle["open"] # Candela verde

# Oscillatori controllati (5 totali)
- RSI > 63.146
- BB% > 0.871
- ATR > high - (atr × 0.556)
- StochRSI > 94.809
- Williams %R > -24.965

# Tag esempio
"sell_overbought_(rsi+bb+atr+stochrsi)"
```

**Vantaggi**:
- ✅ Fallback affidabile se ML non trigger
- ✅ Conferma con candela verde (momentum)
- ✅ Multi-oscillator riduce falsi segnali

**Priorità**: ML exit viene controllato **prima** del multi-oscillator

### Stoploss Smart Ibrido (4 Livelli) - NUOVO

#### LIVELLO 1: Crash Detection con Anti-Wick
```python
# Condizioni (entrambe devono essere vere)
1. Drop > crash_detection_threshold in 15min (3 candles)
2. Drop confermato per 2 candele consecutive

# Comportamento
→ Exit immediato con piccolo buffer (+0.01)

# Esempio
Drop -6.5% in 15min, confermato → exit immediato
```

**Vantaggi**:
- ✅ Protegge da flash crash e dump improvvisi
- ✅ Anti-wick: richiede conferma su 2 candele (evita exit su wick temporanei)
- ✅ Hyperoptabile: trova soglia ottimale (-10% a -3%)

#### LIVELLO 2: Breakeven Move
```python
# Condizione
if current_profit > 0.02:  # +2% profit
    return 0.005  # Muovi stoploss a breakeven (+0.5%)
```

**Vantaggi**:
- ✅ Protegge capital dopo primi profit
- ✅ Non interferisce con DCA iniziale
- ✅ Garantisce piccolo profit minimo

#### LIVELLO 3: ML-Driven Dynamic (DCA esaurito)
```python
# Condizioni
1. Loss > ml_stoploss_activation_loss (default: -12%)
2. DCA esaurito (no capital o max orders)

# Comportamento
→ Stoploss dinamico basato su ML predictions
→ Tight (-11.2%) se ML molto negativo
→ Loose (-21.9%) se ML neutrale/positivo
```

**Vantaggi**:
- ✅ Stoploss intelligente basato su ML confidence
- ✅ Si attiva solo quando DCA non può più recuperare
- ✅ Evita exit prematuri durante DCA recovery

#### LIVELLO 4: Trailing Progressive (DCA attivo)
```python
# Stoploss progressivo basato su entry count
entry_count <= 2: -15%
entry_count <= 4: -20%
entry_count <= 6: -25%
entry_count > 6:  -30%

# Trailing se in profit
if current_profit > 0:
    trailing_stoploss = current_profit - 0.03  # Trail 3% dietro
    return max(trailing_stoploss, base_stoploss)
```

**Vantaggi**:
- ✅ Stoploss si allenta con più DCA (più spazio per recovery)
- ✅ Trailing attivo quando in profit (protegge guadagni)
- ✅ Non interferisce con logica DCA

### Priorità Livelli Stoploss

1. **Crash Detection** (massima priorità) → exit immediato
2. **Breakeven Move** → se profit > 2%
3. **ML-Driven** → se DCA esaurito E loss > -12%
4. **Trailing Progressive** → default durante DCA attivo

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
  --hyperopt-loss ProfitDrawdownDurationHyperOptLoss \
  --epochs 6000 \
  --spaces buy sell \
  --timerange 20241215-20260126 \
  -j 30
```

## Loss Function: ProfitDrawdownDurationHyperOptLoss (RECOMMENDED)

```python
# freqtrade/optimize/hyperopt_loss/hyperopt_loss_profit_drawdown_duration.py
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
    penalty_pct = log(1 + hours_over) / 10  # Percentuale
    duration_penalty = penalty_pct * profit

result = -profit + drawdown_penalty + duration_penalty
```

**Obiettivo**: Massimizzare profit totale con penalità drawdown (>20%) e duration (>5h)

**Drawdown Penalty (Esponenziale Continua)**:
- Formula: `(excess^1.5) * 6` dove excess = drawdown - 20%
- Crescita smooth e progressiva (no salti bruschi)
- Esempi: 22% → 1.7%, 25% → 6.7%, 30% → 19%, 35% → 35%, 45% → 75%

**Duration Penalty Percentuale**:
- 5h → 0% penalty
- 10h → 18% penalty (log(6)/10)
- 24h → 30% penalty (log(20)/10)

**Esempi**:
- 10,000 profit, 20% drawdown, 3h → result = -10,000 (best)
- 10,000 profit, 25% drawdown, 3h → result = -9,330 (6.7% drawdown penalty)
- 10,000 profit, 35% drawdown, 3h → result = -6,510 (34.9% drawdown penalty)
- 10,000 profit, 45% drawdown, 3h → result = -2,500 (75% drawdown penalty)
- 10,000 profit, 20% drawdown, 24h → result = -7,000 (30% duration penalty)
- 10,000 profit, 35% drawdown, 24h → result = -3,510 (35% drawdown + 30% duration)

**Vantaggi**:
- ✅ Massimizza profit assoluto (non ratio)
- ✅ Penalizza drawdown >20% (esponenziale continua)
- ✅ Penalizza duration >5h (logaritmica)
- ✅ **Incentiva fortemente trade 300-800** (crescita lineare, cap a 800)
- ✅ Perfetto per scalping con focus su profit e risk control

**Trade Count Reward (Cap a 800)**:
- <300 trade: crescita logaritmica (~7% a 100, ~14% a 300)
- 300-800 trade: crescita lineare aggressiva (+5% per 100 trade)
- >800 trade: capped a 39% reward (previene dominanza)

## Alternative Loss Functions

```python
# freqtrade/optimize/hyperopt_loss/hyperopt_loss_calmar_rylos.py
calmar_ratio = total_return / max_drawdown

# Duration penalty (penalizza trade lunghi)
if avg_duration <= 5h:
    penalty = 0
elif avg_duration > 5h:
    hours_over = (avg_duration - 5h) / 60
    penalty = log(1 + hours_over)  # Logarithmic growth

result = -calmar_ratio / (1 + penalty)
```

**Obiettivo**: Massimizzare Calmar Ratio penalizzando trade con duration > 5h (scalping focus)

**Esempi Duration Penalty**:
- 2h → penalty = 0 (nessuna penalità)
- 5h → penalty = 0 (soglia)
- 10h → penalty = log(6) = 1.79
- 24h → penalty = log(20) = 3.00

## Alternative Loss Functions

### ProfitDrawdownTolerantHyperOptLoss

```python
# freqtrade/optimize/hyperopt_loss/hyperopt_loss_profit_drawdown_tolerant.py
total_profit = results["profit_abs"].sum()

# Penalità drawdown progressiva
if max_drawdown > 40%:
    penalty = base + (excess * profit * 4)  # Aggressiva
elif max_drawdown > 30%:
    penalty = (excess * profit * 2)  # Moderata
else:
    penalty = 0

result = -profit + penalty
```

**Obiettivo**: Massimizzare profit totale con penalità drawdown solo se >30%

**Problema per scalping**: ❌ NON penalizza trade lunghi! Può trovare configurazioni con alto profit ma trade che durano giorni.

### Confronto

| Feature | ProfitDrawdownTolerant | CalmarRyLoS |
|---------|------------------------|-------------|
| **Obiettivo primario** | Massimizza profit totale | Massimizza Calmar Ratio |
| **Drawdown penalty** | Solo se >30% (progressiva) | Sempre (nel Calmar Ratio) |
| **Duration penalty** | ❌ Nessuna | ✅ Penalizza trade >5h |
| **Scalping focus** | ❌ No | ✅ Sì |
| **Best for** | Swing trading, hold lunghi | Scalping, trade frequenti |

**Raccomandazione**: Usa **ProfitDrawdownDurationHyperOptLoss** per scalping su HYPE (massimizza profit con penalty duration e drawdown).

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
