# ops — script operativi del live (copia di riferimento)

Gli script qui dentro **girano su amazon**, non da questo repo: la copia serve a
sopravvivere a una ricostruzione del server e a versionare le modifiche.

| file | dove gira | cron |
|---|---|---|
| `watchdog_freqtrade.py` | amazon, `~/watchdog/freqtrade_watchdog.py` | `5-59/10 * * * *` |

Dopo ogni modifica qui, ricopiare sul server e verificare che l'md5 combaci:

```bash
scp ops/watchdog_freqtrade.py amazon.ziliani.net:'~/watchdog/freqtrade_watchdog.py'
ssh amazon.ziliani.net 'python3 ~/watchdog/freqtrade_watchdog.py; echo exit=$?'
```

## watchdog_freqtrade.py

Sorveglia il bot live **RyLoS** (HYPE/USDT:USDT su bybit). Il bot non scrive su
file: il log vive solo nel buffer del tmux `ft`, quindi i controlli si fanno su
`tmux capture-pane` più il database dei trade (`tradesv3.sqlite`, aperto in
sola lettura — è in WAL, i mtime non dicono nulla).

Rileva: processo assente · heartbeat fermo da >10 min · stato ≠ RUNNING · righe
ERROR/CRITICAL negli ultimi 15 min · db illeggibile.

**Due classi di rumore sono escluse dall'allarme** (contate nel body del ping, così
un'anomalia prolungata resta visibile). Il criterio è sempre lo stesso: un allarme
che suona sempre per niente insegna a ignorarlo, ed è così che si perde quello vero.

- **Errori del canale Telegram** — rete, il bot continua a operare. La prima
  versione del 2026-08-06 dava subito un falso positivo su
  `Exception happened while polling for updates`.
- **Disconnessioni del websocket** (`exchange_ws`, `NetworkError` code 1006):
  bybit chiude la connessione e freqtrade rientra da solo passando al REST alla
  candela successiva. Fra il 07 e il 10/08/2026 hanno prodotto **5 allarmi
  identici**, tutti auto-risolti in meno di 5 minuti, nessuno con impatto sul
  trading. ⚠️ **Non è un silenziamento**: tornano a essere un guasto se sono ≥3
  nella finestra di 15 min (la rete non tiene) oppure se il fallback al REST non
  compare entro 6 minuti — una candela piena — perché lì il bot è davvero senza
  dati. Costanti `WS_TOLERATED`, `WS_FALLBACK_GRACE_MIN`.

⚠️ **Le date del db sono in UTC**, il resto del body è in ora locale: `utc_to_local()`
converte con `astimezone()` e non con un offset fisso, altrimenti d'inverno
sbaglierebbe di un'ora.

**Riavvio automatico solo a processo ASSENTE.** Il motivo è che
`stoploss_on_exchange` è disattivo per scelta: il guard-stop vive nel bot, quindi
a bot morto una posizione aperta resta senza protezione. Un bot vivo ma bloccato
non viene toccato — resta in allarme e decide Marco. Freni: max 2 tentativi in
60 minuti, e il file `~/watchdog/ft_maintenance` che disabilita ogni riavvio
(crearlo **prima** di ogni fermata voluta: deploy, cambio candidato).

**Il nome del candidato non è hardcodato.** `candidato_attivo()` calcola l'md5 di
`user_data/strategies/RyLoSStrategy.json` e lo confronta con gli archiviati in
`user_data/candidates/`, usando il nome del file che combacia (fallback: md5
breve). L'etichetta fissa "T4G" era sopravvissuta a due cambi di candidato prima
che me ne accorgessi.

**Notifiche**: canale unico su healthchecks.io, check `freqtrade (bybit)` — ping
di successo col riepilogo nel body, `/fail` con la diagnosi, e scadenza
automatica se cron o macchina muoiono (dead man switch).

⚠️ L'URL di ping **è una credenziale**: sta solo in `~/watchdog/healthchecks.env`
(chmod 600) sul server, mai nel repo.
