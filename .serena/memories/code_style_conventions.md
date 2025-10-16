# Stile e Convenzioni di Codice Freqtrade

## Formattazione Codice
- **Line length**: 100 caratteri
- **Formatter**: ruff format (compatibile con black)
- **Import sorting**: isort con profilo black
- **Quotes**: Doppi apici per docstring, singoli per stringhe normali

## Convenzioni Naming
- **Classi**: PascalCase (es. `RyLoSStrategy`, `IStrategy`)
- **Funzioni/Metodi**: snake_case (es. `populate_indicators`, `custom_exit`)
- **Variabili**: snake_case (es. `dataframe`, `current_profit`)
- **Costanti**: UPPER_SNAKE_CASE (es. `MINIMAL_ROI`)
- **Parametri**: snake_case con suffisso descrittivo (es. `rsi_oversold_threshold`)

## Type Hints
- **Obbligatori** per tutti i metodi pubblici
- **Imports**: `from typing import Optional, Dict, List, Tuple`
- **Pandas**: `from pandas import DataFrame`
- **Freqtrade types**: `from freqtrade.ft_types import AnnotationType`

## Docstrings
- **Formato**: reST style
- **Quotes**: Doppi apici
- **Struttura**:
```python
def my_method(self, param1: str, param2: int) -> bool:
    """
    Brief description of the method.
    
    :param param1: Description of param1
    :param param2: Description of param2
    :return: Description of return value
    :raises ValueError: When something goes wrong
    """
```

## Struttura Strategia
```python
class MyStrategy(IStrategy):
    # Configurazione base
    timeframe = '5m'
    can_short = False
    
    # Parametri ottimizzabili
    buy_param = DecimalParameter(0.1, 1.0, default=0.5, space='buy', optimize=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calcola indicatori tecnici."""
        
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Definisce condizioni di entrata."""
        
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Definisce condizioni di uscita."""
```

## Linting Rules
- **ruff**: Configurato in pyproject.toml
- **mypy**: Type checking abilitato
- **Complexity**: Max 12 (mccabe)
- **Security**: flake8-bandit checks abilitati

## Pre-commit Hooks
- ruff (linting + formatting)
- mypy (type checking)
- isort (import sorting)
- codespell (spell checking)
- end-of-file-fixer
- trailing-whitespace
