# Struttura repo (fork rylos/freqtrade, 2026-07-21)

Repo: `/home/marco/dev/freqtrade`, fork di freqtrade/freqtrade.
- `origin` = github.com/rylos/freqtrade (develop = branch di lavoro e default PR)
- `upstream` = github.com/freqtrade/freqtrade — ⚠️ upstream ha RISCRITTO la storia (2026-07): mai merge diretto; riallineamento fatto con reset + riapplicazione file custom
- Branch `develop-old` su origin: backup completo pre-riallineamento (MLv3, RL, doc, vecchie loss)

## File custom (tutto qui, il resto è upstream vanilla)

```
user_data/strategies/RyLoSStrategy.py        # strategia (git add -f, upstream la gitignora)
freqtrade/optimize/hyperopt_loss/
  hyperopt_loss_sortino_rylos.py             # loss custom (Calmar rimossa)
freqtrade/strategy/strategy_wrapper.py       # PATCH FORK: opt-out disable_trade_deepcopy
```

`user_data/strategies/RyLoSStrategy.json.pre-passivbot.bak` = vecchi parametri hyperopt archiviati (se presente un nuovo `RyLoSStrategy.json`, freqtrade lo carica e SOVRASCRIVE i default — attenzione dopo ogni hyperopt).

## Convenzioni

- Commit su develop, push su origin; debian si allinea con `git pull`
- La patch a `strategy_wrapper.py` va ricontrollata a ogni riallineamento con upstream (conflitto probabile)
- Loss function: costanti di peso in testa al file con commenti sul razionale; ogni modifica va verificata con l'audit empirico (correlazioni sui `.fthypt`) non solo con scenari sintetici
- Script di audit loss: `loss_audit.py` (scratchpad sessione / `/tmp/loss_audit.py` su debian)
