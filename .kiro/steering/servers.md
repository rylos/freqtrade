# Server Configurazioni

## Server Hyperopt - debian-lifting
- **SSH**: `ssh marco@192.168.0.34`
- **Path**: `/opt/freqtrade`
- **Uso**: Hyperopt e backtesting con FreqAI
- **Specs**: Potente (multi-core, RAM abbondante)

## Server Live Trading - AWS
- **SSH**: `ssh admin@amazon.ziliani.net`
- **Path Hyperliquid**: `/opt/freqtrade-hl`
- **Path Bybit**: `/opt/freqtrade`
- **Uso**: Trading live con FreqAI
- **Specs**: 2 core, 4GB RAM (config ottimizzato per queste risorse)

## Comandi Copia File

### Copia su debian-lifting (hyperopt)
```bash
# Strategia
scp user_data/strategies/RyLoSStrategyMLv3.py marco@192.168.0.34:/opt/freqtrade/user_data/strategies/

# Modello PyTorch
scp user_data/freqaimodels/RyLoSPyTorchModel.py marco@192.168.0.34:/opt/freqtrade/user_data/freqaimodels/

# Config ML
scp user_data/config_ml.json marco@192.168.0.34:/opt/freqtrade/user_data/

# Loss function
scp freqtrade/optimize/hyperopt_loss/hyperopt_loss_profit_drawdown_tolerant.py marco@192.168.0.34:/opt/freqtrade/freqtrade/optimize/hyperopt_loss/
```

### Copia su AWS (live trading)
```bash
# Bybit (RyLoS Strategy)
scp user_data/strategies/RyLoSStrategyMLv3.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/strategies/
scp user_data/freqaimodels/RyLoSPyTorchModel.py admin@amazon.ziliani.net:/opt/freqtrade/user_data/freqaimodels/
scp user_data/config_ml.json admin@amazon.ziliani.net:/opt/freqtrade/user_data/

# Hyperliquid (RyLoS Strategy)
scp user_data/strategies/RyLoSStrategyMLv3.py admin@amazon.ziliani.net:/opt/freqtrade-hl/user_data/strategies/
scp user_data/freqaimodels/RyLoSPyTorchModel.py admin@amazon.ziliani.net:/opt/freqtrade-hl/user_data/freqaimodels/
scp user_data/config_ml_hl.json admin@amazon.ziliani.net:/opt/freqtrade-hl/user_data/
```

## Hyperopt Command (debian-lifting)

```bash
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate

# Usa -j 30 per sfruttare tutti i core
freqtrade hyperopt -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss ProfitDrawdownTolerantHyperOptLoss \
  --epochs 6000 --spaces buy sell \
  --timerange 20241215-20260122 \
  -j 30
```

## Note

- **debian-lifting**: Server potente per hyperopt, usa `-j 30` per parallelizzare
- **AWS live**: Config ML ottimizzato per 2 core/4GB RAM (batch_size 512, hidden_dim 64)
