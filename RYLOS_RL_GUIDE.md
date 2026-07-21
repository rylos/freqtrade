# RyLoS RL Strategy - Reinforcement Learning Guide

## Overview

Strategia RL pura dove l'agent impara autonomamente la policy ottimale per entry/exit.

## Files Creati

```
user_data/
├── strategies/
│   └── RyLoSStrategyRL.py          # Strategia RL
├── freqaimodels/
│   └── RyLoSRLModel.py             # Modello RL con custom reward
└── config_rl.json                   # Config FreqAI RL
```

## Come Funziona RL

### 1. Features (Indicatori)

**Sì, RL necessita di features!** L'agent usa gli indicatori per capire lo "stato" del mercato:

**Features fornite** (15 totali):
- RSI(10), ATR%, StochRSI, Williams%R
- Price/Volume % change
- BB%(20), MACD + signal + hist
- EMA(9), EMA(21), CCI(10), ADX(14)
- **RAW OHLCV** (obbligatorio per RL environment)

**Espanse su periodo 10**:
- RSI(10), BB width(10), Volume ratio(10)

### 2. Agent Actions (Base5ActionRLEnv)

- **0**: Neutral (hold)
- **1**: Long enter ✅ (first buy OR DCA)
- **2**: Long exit ✅
- **3**: Short enter ❌ (disabled, can_short=False)
- **4**: Short exit ❌ (disabled, can_short=False)

**DCA Support**: Action 1 has dual meaning:
- If position=Neutral → First buy
- If position=Long → DCA (add to position)

### 3. DCA (Dollar Cost Averaging)

**Dynamic calculation** based on official Freqtrade approach:

- **No fixed parameters** - everything calculated from first order
- **Progressive growth**: Each DCA is 25% larger (1x, 1.25x, 1.5x, 1.75x, etc.)
- **Balance-aware**: Respects 4x leverage limits dynamically
- **Agent-controlled**: RL agent decides WHEN to DCA via reward function

**Example progression** (first order = 100 USDT):
```
Entry 0: 100 USDT (1.00x)
Entry 1: 125 USDT (1.25x)
Entry 2: 150 USDT (1.50x)
Entry 3: 175 USDT (1.75x)
Entry 4: 200 USDT (2.00x)
Total: 750 USDT (7.5x first order)
```

**Key difference from MLv3**: Linear progressive (1 + n × 0.25) instead of exponential (2.665^n).

### 4. Reward Function (Optimized for DCA)

**Obiettivo**: Massimizzare profit tramite DCA recovery strategy

**Rewards (Positive)**:
- ✅ **First entry**: +25 (fixed, encourage trading)
- ✅ **DCA in big loss** (>5%): +50 × abs(pnl) - STRONG incentive
- ✅ **DCA in small loss** (0-5%): +20 × abs(pnl) - Medium incentive
- ✅ **Exit in profit**: +200 × pnl - STRONG reward
- ✅ **Exit breakeven**: +5 (avoid bigger loss)

