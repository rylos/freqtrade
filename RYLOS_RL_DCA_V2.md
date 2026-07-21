# RyLoS RL DCA Strategy v2 - Custom Environment

## Overview

Custom Reinforcement Learning environment che supporta **DCA completo** con:
- ✅ Multiple entries (DCA illimitato fino ai limiti)
- ✅ Progressive stake sizing (ogni DCA è 25% più grande)
- ✅ Global e per-pair limits
- ✅ Stoploss management (-20% position = -80% capital)
- ✅ Reward function ottimizzata per DCA recovery

## Architettura

### Custom Environment: `RyLoSRLModelDCA`

Eredita da `BaseEnvironment` (non da Base5ActionRLEnv) per controllo completo.

**Actions (3 invece di 5):**
- `0`: Neutral (hold)
- `1`: Long_enter (first entry OR DCA)
- `2`: Long_exit (exit completo)

**Key Features:**
- `_is_valid()` custom - permette Long_enter anche in posizione
- DCA tracking: entry_count, total_stake, entry_prices, entry_stakes
- Progressive stake: `stake_n = first_stake × (1 + n × 0.25)`
- Limits check: global e per-pair prima di ogni entry
- Stoploss: -20% position (-80% capital con 4x leverage)

## DCA Logic

### Progressive Stake Sizing

```python
# Formula
stake_n = first_stake × (1 + n × dca_size_multiplier)

# Esempio con dca_size_multiplier=0.25
Entry 0: 1.00x first_stake
Entry 1: 1.25x first_stake
Entry 2: 1.50x first_stake
Entry 3: 1.75x first_stake
Entry 4: 2.00x first_stake
```

### Limits Check

**Per-pair limit:**
```python
per_pair_limit = (balance × leverage) / max_open_trades
```

**Global limit:**
```python
global_limit = balance × leverage
```

**Check prima di ogni DCA:**
```python
if total_stake × leverage + next_stake × leverage > per_pair_limit:
    return False  # DCA blocked
```

### Average Entry Price

```python
avg_entry = sum(price × stake) / total_stake
```

### Position PnL

```python
pnl% = (current_price - avg_entry) / avg_entry × leverage
```

## Reward Function

### Principles

1. **Continuously differentiable** - reward scala con PnL
2. **Well scaled** - penalità piccole per eventi comuni
3. **DCA-optimized** - forte incentivo per DCA in loss

### Formula

**First Entry:**
```python
+25 (fisso)
```

**DCA in big loss (>5%):**
```python
+50 × |pnl|  # Esempio: -10% loss → +5 reward
```

**DCA in small loss (0-5%):**
```python
+20 × |pnl|  # Esempio: -2% loss → +0.4 reward
```

**DCA in profit:**
```python
-10 (penalità fissa)
```

**Exit in profit:**
```python
+200 × pnl  # Esempio: +5% profit → +10 reward
```

**Exit in loss:**
```python
+50 × pnl  # Esempio: -5% loss → -2.5 reward (meglio che hold)
```

**Hold in big loss (>5%):**
```python
-2 (forza azione)
```

**Hold in small loss (0-5%):**
```python
-0.5
```

**Hold in profit:**
```python
-0.1 (ok aspettare)
```

**Neutral inactive:**
```python
-1
```

**Invalid action:**
```python
-2
```

## Stoploss Management

**Fixed stoploss:**
```python
stoploss_pct = -0.20  # -20% position
```

**Con 4x leverage:**
```python
-20% position = -80% capital
```

**Comportamento:**
- Checked ogni step
- Se `pnl <= -0.20`: force exit + episode terminato
- Logged in Tensorboard: `stoploss_hit`

## Training Configuration

### Config RL

```json
{
  "freqai": {
    "rl_config": {
      "train_cycles": 100,
      "max_trade_duration_candles": 24,
      "max_training_drawdown_pct": 0.8,
      "cpu_count": 30,
      "model_type": "PPO",
      "policy_type": "MlpPolicy",
      "net_arch": [512, 512, 256, 128],
      "model_reward_parameters": {
        "rr": 1.0,
        "profit_aim": 0.02
      }
    }
  }
}
```

### Strategy Config

```python
timeframe = "5m"
can_short = False
leverage = 4.0
stoploss = -0.20
position_adjustment_enable = True
dca_size_multiplier = 0.25
```

## Files

```
user_data/
├── strategies/
│   └── RyLoSStrategyRL.py           # Strategy (unchanged)
├── freqaimodels/
│   ├── RyLoSRLModel.py              # Old model (Base5ActionRLEnv)
│   └── RyLoSRLModelDCA.py           # NEW - Custom DCA environment
└── config_rl.json                    # Config (unchanged)
```

## Training Command

```bash
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate

# Copy new model
scp user_data/freqaimodels/RyLoSRLModelDCA.py marco@192.168.0.34:/opt/freqtrade/user_data/freqaimodels/

# Training with new model
freqtrade backtesting \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModelDCA \
  --timerange 20260101-20260206
```

