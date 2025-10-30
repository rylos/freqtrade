# RyLoS Strategy - Procedura Aggiornamento Default

## Comando Standard
Quando l'utente chiede di "aggiornare i default della strategia", seguire questa procedura:

1. Leggere i parametri ottimizzati da: `user_data/strategies/RyLoSStrategy.json`
2. Confrontare con i valori default attuali in: `user_data/strategies/RyLoSStrategy.py`
3. Aggiornare SOLO i parametri con valori diversi
4. Includere anche parametri di classe (es. trailing_stop) se presenti nel JSON

## File Coinvolti
- **Source**: `/home/marco/dev/freqtrade/user_data/strategies/RyLoSStrategy.json`
- **Target**: `/home/marco/dev/freqtrade/user_data/strategies/RyLoSStrategy.py`

## Parametri da Aggiornare
Dal JSON sezione `params`:
- `buy.*` → DecimalParameter/IntParameter con space="buy"
- `sell.*` → DecimalParameter/IntParameter con space="sell"
- `trailing.*` → Attributi di classe (trailing_stop, trailing_stop_positive, etc.)
- `stoploss.stoploss` → Attributo di classe stoploss
- `roi` → Attributo di classe minimal_roi

## Note
- A meno che l'utente non specifichi diversamente, questa è la procedura standard
- Usare fs_read per leggere i file (path assoluti)
- Aggiornare solo valori effettivamente diversi
- Mantenere formattazione e commenti esistenti
