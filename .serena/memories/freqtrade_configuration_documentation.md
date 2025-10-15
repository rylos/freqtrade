# Configurazione Freqtrade

## File di Configurazione

### Formato e Posizione
- **File principale**: `config.json` (directory corrente)
- **Formato**: JSON con supporto commenti `//` e `/* */`
- **Generazione**: `freqtrade new-config --config user_data/config.json`
- **Validazione**: `freqtrade show-config` per vedere configurazione finale

### Schema JSON
```json
{
  "$schema": "https://schema.freqtrade.io/schema.json",
  // Resto della configurazione...
}
```

## Variabili d'Ambiente

### Formato
- Prefisso: `FREQTRADE__`
- Separatore livelli: `__`
- Esempio: `FREQTRADE__STAKE_AMOUNT=200`
- Esempio complesso: `FREQTRADE__EXCHANGE__KEY=<key>`

### Esempi Comuni
```bash
export FREQTRADE__TELEGRAM__CHAT_ID=<chatid>
export FREQTRADE__TELEGRAM__TOKEN=<token>
export FREQTRADE__EXCHANGE__KEY=<key>
export FREQTRADE__EXCHANGE__SECRET=<secret>
export FREQTRADE__EXCHANGE__PAIR_WHITELIST='["BTC/USDT", "ETH/USDT"]'
```

## File Multipli

### Configurazione con add_config_files
```json
{
  "add_config_files": [
    "config-private.json",
    "config-pairs.json"
  ]
}
```

### Precedenza Configurazioni
1. **CLI arguments** (massima priorità)
2. **Environment Variables**
3. **Configuration files** (ultimo file vince)
4. **Strategy configurations** (minima priorità)

## Parametri Principali

### Parametri Obbligatori
```json
{
  "max_open_trades": 3,           // Numero max trade aperti
  "stake_currency": "USDT",       // Valuta di base
  "stake_amount": 100,            // Importo per trade ("unlimited" per tutto)
  "dry_run": true,                // Modalità simulazione
  "exchange": {
    "name": "binance",
    "key": "your_api_key",
    "secret": "your_api_secret"
  }
}
```

### Trading
```json
{
  "tradable_balance_ratio": 0.99,     // % bilancio utilizzabile
  "available_capital": 1000,          // Capitale disponibile
  "amend_last_stake_amount": true,    // Aggiusta ultimo trade
  "last_stake_amount_min_ratio": 0.5, // Ratio minimo ultimo trade
  "fiat_display_currency": "EUR",     // Valuta display
  "timeframe": "5m",                  // Timeframe principale
  "dry_run_wallet": 1000              // Wallet simulazione
}
```

### Exchange
```json
{
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "ccxt_config": {},
    "ccxt_async_config": {},
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"],
    "pair_blacklist": ["BNB/.*"],
    "markets_refresh_interval": 60
  }
}
```

### Order Types
```json
{
  "order_types": {
    "entry": "limit",
    "exit": "limit", 
    "emergency_exit": "market",
    "force_exit": "market",
    "force_entry": "market",
    "stoploss": "market",
    "stoploss_on_exchange": false,
    "stoploss_on_exchange_interval": 60,
    "stoploss_on_exchange_limit_ratio": 0.99
  }
}
```

### Pairlist
```json
{
  "pairlists": [
    {
      "method": "StaticPairList"
    },
    {
      "method": "VolumePairList",
      "number_assets": 20,
      "sort_key": "quoteVolume",
      "min_value": 0,
      "refresh_period": 1800
    }
  ]
}
```

### Protections
```json
{
  "protections": [
    {
      "method": "StoplossGuard",
      "lookback_period_candles": 60,
      "trade_limit": 4,
      "stop_duration_candles": 60,
      "only_per_pair": false
    },
    {
      "method": "MaxDrawdown",
      "lookback_period_candles": 200,
      "trade_limit": 20,
      "stop_duration_candles": 10,
      "max_allowed_drawdown": 0.2
    }
  ]
}
```

### Telegram
```json
{
  "telegram": {
    "enabled": true,
    "token": "your_telegram_token",
    "chat_id": "your_chat_id",
    "balance_dust_level": 0.01,
    "notification_settings": {
      "status": "silent",
      "warning": "on",
      "startup": "on",
      "entry": "silent",
      "entry_fill": "on",
      "exit": "on",
      "exit_fill": "on",
      "protection_trigger": "on",
      "protection_trigger_global": "on"
    }
  }
}
```

### API Server
```json
{
  "api_server": {
    "enabled": true,
    "listen_ip_address": "127.0.0.1",
    "listen_port": 8080,
    "verbosity": "error",
    "enable_openapi": false,
    "jwt_secret_key": "your_secret_key",
    "CORS_origins": [],
    "username": "freqtrade",
    "password": "your_password"
  }
}
```

### Logging
```json
{
  "initial_state": "running",
  "force_entry_enable": false,
  "internals": {
    "process_throttle_secs": 5,
    "heartbeat_interval": 60,
    "sd_notify": false
  },
  "logfile": "logs/freqtrade.log",
  "verbosity": 3
}
```

## Esempio Configurazione Completa

```json
{
  "$schema": "https://schema.freqtrade.io/schema.json",
  "max_open_trades": 3,
  "stake_currency": "USDT",
  "stake_amount": 100,
  "tradable_balance_ratio": 0.99,
  "fiat_display_currency": "EUR",
  "timeframe": "5m",
  "dry_run": true,
  "dry_run_wallet": 1000,
  "cancel_open_orders_on_exit": false,
  "trading_mode": "spot",
  "margin_mode": "",
  "unfilledtimeout": {
    "entry": 10,
    "exit": 10,
    "exit_timeout_count": 0,
    "unit": "minutes"
  },
  "entry_pricing": {
    "price_side": "same",
    "use_order_book": true,
    "order_book_top": 1,
    "price_last_balance": 0.0,
    "check_depth_of_market": {
      "enabled": false,
      "bids_to_ask_delta": 1
    }
  },
  "exit_pricing": {
    "price_side": "same",
    "use_order_book": true,
    "order_book_top": 1
  },
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "ccxt_config": {},
    "ccxt_async_config": {},
    "pair_whitelist": [
      "BTC/USDT",
      "ETH/USDT"
    ],
    "pair_blacklist": [
      "BNB/.*"
    ]
  },
  "pairlists": [
    {"method": "StaticPairList"}
  ],
  "telegram": {
    "enabled": false,
    "token": "",
    "chat_id": ""
  },
  "api_server": {
    "enabled": false,
    "listen_ip_address": "127.0.0.1",
    "listen_port": 8080,
    "verbosity": "error",
    "enable_openapi": false,
    "jwt_secret_key": "",
    "CORS_origins": [],
    "username": "",
    "password": ""
  },
  "bot_name": "freqtrade",
  "initial_state": "running",
  "force_entry_enable": false,
  "internals": {
    "process_throttle_secs": 5
  }
}
```