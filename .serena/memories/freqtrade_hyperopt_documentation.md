# Hyperopt - Ottimizzazione Parametri Freqtrade

## Concetti Base

### Cos'è Hyperopt
- Ottimizzazione automatica dei parametri della strategia
- Usa algoritmi di Optuna (NSGAIIISampler)
- Esegue migliaia di backtest con parametri diversi
- Trova combinazione ottimale che minimizza loss function

### Requisiti
- Dati storici (come per backtesting)
- CPU potente (usa tutti i core)
- Dipendenze hyperopt: `pip install -r requirements-hyperopt.txt`

## Parametri Ottimizzabili

### Tipi di Parametri
```python
from freqtrade.strategy import (
    BooleanParameter, CategoricalParameter, 
    DecimalParameter, IntParameter, RealParameter
)

class MyStrategy(IStrategy):
    # Parametri per segnali di entrata (space='buy')
    buy_rsi_enabled = BooleanParameter(default=True, space='buy')
    buy_rsi = IntParameter(20, 40, default=30, space='buy')
    buy_adx = DecimalParameter(20, 40, decimals=1, default=30.1, space='buy')
    
    # Parametri per segnali di uscita (space='sell')
    sell_rsi = IntParameter(60, 80, default=70, space='sell')
    sell_hold = CategoricalParameter(['none', 'profit', 'loss'], default='none', space='sell')
```

### Spaces Disponibili
- **buy**: Parametri per segnali di entrata
- **sell**: Parametri per segnali di uscita  
- **roi**: Ottimizzazione ROI
- **stoploss**: Ottimizzazione stoploss
- **trailing**: Parametri trailing stoploss
- **protection**: Parametri protezioni
- **all**: Tutti gli spazi
- **default**: buy + sell + roi + stoploss

## Comandi Hyperopt

### Comando Base
```bash
freqtrade hyperopt --strategy MyStrategy --epochs 100 --spaces buy sell
```

### Parametri Principali
- `-e/--epochs`: Numero di iterazioni (default: 100)
- `--spaces`: Spazi da ottimizzare (buy, sell, roi, stoploss, etc.)
- `-j/--job-workers`: Core CPU da usare (-1 = tutti)
- `--timerange`: Range temporale dati
- `--min-trades`: Numero minimo trade per valutazione
- `--hyperopt-loss`: Funzione di loss da usare

### Funzioni di Loss Disponibili
- **SharpeHyperOptLoss**: Massimizza Sharpe ratio
- **SortinoHyperOptLoss**: Massimizza Sortino ratio
- **OnlyProfitHyperOptLoss**: Solo profitto totale
- **CalmarHyperOptLoss**: Calmar ratio
- **MaxDrawDownHyperOptLoss**: Minimizza drawdown
- **ShortTradeDurHyperOptLoss**: Minimizza durata trade

## Esempio Strategia con Hyperopt

```python
class OptimizedStrategy(IStrategy):
    # Parametri ottimizzabili
    buy_rsi = IntParameter(20, 40, default=30, space='buy')
    buy_adx = DecimalParameter(20, 40, decimals=1, default=30.1, space='buy')
    sell_rsi = IntParameter(60, 80, default=70, space='sell')
    
    def populate_indicators(self, dataframe, metadata):
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=14)
        return dataframe
    
    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe['rsi'] < self.buy_rsi.value) &
            (dataframe['adx'] > self.buy_adx.value),
            'enter_long'] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[
            (dataframe['rsi'] > self.sell_rsi.value),
            'exit_long'] = 1
        return dataframe
```

## Gestione Risultati

### Visualizzare Risultati
```bash
# Lista risultati hyperopt
freqtrade hyperopt-list

# Mostra dettagli risultato specifico
freqtrade hyperopt-show -n 1

# Esporta migliori parametri
freqtrade hyperopt-show -n 1 --print-json --no-header
```

### Applicare Risultati
I parametri ottimali vengono automaticamente esportati in:
- `user_data/hyperopt_results/strategy_<name>.json`
- Possono essere copiati nella strategia

## Best Practices

### Performance
- Usare `--analyze-per-epoch` per strategie complesse
- Limitare epochs iniziali (100-500) per test
- Usare `--random-state` per risultati riproducibili
- Ottimizzare un space alla volta per strategie complesse

### Validazione
- Sempre validare risultati con backtest separato
- Testare su dati out-of-sample
- Attenzione all'overfitting con troppi parametri
- Usare `--min-trades` per evitare risultati con pochi trade

### Esempio Comando Completo
```bash
freqtrade hyperopt \
  --strategy MyStrategy \
  --epochs 500 \
  --spaces buy sell \
  --timerange 20230101-20231201 \
  --hyperopt-loss SharpeHyperOptLoss \
  --min-trades 100 \
  -j 8
```