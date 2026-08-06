# Server (RyLoS Classic, aggiornato 2026-07-21 sera)

## debian — hyperopt/backtest freqtrade
- SSH: `ssh marco@192.168.0.34` (28 core)
- Path: `/opt/freqtrade`, venv `.venv` (Python 3.11)
- **Sync via git**: fork `github.com/rylos/freqtrade`, branch develop → `git pull origin develop`
- tmux `ft-hyperopt`: hyperopt RyLoS (~22 epoch/min con -j 30). NON toccare i tmux passivbot: `back`, `back2`, `opt`
- Dati: HYPE/USDT:USDT 5m futures dal 2024-12-05 + funding/mark
- Config: `user_data/config.json` (bybit, HYPE, max_open_trades 1, futures isolated)
- Utility in /tmp: `extract_epoch.py N` (estrazione epoch), `loss_audit.py` (audit correlazioni loss)
- Passivbot (NON toccare): `/opt/passivbot`, config dd39 in `backtests/combined/2026-07-20T11_47_30_dd39/config.json`

## AWS — live trading (`ssh admin@amazon.ziliani.net`, 2 core ARM, 4GB)
- **`/opt/freqtrade`**: ricreato da zero 2026-07-21 (il vecchio era cancellato). Clone shallow fork (https, develop), venv `.venv` (Python 3.11.2, install base), ta-lib C di sistema
- **Config** `user_data/config.json` (chmod 600): bybit chiavi `bybit_02` (importate da `/opt/passivbot/api-keys.json`), HYPE/USDT:USDT futures isolated, max_open_trades 1, stake unlimited, pricing orderbook "other", **dry_run: true, dry_run_wallet 8200**. Telegram: **@freqtraderylos_bot** (token 1363889286:..., chat_id 46772914). api_server NON nel config (schema rifiuta campi vuoti: omettere = disabilitato)
- **Stato al 2026-08-06**: bot up e RUNNING (stessa versione `2026.8-dev-a4ed5fa`, PID 156300), **flat dal 04/08 12:02**, zero posizioni su bybit. **Saldo reale 7.333,10 USDT** (da 8.200 al go-live). Verifica saldo/posizioni: script ccxt con le chiavi del config via `.venv/bin/python` (`fetch_balance`, `fetch_positions`, `fetch_ticker`) — il db dà i P&L dei trade ma NON il funding
- **Stato al 2026-08-04**: live (`dry_run: false`) su **`2026.8-dev-a4ed5fa`** (merge upstream del 04/08, deploy fatto col trade 3 aperto: freqtrade lo riprende dal db, `Found open trade` nel log di avvio). `.py` md5 `857bccc947ca8b4f8ffabc6b507be982`, json T4G md5 `23baf272dbd3e40fb17e9945f3bf6c75`. Prima del riavvio conviene un `list-strategies` come smoke test del codice nuovo sul venv esistente
- **Stato al 2026-07-26**: live (`dry_run: false`) su `2026.7-dev-b0eabf4` dopo il merge upstream; `.py` consolidato coi default 5371 + json live invariato. **Riavvio bot**: `tmux send-keys -t ft C-c` (l'`AttributeError: '_abort'` + errore Telegram in chiusura sono normali), attendere ~12s, poi `tmux send-keys -t ft "cd /opt/freqtrade && .venv/bin/freqtrade trade -c user_data/config.json" Enter`. ⚠️ `pgrep -f "freqtrade trade"` via ssh matcha sé stesso: usare `pgrep -af "bin/freqtrade"`. Update codice: `git checkout -- user_data/strategies/RyLoSStrategy.py` (clone shallow, il file è tracciato e modificato) poi `git pull --depth=50 origin develop`, e verificare md5 = `227d4b88a954a368ef4f97309e68b1eb`
- **tmux `ft`**: bot RyLoS dry-run col candidato hyperopt corrente (`user_data/strategies/RyLoSStrategy.json` = params epoch deployato). Aggiornamento candidato: scp nuovo json params (CON chiave "stoploss"!) + **rm tradesv3.dryrun.sqlite*** + riavvio
- Dal 2026-07-22: **epoch 5371** in dry-run (stoploss -0.721 confermato nel log di avvio; con leva 4x lo stop sta ~3-4 punti di prezzo sopra la liquidazione → la liquidazione non viene mai toccata)
- Altri tmux da NON toccare: `ry`/`ry-hl` (passivbot live), `ft-hl` (vecchio), `mm`
- Go-live: dry-run ≥24h col candidato finale → `dry_run: false` su ok esplicito di Marco
- **Piano passaggio di consegne (2026-07-22, GESTISCE MARCO in autonomia)**: passivbot `ry` opera su bybit_02 (HYPE, hedge mode, posizione aperta) → chiusura posizione → stop tmux `ry` → switch account a one-way mode (freqtrade non supporta hedge) → poi go-live freqtrade. Freqtrade NON può adottare posizioni non sue; due bot sulla stessa coin/account non possono coesistere
- **Esecuzione ordini**: limit "aggressivi" al 2° livello del lato opposto dell'orderbook (price_side "other", order_book_top 2) per entry/exit/clip; stoploss = market lato bot (check ~5s)
- **Decisione Marco 2026-07-22: `stoploss_on_exchange` resta DISATTIVO per ora** (proposto per proteggere il guard-stop da crash del VPS, rifiutato consapevolmente — non riproporlo, ma è il primo candidato se in live si verificano disservizi del bot)
- Il soak test dry-run ha già scovato un bug live invisibile al backtest (unità timestamp) — vedi `mem:tech`

## pc-work / pc-casa
- pc-work: sviluppo, `/home/marco/dev/freqtrade`
- pc-casa: `ssh -p 22222 marco@home.ziliani.net`; screenshot in `/home/marco/Immagini/Schermate/` (recuperare con scp quando li cita)
