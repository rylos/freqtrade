# FreqAI Setup per RyLoS Strategy

## Configurazione Corretta v3

### 1. Strategia - Metodi Obbligatori

```python
class RyLoSStrategyMLv3(IStrategy):
    startup_candle_count: int = 50  # Massimo periodo indicatori
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """CRITICO: Deve chiamare freqai.start() PRIMA degli indicatori"""
        dataframe = self.freqai.start(dataframe, metadata, self)
        
        # Calcola indicatori per la strategia (non per FreqAI)
        dataframe["rsi"] = ta.RSI(dataframe["close"], timeperiod=10)
        # ... altri indicatori
        
        return dataframe
    
    def feature_engineering_expand_all(self, dataframe, period, metadata, **kwargs):
        """Features espanse per ogni periodo in indicator_periods_candles"""
        dataframe[f"%-rsi_{period}"] = ta.RSI(dataframe["close"], timeperiod=period)
        bb_upper, bb_middle, bb_lower = ta.BBANDS(dataframe["close"], timeperiod=period)
        dataframe[f"%-bb_width_{period}"] = (
            (dataframe["close"] - bb_lower) / (bb_upper - bb_lower)
        )
        dataframe[f"%-volume_ratio_{period}"] = (
            dataframe["volume"] / dataframe["volume"].rolling(period).mean()
        )
        return dataframe
    
    def feature_engineering_expand_basic(self, dataframe, metadata, **kwargs):
        """Features base - CALCOLA QUI gli indicatori per FreqAI"""
        dataframe["%-rsi"] = ta.RSI(dataframe["close"], timeperiod=10)
        dataframe["%-atr_pct"] = (ta.ATR(dataframe, timeperiod=10) / dataframe["close"]) * 100
        
        # IMPORTANTE: ta.STOCHRSI restituisce tupla (fastk, fastd), non dict
        stoch_k, stoch_d = ta.STOCHRSI(dataframe["close"], timeperiod=10,
                                       fastk_period=5, fastd_period=3)
        dataframe["%-stochrsi"] = stoch_k
        
        dataframe["%-williams"] = ta.WILLR(dataframe, timeperiod=10)
        dataframe["%-pct_change"] = dataframe["close"].pct_change()
        dataframe["%-pct_change_vol"] = dataframe["volume"].pct_change()
        
        return dataframe
    
    def feature_engineering_standard(self, dataframe, metadata, **kwargs):
        """Features standard (non espanse)"""
        dataframe["%-adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["%-hour"] = dataframe["date"].dt.hour
        dataframe["%-day_of_week"] = dataframe["date"].dt.dayofweek
        return dataframe
    
    def set_freqai_targets(self, dataframe, metadata, **kwargs):
        """Target per training - OBBLIGATORIO"""
        # Predice variazione % prezzo tra 1 ora (12 candele da 5m)
        dataframe["&-s_close"] = (
            (dataframe["close"].shift(-12) - dataframe["close"]) / 
            dataframe["close"]
        )
        return dataframe
    
    def get_ml_prediction(self, pair: str) -> float:
        """Ottieni predizione ML corrente"""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1 or "&-s_close" not in dataframe.columns:
            return 0.0
        return dataframe["&-s_close"].iloc[-1]
```

### 2. Config FreqAI (user_data/config_ml.json)

```json
{
  "freqai": {
    "enabled": true,
    "purge_old_models": 2,
    "train_period_days": 10,
    "backtest_period_days": 2,
    "identifier": "rylos_hype_pytorch_v4",
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

### 3. Modello PyTorch (user_data/freqaimodels/RyLoSPyTorchModel.py)

Eredita da `BasePyTorchRegressor`:

```python
from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor
from freqtrade.freqai.torch.PyTorchDataConvertor import DefaultPyTorchDataConvertor
import torch

class RyLoSPyTorchModel(BasePyTorchRegressor):
    @property
    def data_convertor(self):
        return DefaultPyTorchDataConvertor(target_tensor_type=torch.float)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        config = self.freqai_info.get("model_training_parameters", {})
        self.learning_rate = config.get("learning_rate", 3e-4)
        self.model_kwargs = config.get("model_kwargs", {})
        self.trainer_kwargs = config.get("trainer_kwargs", {})
```

### 4. Uso ML nella Strategia v3

**UNICO PUNTO**: Filtro DCA Standard in `adjust_trade_position()`

```python
# Dopo tutti i controlli tradizionali (distanza, prezzo, limiti)
ml_pred = self.get_ml_prediction(trade.pair)
if ml_pred < self.ml_dca_block_threshold.value:  # default: -0.02
    from freqtrade.loggers import logger
    logger.info(
        f"{trade.pair}: DCA blocked by ML filter "
        f"(pred={ml_pred:.4f} < threshold={self.ml_dca_block_threshold.value:.4f})"
    )
    return None

return next_stake, f"dca_{entry_count + 1}_{current_profit*100:.1f}%"
```

**Parametro ottimizzabile**:
```python
ml_dca_block_threshold = DecimalParameter(-0.05, -0.01, default=-0.02, space="buy", optimize=True)
```

## Comandi

```bash
# Backtest con FreqAI
freqtrade backtesting -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --timerange 20241215-20260122

# Hyperopt
freqtrade hyperopt -c user_data/config_ml.json \
  --strategy RyLoSStrategyMLv3 \
  --freqaimodel RyLoSPyTorchModel \
  --hyperopt-loss CalmarRyLoSHyperOptLoss \
  --epochs 50 --spaces buy \
  --timerange 20241215-20260122 \
  --jobs 4
```

## Note Importanti

1. **`self.freqai.start()`** è OBBLIGATORIO in `populate_indicators()`
2. **Tutte le features** devono iniziare con `%`
3. **Tutti i target** devono iniziare con `&`
4. **`ta.STOCHRSI()`** restituisce tupla `(fastk, fastd)` - usa unpacking
5. **`ta.BBANDS()`** restituisce tupla `(upper, middle, lower)` - usa unpacking
6. **Emergency DCA** NON è filtrato da ML (sempre passa)
7. **Entry/Exit** NON usano ML (sempre tradizionali)

## Features Totali (14)

**Base (7)**:
- `%-rsi`, `%-atr_pct`, `%-stochrsi`, `%-williams`
- `%-pct_change`, `%-pct_change_vol`, `%-adx`

**Espanse periodo 10 (5)**:
- `%-rsi_10`, `%-bb_width_10`, `%-volume_ratio_10`

**Temporali (2)**:
- `%-hour`, `%-day_of_week`

## Target ML

`&-s_close`: Variazione % prezzo tra 1 ora (12 candele)
- Esempio: prezzo ora $100, prezzo tra 1h $102 → target = +0.02 (+2%)
