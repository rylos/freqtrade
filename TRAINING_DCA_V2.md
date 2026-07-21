# Training RyLoS RL DCA v2

## Setup Completato ✅

Tutti i file sono stati copiati su debian:
- ✅ `RyLoSStrategyRL.py` (strategy)
- ✅ `RyLoSRLModelDCA.py` (custom DCA environment)
- ✅ `config_rl.json` (config ottimizzato)

## Training Command

```bash
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate

# Clean old models
rm -rf user_data/models/rylos_rl_v1

# Start training with DCA environment
freqtrade backtesting \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModelDCA \
  --timerange 20260101-20260206
```

## Monitoring

### Tensorboard

```bash
# In altra shell SSH
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate
tensorboard --logdir user_data/models/rylos_rl_v1/tensorboard --host 0.0.0.0
```

Apri: http://192.168.0.34:6006

### Metriche Chiave

**DEVE VEDERE (se DCA funziona):**
- ✅ `reward/dca_big_loss` - DEVE AUMENTARE (agent fa DCA in loss)
- ✅ `reward/dca_small_loss` - DEVE AUMENTARE
- ✅ `reward/exit_profit` - DEVE AUMENTARE (agent esce in profit)
- ✅ `reward/hold_big_loss` - DEVE DIMINUIRE (agent non hold in loss)
- ✅ `rollout/ep_rew_mean` - DEVE DIVENTARE POSITIVO (+500+)

**Actions:**
- `actions/Long_enter` > `actions/Long_exit` (più entries = DCA)

## Tempo Stimato

```
Timerange: 20260101-20260206 = 36 giorni
train_period_days: 10
backtest_period_days: 2

Numero modelli: 36 / 2 = 18 training
Tempo per training: ~15 minuti
Totale: 18 × 15 min = ~4.5 ore
```

## Progresso

Guarda il terminale SSH:
```
Eval num_timesteps=2010, episode_reward=...
Eval num_timesteps=4020, episode_reward=...
...
```

Ogni training fa ~71,600 timesteps (100 cicli × 716 candles).

## Cosa Aspettarsi

### Primi 10-20 eval
- Reward negativi (-1000 a -500)
- `dca_big_loss` = 0 (agent non fa DCA ancora)

### Eval 20-50
- Reward migliorano (0 a +500)
- `dca_big_loss` inizia ad aumentare
- Agent impara a fare DCA

### Eval 50-100
- Reward positivi (+500 a +1000)
- `dca_big_loss` alto e stabile
- `exit_profit` alto
- Agent ha imparato DCA recovery

## Se DCA Non Funziona

**Sintomi:**
- `reward/dca_big_loss` rimane 0 o molto basso dopo 30+ eval
- `actions/Long_enter` ≈ `actions/Long_exit` (no DCA)

**Possibili fix:**
1. Aumenta reward DCA: `50 × |pnl|` → `100 × |pnl|`
2. Aumenta penalità hold: `-2` → `-5`
3. Riduci reward exit: `200 × pnl` → `100 × pnl`

## Dopo Training

### Sync Models

```bash
# Da pc-work
rsync -avz --progress marco@192.168.0.34:/opt/freqtrade/user_data/models/rylos_rl_v1/ user_data/models/rylos_rl_v1/
```

### Backtest Locale

```bash
freqtrade backtesting \
  -c user_data/config_rl.json \
  --strategy RyLoSStrategyRL \
  --freqaimodel RyLoSRLModelDCA \
  --timerange 20260201-20260206
```

Vedrai:
- Total profit
- Win rate
- Max drawdown
- Numero trades
- Numero DCA per trade

## Deploy to AWS

```bash
# Copy files
scp user_data/strategies/RyLoSStrategyRL.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/strategies/
scp user_data/freqaimodels/RyLoSRLModelDCA.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/freqaimodels/
scp user_data/config_rl.json admin@amazon.ziliani.net:/opt/freqtrade/user_data/

# Copy trained models
rsync -avz --progress user_data/models/rylos_rl_v1/ admin@amazon.ziliani.net:/opt/freqtrade/user_data/models/rylos_rl_v1/

# Start bot
ssh admin@amazon.ziliani.net
cd /opt/freqtrade
source .venv/bin/activate
freqtrade trade -c user_data/config_rl.json --strategy RyLoSStrategyRL --freqaimodel RyLoSRLModelDCA
```

## Notes

- Custom environment supporta DCA completo
- Progressive stake sizing (25% increase per DCA)
- Global e per-pair limits rispettati
- Stoploss -20% position (-80% capital)
- Reward function ottimizzata per DCA recovery
- Tensorboard logging completo per debugging
