# RyLoS RL with DCA - Implementation Details

## Overview

RL Agent now controls **full trading lifecycle**:
- ✅ **First buy**: When to enter (action=1, position=Neutral)
- ✅ **DCA**: When to add position (action=1, position=Long)
- ✅ **Exit**: When to close (action=2)
- ✅ **Stoploss**: Learns optimal stop loss timing
- ✅ **Take profit**: Learns optimal take profit timing

## Agent Actions

| Action | Position | Meaning |
|--------|----------|---------|
| **0** | Any | Neutral (hold) |
| **1** | Neutral | **First buy** (enter new position) |
| **1** | Long | **DCA** (add to existing position) |
| **2** | Long | **Exit** (close position) |
| **3** | Any | Short enter (disabled, can_short=False) |
| **4** | Any | Short exit (disabled, can_short=False) |

**Key Innovation**: Same action (1) has different meaning based on position state!

## DCA Implementation

### Dynamic Calculation (Official Freqtrade Approach)

**No fixed parameters** - everything calculated dynamically based on:
- First order stake amount
- Progressive multiplier (25% increase per order)
- Available balance
- Leverage limits (4x)

```python
leverage = 4.0
dca_size_multiplier = 0.25  # Each DCA is 25% larger

# Limits (calculated dynamically)
global_limit = balance × 4
per_pair_limit = global_limit / max_open_trades
max_orders = calculated based on first_order_stake
```

### DCA Logic Flow

```
1. Agent signals action=1 (entry)
2. Check current position:
   - If Neutral → First buy (populate_entry_trend)
   - If Long → DCA (adjust_trade_position)
3. DCA checks:
   ✓ Agent action == 1
   ✓ No open orders
   ✓ Not exceeded max_orders (dynamic)
   ✓ Not exceeded global limit (95%)
   ✓ Not exceeded per_pair_limit
   ✓ Sufficient available balance
4. Calculate progressive stake:
   stake = first_order_stake × (1 + entry_count × 0.25)
5. Execute DCA with tag: "dca_rl_{count}_{profit}%"
```

### Stake Progression Example

**Assuming first order = 100 USDT**:

```
Entry 0 (first): 100 × 1.00 = 100 USDT
Entry 1 (DCA 1): 100 × 1.25 = 125 USDT
Entry 2 (DCA 2): 100 × 1.50 = 150 USDT
Entry 3 (DCA 3): 100 × 1.75 = 175 USDT
Entry 4 (DCA 4): 100 × 2.00 = 200 USDT
...
Total: 100 + 125 + 150 + 175 + 200 = 750 USDT (7.5x first order)
Max entries: Dynamic (depends on balance and limits)
```

**Key difference from MLv3**: No exponential growth (2.665^n), but linear progressive growth (1 + n × 0.25).

## Reward Function (Updated)

### Principles

Based on official Freqtrade docs and DCA strategy requirements:

1. **Continuously differentiable**: Rewards scale with pnl (not binary)
2. **Well scaled**: Small penalties for common events, not large penalties for rare events
3. **DCA-focused**: Strong incentive for DCA in loss (recovery strategy)
4. **Dense rewards**: Feedback at every step (not just at trade end)

### Reward Structure

```python
# FIRST ENTRY
+25  # Fixed reward (encourage trading)

# DCA
+50 × abs(pnl)  # Big loss (>5%) - STRONG incentive
+20 × abs(pnl)  # Small loss (0-5%) - Medium incentive
-10             # In profit - Penalty (don't add to winner)

# EXIT
+200 × pnl      # Profit - STRONG reward (increased from 100)
+5              # Breakeven - Small reward
+50 × pnl       # Loss - Reduced penalty (better than holding)

# HOLD IN POSITION
-2.0            # Big loss (>5%) - HIGH penalty (force action!)
-0.5            # Small loss (0-5%) - Medium penalty
-0.1            # In profit - Low penalty (ok to wait)

# NEUTRAL INACTIVE
-1.0            # As per official docs

# INVALID ACTION
-2.0            # Small penalty (as per official docs)
```

### Example Scenarios

**Successful DCA Recovery**:
```
1. Entry at $100: +25
2. Price drops to $90 (-10%): Hold penalty -2 × 5 = -10
3. DCA at $90: +50 × 0.10 = +5
4. Price rises to $95 (-5%): Hold penalty -0.5 × 10 = -5
5. Exit at $102 (+2%): +200 × 0.02 = +4

Total: +25 -10 +5 -5 +4 = +19 ✅ (Positive!)
```

**Failed Trade (No DCA)**:
```
1. Entry at $100: +25
2. Price drops to $90 (-10%): Hold penalty -2 × 20 = -40
3. Exit at $90 (-10%): +50 × -0.10 = -5

Total: +25 -40 -5 = -20 ❌ (Negative)
```

**Lesson**: Agent learns DCA in loss is better than holding in loss!

## Tensorboard Metrics

**New DCA metrics**:
- `dca_recovery`: Count of DCA in big loss (> 3%)
- `dca_small_loss`: Count of DCA in small loss
- `dca_in_profit`: Count of DCA in profit (should be low!)

**Existing metrics**:
- `entry_dip`: First entry on dip
- `entry_normal`: First entry normal
- `entry_overbought`: First entry overbought
- `exit_profit`: Profitable exits
- `exit_profit_target`: Exits hitting target
- `exit_loss_early`: Early stop loss
- `exit_loss_late`: Late stop loss
- `hold_toolong`: Holding too long
- `neutral_inactive`: Inactivity

## Training Expectations

### What Agent Should Learn

