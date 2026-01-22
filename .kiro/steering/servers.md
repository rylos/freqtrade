# Server Configurazioni

## Server Hyperopt (Freqtrade)
- **SSH**: `ssh marco@192.168.0.34`
- **Path**: `/opt/freqtrade`
- **Uso**: Hyperopt e backtesting con FreqAI
- **Specs**: 2 core, 4GB RAM

## Comandi Copia File

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

## Hyperopt Command

```bash
ssh marco@192.168.0.34
cd /opt/freqtrade
source .venv/bin/activate

freqtrade hyperopt -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss ProfitDrawdownTolerantHyperOptLoss \
  --epochs 50 --spaces buy sell \
  --timerange 20241215-20260122 \
  --jobs 1
```