**Penalties (Negative)**:
- ❌ **Invalid action**: -2 (small, as per docs)
- ❌ **DCA in profit**: -10 (don't add to winner)
- ❌ **Exit in loss**: +50 × pnl (reduced penalty)
- ❌ **Hold in big loss** (>5%): -2 (force DCA or exit!)
- ❌ **Hold in small loss** (0-5%): -0.5 (medium)
- ❌ **Hold in profit**: -0.1 (low, ok to wait)
- ❌ **Neutral inactive**: -1 (as per docs)

**Key Design Principles**:
1. **Scaled rewards**: Proportional to pnl (continuous feedback)
2. **DCA incentive**: Bigger loss = bigger reward for DCA
3. **Hold penalties**: Scale with loss/profit (force action in loss)
4. **Exit rewards**: Increased to 200× (was 100×) to encourage profit taking

### 5. State Info (add_state_info: false)

**DISABLED** per performance. Agent usa solo features (indicatori) per decisioni.

Se abilitato (`add_state_info: true`), agent riceverebbe anche:
- **current_profit**: Profit % corrente
- **position**: Neutral/Long
- **trade_duration**: Durata trade in candles

**Nota**: Disabilitato per evitare overfitting su stato interno.

## Training

### Backtest (Training)

**RECOMMENDED: Train on pc-casa (more powerful CPU) then sync to all servers**

**IMPORTANT**: PPO with MlpPolicy is optimized for CPU, not GPU. GPU is only useful with CNN policies. See [stable_baselines3 issue #1245](https://github.com/DLR-RM/stable-baselines3/issues/1245).

#### 1. Train on pc-casa (More Powerful CPU)

```bash
# SSH to pc-casa
ssh -p 22222 marco@home.ziliani.net
cd /home/marco/dev/freqtrade
source .venv/bin/activate

# Download dati (almeno 15 giorni per train_period_days=10)
freqtrade download-data \
  -c user_data/config_rl_gpu.json \
  --timerange 20241201-20260131

# Backtest con training RL (più cicli e network più grande)
freqtrade backtesting \
  -c user_data/config_rl_gpu.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel \
  --timerange 20241215-20260131
```

**Training process**:
1. Agent cicla attraverso dati storici 50 volte (`train_cycles: 50`)
2. Ogni ciclo: agent fa azioni → riceve reward → aggiorna policy
3. Dopo training: modello salvato in `user_data/models/rylos_rl_v1_gpu/`

**pc-casa advantage**: More cycles (50 vs 25) and larger network (256 vs 128) for better training!

#### 2. Sync Models to All Servers

**Automatic (recommended)**:
```bash
# From pc-work
./sync_rl_models.sh
```

**Manual**:
```bash
# From pc-work: Sync from pc-casa to pc-work
rsync -avz --progress -e "ssh -p 22222" \
  marco@home.ziliani.net:/home/marco/dev/freqtrade/user_data/models/rylos_rl_v1_gpu/ \
  user_data/models/rylos_rl_v1_gpu/

# From pc-work: Sync to debian
rsync -avz --progress \
  user_data/models/rylos_rl_v1_gpu/ \
  marco@192.168.0.34:/opt/freqtrade/user_data/models/rylos_rl_v1_gpu/

# From pc-work: Sync to AWS
rsync -avz --progress \
  user_data/models/rylos_rl_v1_gpu/ \
  admin@amazon.ziliani.net:/opt/freqtrade/user_data/models/rylos_rl_v1_gpu/
```

#### 3. Use Trained Models (No Retraining)

**On pc-work (fast backtest)**:
```bash
# Uses pre-trained models from pc-casa
freqtrade backtesting \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel \
  --timerange 20241215-20260131
```

**On debian (hyperopt)**:
```bash
# Uses pre-trained models, no need to retrain
freqtrade backtesting \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel \
  --timerange 20241215-20260131
```

**On AWS (live trading)**:
```bash
# Uses pre-trained models, retrains every 4h
freqtrade trade \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel
```

### Model Structure

```
user_data/models/rylos_rl_v1_gpu/
├── run_params.json                    # Config FreqAI
├── pair_dictionary.json               # Training queue
├── backtesting_predictions/           # Predictions cache
│   └── cb_hype_<timestamp>_prediction.feather
└── sub-train-HYPE_<timestamp>/        # Model per period
    ├── cb_hype_<timestamp>_model.zip              # RL agent (PPO weights)
    ├── cb_hype_<timestamp>_metadata.json          # Metadata
    ├── cb_hype_<timestamp>_trained_df.pkl         # Training data
    ├── cb_hype_<timestamp>_trained_dates_df.pkl   # Training dates
    └── tensorboard/                               # TensorBoard logs
```

**IMPORTANT**: 
- Models are **portable** - train once on GPU, use everywhere
- Predictions cache speeds up subsequent backtests
- TensorBoard logs help analyze training performance

### Tensorboard (Monitor Training)

```bash
# In shell separata
tensorboard --logdir user_data/models/rylos_rl_v1

# Apri browser: http://127.0.0.1:6006
```

**Metriche da monitorare**:
- `episode_reward`: Reward totale per episodio (deve crescere)
- `entry_dip`: Quante volte entra su dip
- `exit_profit`: Quante volte esce in profit
- `hold_toolong`: Quante volte tiene troppo a lungo

### Live/Dry Run

```bash
freqtrade trade \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel
```

**Comportamento**:
- Usa modello trainato
- Ritraina ogni 4 ore (`live_retrain_hours: 4`)
- Agent continua a imparare da nuovi dati

## Config RL Parameters

```json
"rl_config": {
  "train_cycles": 25,              // Cicli training (più = meglio, ma più lento)
  "add_state_info": false,         // Include profit/position/duration (NOT available in backtest)
  "max_trade_duration_candles": 24, // Max 2h @ 5m (per penalty)
  "max_training_drawdown_pct": 0.02, // Stop training se DD > 2%
  "cpu_count": 2,                  // CPU per training parallelo
  "model_type": "PPO",             // Algoritmo RL (PPO = stable)
  "policy_type": "MlpPolicy",      // Neural network policy
  "model_reward_parameters": {
    "rr": 1.0,                     // Risk/Reward ratio
    "profit_aim": 0.02             // Target profit 2%
  },
  "net_arch": [128, 128],          // Neural net: 2 layers × 128 neurons
  "progress_bar": true             // Mostra progress durante training
}
```

### GPU vs CPU Configuration

**CPU Config** (pc-work, debian, AWS):
```json
{
  "model_training_parameters": {
    "device": "cpu"
  },
  "rl_config": {
    "train_cycles": 25,
    "net_arch": [128, 128],
    "cpu_count": 2
  }
}
```

**GPU Config** (pc-casa RTX 4070):
```json
{
  "model_training_parameters": {
    "device": "cuda"
  },
  "rl_config": {
    "train_cycles": 50,
    "net_arch": [256, 256, 128],
    "cpu_count": 8
  }
}
```

### GPU vs CPU Performance

| Operation | GPU (pc-casa) | CPU (debian/AWS) |
|-----------|---------------|------------------|
| **Training** | 🚀 Fast (3-5x) | 🐌 Slow |
| **Inference** (prediction) | ⚡ Fast | ✅ Fast (almost same) |
| **Live trading** | ✅ OK | ✅ OK (recommended) |

**Key Points**:
- ✅ **Models trained on GPU work perfectly on CPU** (PyTorch auto-detects device)
- ✅ **Inference is fast on CPU** (predicts 1 candle at a time, small network)
- ⚠️ **Retraining on CPU is slow** (but happens only every 4-8h in live)
- 🚀 **Train on GPU, deploy on CPU** (recommended workflow)

**Recommended Workflow**:
1. **Train on pc-casa (GPU)**: Fast initial training (50 cycles, large network)
2. **Sync models to all servers**: Use `sync_rl_models.sh` script
3. **Deploy on AWS (CPU)**: Fast inference, slow retraining (acceptable)
4. **Increase `live_retrain_hours: 8`**: Reduce retraining frequency on CPU

## Differenze vs MLv3 (Regressor)

| Feature | MLv3 (Regressor) | RL |
|---------|------------------|-----|
| **Predizioni** | 5 target numerici (5m, 15m, 30m, dd) | Azioni discrete (0-4) |
| **Decisioni** | Strategia (threshold fissi) | Agent (policy appresa) |
| **Adattività** | Statica | Dinamica (impara da reward) |
| **Stoploss** | Custom stoploss fisso | Agent impara stoploss ottimale |
| **Take Profit** | Threshold fisso | Agent impara take profit ottimale |
| **DCA** | Logica manuale | Agent decide quando entrare |
| **Training** | Supervised (target noti) | Reinforcement (reward) |
| **Complessità** | Media | Alta |
| **Debugging** | Facile (vedi predizioni) | Difficile (black box) |

## Vantaggi RL

1. ✅ **Adattività**: Impara policy ottimale per mercato corrente
2. ✅ **Stoploss dinamico**: Non fisso, si adatta a volatilità
3. ✅ **Take profit dinamico**: Massimizza profit senza threshold fissi
4. ✅ **Market reactivity**: Reagisce a cambiamenti mercato
5. ✅ **No overfitting su threshold**: Non dipende da hyperopt

## Svantaggi RL

1. ❌ **Complessità**: Più difficile da debuggare
2. ❌ **Training lungo**: 25 cicli × dati storici
3. ❌ **Rischio "cheats"**: Agent può trovare scorciatoie
4. ❌ **Black box**: Difficile capire perché agent decide
5. ❌ **Richiede dati**: Minimo 10-15 giorni per training

## Tips per Migliorare Reward

### 1. Reward Scaling

**Problema**: Reward troppo grandi/piccoli → agent non impara

**Soluzione**: Scala reward tra -10 e +100
```python
# BAD
return 10000 * pnl  # Troppo grande

# GOOD
return 100 * pnl  # Scaled
```

### 2. Continuous Rewards

**Problema**: Penalty singola grande → agent non impara

**Soluzione**: Penalty piccola continua
```python
# BAD
if trade_duration > 100:
    return -1000  # Singola penalty grande

# GOOD
if trade_duration > max_duration:
    return -2 * (trade_duration / max_duration)  # Penalty crescente
```

### 3. Reward Shaping

**Problema**: Agent trova "cheats" (es. non entra mai)

**Soluzione**: Bilancia reward entry/exit
```python
# Reward entry (incentiva trading)
if action == Actions.Long_enter.value:
    return 25

# Penalty inattività (penalizza non trading)
if action == Actions.Neutral.value:
    return -0.2
```

## Prossimi Passi

1. **Test backtest**: Verifica che training funzioni
2. **Monitor Tensorboard**: Controlla che reward cresca
3. **Tune reward function**: Modifica reward per migliorare performance
4. **Tune RL config**: Aumenta train_cycles, modifica net_arch
5. **Dry run**: Testa su mercato reale (dry)
6. **Live**: Deploy su AWS

## GPU vs CPU: Portability

**Models are portable**: Train on GPU, use on CPU without any changes!

```bash
# Train on pc-casa (GPU)
freqtrade backtesting -c config_rl_gpu.json ...

# Sync to AWS
./sync_rl_models.sh

# Use on AWS (CPU) - works perfectly!
freqtrade trade -c config_rl.json ...
```

**PyTorch automatically**:
- Detects available device (GPU or CPU)
- Loads model weights on correct device
- No code changes needed

**Performance**:
- Training: GPU 3-5x faster
- Inference: CPU almost same speed (1 prediction at a time)
- Live trading: CPU is sufficient

## Troubleshooting

### Agent non entra mai

**Causa**: Penalty inattività troppo bassa

**Fix**: Aumenta penalty neutral
```python
if action == Actions.Neutral.value:
    return -1.0  # Era -0.2
```

### Agent entra/esce continuamente

**Causa**: Reward entry troppo alto

**Fix**: Riduci reward entry o aggiungi cooldown
```python
if action == Actions.Long_enter.value:
    return 10  # Era 25
```

### Reward non cresce

**Causa**: Reward mal scalato o train_cycles troppo basso

**Fix**: Scala reward o aumenta train_cycles
```json
"train_cycles": 50  // Era 25
```

### Training troppo lento

**Causa**: cpu_count troppo basso o train_cycles troppo alto

**Fix**: Aumenta cpu_count o riduci train_cycles
```json
"cpu_count": 8,      // Era 2
"train_cycles": 15   // Era 25
```