**Good behavior**:
1. ✅ Enter on dips (RSI < 40)
2. ✅ DCA when in loss (trying to recover)
3. ✅ Exit in profit (> 2%)
4. ✅ Cut losses early (< 2h)
5. ✅ Don't hold too long (< 2h)

**Bad behavior to avoid**:
1. ❌ Enter overbought (RSI > 60)
2. ❌ DCA in profit (adding to winner)
3. ❌ Hold losses too long (> 2h)
4. ❌ Exit too early (< 1% profit)
5. ❌ Stay inactive (not trading)

### Tensorboard Monitoring

**Episode reward should increase** over training cycles.

**Check metrics**:
- `dca_recovery` should be **high** (agent learns to DCA in loss)
- `dca_in_profit` should be **low** (agent avoids DCA in profit)
- `exit_profit` should be **high** (agent exits in profit)
- `hold_toolong` should be **low** (agent exits before 2h)

## Differences vs MLv3

| Feature | MLv3 (Regressor) | RL with DCA |
|---------|------------------|-------------|
| **First buy** | Threshold (weighted_pred > -0.61%) | Agent learns (RSI-based reward) |
| **DCA trigger** | Threshold (weighted_pred > -1.84%) | Agent learns (loss-based reward) |
| **DCA stake** | Exponential (2.665^n) | Progressive linear (1 + n × 0.25) |
| **DCA distance** | Dynamic (ATR-based) | Agent decides timing |
| **DCA cooldown** | 1 candle (5 min) | Agent decides timing |
| **Exit** | Threshold (5m < +0.34%) | Agent learns (profit-based reward) |
| **Stoploss** | 5 levels (ML drawdown, crash, etc.) | Agent learns (loss-based reward) |
| **Take profit** | Fixed (2.29%) | Agent learns (profit-based reward) |
| **Adaptivity** | Static thresholds | Dynamic policy |

## Advantages RL with DCA

1. ✅ **Adaptive DCA**: Agent learns when to DCA (not fixed distance)
2. ✅ **Context-aware**: Agent sees full market state (15 features)
3. ✅ **No cooldown**: Agent decides timing (not fixed 5 min)
4. ✅ **Dynamic stoploss**: Agent learns optimal stop (not fixed -20%)
5. ✅ **Dynamic take profit**: Agent learns optimal exit (not fixed 2.29%)
6. ✅ **Market reactivity**: Agent adapts to changing conditions
7. ✅ **Progressive DCA**: Linear growth (1.25x, 1.5x, 1.75x) vs exponential (2.665^n)
8. ✅ **Balance-aware**: Stake calculated from first order, not fixed %

## Disadvantages RL with DCA

1. ❌ **Complexity**: Harder to debug than fixed thresholds
2. ❌ **Training time**: Longer training (50 cycles × data)
3. ❌ **Black box**: Hard to understand why agent decides
4. ❌ **Overfitting risk**: Agent may find "cheats"
5. ❌ **Requires tuning**: Reward function needs careful design

## Testing Workflow

### 1. Train on pc-casa (GPU)

```bash
ssh -p 22222 marco@home.ziliani.net
cd /home/marco/dev/freqtrade
source .venv/bin/activate

# Download data
freqtrade download-data -c user_data/config_rl_gpu.json --timerange 20241201-20260131

# Train with DCA
freqtrade backtesting \
  -c user_data/config_rl_gpu.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel \
  --timerange 20241215-20260131
```

### 2. Monitor Tensorboard

```bash
# In separate shell
tensorboard --logdir user_data/models/rylos_rl_v1_gpu

# Open: http://127.0.0.1:6006
```

**Check**:
- Episode reward increasing
- `dca_recovery` high (good DCA in loss)
- `dca_in_profit` low (avoid DCA in profit)
- `exit_profit` high (profitable exits)

### 3. Sync Models

```bash
# From pc-work
./sync_rl_models.sh
```

### 4. Deploy

```bash
# AWS (live trading)
freqtrade trade \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModel
```

## Troubleshooting

### Agent Not Doing DCA

**Cause**: DCA reward too low or penalty too high

**Fix**: Increase DCA reward in loss
```python
# In RyLoSRLModel.calculate_reward()
if pnl < -0.03:
    reward = 50 * abs(pnl)  # Was 30 (increase)
```

### Agent Doing Too Much DCA

**Cause**: DCA reward too high

**Fix**: Reduce DCA reward or add penalty
```python
if pnl < -0.03:
    reward = 20 * abs(pnl)  # Was 30 (reduce)
```

### Agent DCA in Profit

**Cause**: DCA in profit penalty too low

**Fix**: Increase penalty
```python
if pnl > 0:  # DCA in profit
    return -20  # Was -10 (increase penalty)
```

### Agent Not Exiting

**Cause**: Exit reward too low or hold penalty too low

**Fix**: Increase exit reward or hold penalty
```python
# Exit reward
reward = 150 * pnl  # Was 100 (increase)

# Hold penalty
return -1.0  # Was -0.5 (increase)
```

## Next Steps

1. ✅ Test training on pc-casa (GPU)
2. ✅ Monitor Tensorboard metrics
3. ✅ Tune reward function if needed
4. ✅ Sync models to all servers
5. ✅ Dry run on AWS
6. ✅ Live trading

## Files Modified

- `user_data/strategies/RyLoSStrategyRL.py` - Added DCA logic
- `user_data/freqaimodels/RyLoSRLModel.py` - Added DCA rewards
- `user_data/config_rl.json` - Enabled position_adjustment
- `user_data/config_rl_gpu.json` - Enabled position_adjustment