## Tensorboard Metrics

### Actions (tab "actions")
- `Neutral` - Hold count
- `Long_enter` - Entry + DCA count
- `Long_exit` - Exit count

### Rewards (tab "reward")
- `reward/entry_first` - First entries
- `reward/dca_big_loss` - DCA in loss >5% (DEVE AUMENTARE!)
- `reward/dca_small_loss` - DCA in loss 0-5%
- `reward/dca_in_profit` - DCA in profit (deve diminuire)
- `reward/exit_profit` - Exit in profit (deve aumentare)
- `reward/exit_loss` - Exit in loss
- `reward/exit_breakeven` - Exit breakeven
- `reward/hold_big_loss` - Hold in loss >5% (deve diminuire)
- `reward/hold_small_loss` - Hold in loss 0-5%
- `reward/hold_profit` - Hold in profit
- `reward/neutral_inactive` - Inattivo
- `reward/invalid_action` - Azioni invalide

### Metrics (tab "metrics")
- `metrics/current_pnl` - PnL corrente
- `stoploss_hit` - Stoploss triggered

### Rollout (tab "rollout")
- `rollout/ep_rew_mean` - Reward medio episodio (DEVE AUMENTARE!)
- `rollout/ep_len_mean` - Lunghezza episodio

## Expected Behavior

### Training Progress

**Primi 10-20 eval:**
- Reward negativi (-1000 a -500)
- Agent random, non fa DCA
- `dca_big_loss` = 0 o molto basso

**Eval 20-50:**
- Reward migliorano (0 a +500)
- Agent inizia a fare DCA
- `dca_big_loss` aumenta
- `exit_profit` aumenta

**Eval 50-100:**
- Reward positivi stabili (+500 a +1000)
- Agent fa DCA consistentemente
- `dca_big_loss` alto e stabile
- `exit_profit` alto e stabile
- `hold_big_loss` basso (non sta fermo in loss)

### Convergenza OK

✅ `rollout/ep_rew_mean` diventa positivo (+500+)
✅ `reward/dca_big_loss` aumenta (agent impara DCA)
✅ `reward/exit_profit` aumenta (agent esce in profit)
✅ `reward/hold_big_loss` diminuisce (agent non hold in loss)
✅ `actions/Long_enter` > `actions/Long_exit` (più entries che exits = DCA)

## Differences vs Base5ActionRLEnv

| Feature | Base5ActionRLEnv | RyLoSRLModelDCA |
|---------|------------------|-----------------|
| **Actions** | 5 (Long enter/exit, Short enter/exit, Neutral) | 3 (Long enter, Long exit, Neutral) |
| **DCA Support** | ❌ NO (blocks entry if in position) | ✅ YES (allows multiple entries) |
| **Stake Sizing** | Fixed | Progressive (25% increase per DCA) |
| **Position Tracking** | Simple (Long/Short/Neutral) | Advanced (entry_count, total_stake, avg_entry) |
| **Limits Check** | None | Global + per-pair |
| **Stoploss** | None | -20% position (-80% capital) |
| **Reward** | Generic | DCA-optimized |

## Troubleshooting

### Agent non fa DCA

**Sintomi:**
- `reward/dca_big_loss` = 0 o molto basso
- `actions/Long_enter` ≈ `actions/Long_exit`

**Cause:**
1. Reward DCA troppo basso → aumenta moltiplicatore
2. Penalità hold troppo bassa → aumenta penalità
3. Agent preferisce exit immediato → riduci reward exit

### Reward non migliora

**Sintomi:**
- `rollout/ep_rew_mean` rimane negativo dopo 50+ eval
- Oscillazioni grandi tra eval

**Cause:**
1. Learning rate troppo alto → riduci a 0.00005
2. Network troppo grande → riduci a [256, 256, 128]
3. Reward function non bilanciata → rivedi pesi

### Stoploss hit troppo spesso

**Sintomi:**
- `stoploss_hit` molto alto
- Episode terminano prematuramente

**Cause:**
1. Stoploss troppo stretto → aumenta a -0.30
2. Agent non fa DCA abbastanza → aumenta reward DCA
3. Leverage troppo alto → riduci a 3x

## Next Steps

1. ✅ Copy new model to debian
2. ✅ Start training with `--freqaimodel RyLoSRLModelDCA`
3. ✅ Monitor Tensorboard for DCA metrics
4. ✅ Wait for convergence (~2-3 hours)
5. ✅ Backtest with trained models
6. ✅ Deploy to AWS for live trading

## Notes

- Custom environment è la via ufficiale raccomandata da Freqtrade
- Eredita da `BaseEnvironment` per controllo completo
- Supporta DCA illimitato fino ai limiti configurati
- Reward function ottimizzata per DCA recovery
- Stoploss management integrato
- Tensorboard logging completo per debugging
