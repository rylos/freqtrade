# Artifact report di un epoch hyperopt (procedura)

Quando Marco chiede "l'artifact/grafico dell'epoch N":

## 1. Estrazione (su debian, NON ferma l'hyperopt — .fthypt è append-only)

Script pronto: `/tmp/extract_epoch.py N` su debian (copia nello scratchpad sessione 2026-07-21; è cresciuto per append, 3 blocchi). Produce `/tmp/epN_params.json` (deploy amazon) e `/tmp/epN_chart.json` con:
- equity giornaliera, underwater, serie TWE (max su trade attivi di `max_stake_amount*leverage/equity_giorno`), `twe_limit`
- stats: profit, dd, sortino, sharpe, cagr, profit_factor, trades, tpd
- extra: winrate, expectancy, sqn, max_consec_wins/losses, holding_avg_h, holding max, market_change, **adg / adg_w / mdg_w** (10 slice trailing come lo scoring passivbot, in ratio/giorno), **dd_duration_d** (streak max giorni sotto il picco — il campo freqtrade `drawdown_duration_s` arriva vuoto, va calcolato dalla curva underwater)
- exit_reasons grezzi (tag dinamici!) — aggregare per famiglia: `tp_grid*`, `sell_4rsi*`, `sell_trailing_close*`, `unstuck*`, `stop_loss`, `emergency*`

## 2. Pagina — builder riusabile: `python build_report.py N` (scratchpad, legge epN_chart.json)

Novità 2026-07-21 sera: due curve (balance realizzato + equity mark-to-market, campo `equity_mtm`), toggle log/lineare, underwater su MTM, tile "Max DD mark-to-market". La MTM va ricostruita **dai singoli fill** (`trades[].orders`: amount/cost/safe_price/timestamp — ultimo blocco di extract_epoch.py): la prima versione approssimata (size/avg finali) gonfiava gli spike intra-trade (+35% finti) e l'underwater (-32% da picco finto). Con i fill esatti il dd MTM dell'epoch 2105 è **11.9% ≈ realizzato 11.5%**: l'unrealized risk della famiglia di candidati è contenuto, non nascosto.

Sezioni: header → tiles riga 1 (Profitto+multiplo, Max DD, Sortino, Trade+/g, CAGR, Profit factor) → tiles riga 2 (**adg, adg_w, mdg_w in %/g**, Winrate, Expectancy, SQN, Loss consecutive max, Holding medio, Holding max, DD duration, Buy&hold vs strategia) → equity scala log → underwater → TWE con linea limite → tabella "Exit per meccanica" → tabella mensile in details.
Palette dataviz default (blu #2a78d6/#3987e5), light+dark, SVG inline con crosshair+tooltip.

## 3. Pubblicazione

STESSA URL sempre (da altra sessione passarla come `url`):
`https://claude.ai/code/artifact/508e2d41-3f46-4922-a325-3b7c2a9b2cae` — favicon 📈.

## Segnali da commentare
- Quota P&L per meccanica (tipico: tp_grid ~89%, 4RSI ~10%, trailing ~1%)
- **`stop_loss` count** = trade a stake −100% (quasi-liquidazione, stoploss −1): nella famiglia di candidati 2026-07 sono SEMPRE gli stessi 2 eventi (~4% del lordo) — tail risk irriducibile senza stoploss vero; caso peggiore strutturale = liquidazione a pieno TWE ≈ −70% wallet
- mdg_w/adg_w ≈ 0.6 = compounding sano (wiki passivbot: il config buono aveva 0.64)
- Confronto buy&hold `market_change`

## Note
- Skill `dataviz` prima del grafico, `artifact-design` prima della pagina (obbligo harness)
- Deploy epoch su amazon dry-run: `epN_params.json` → scp come `user_data/strategies/RyLoSStrategy.json`, **cancellare `tradesv3.dryrun.sqlite*`**, riavviare bot nel tmux `ft`, verificare 0 errori + heartbeat e che il log riporti lo stoploss atteso
- ⚠️ **il params json DEVE includere la chiave "stoploss"** (`params_details["stoploss"]`, spazio hyperopt separato) — extract_epoch.py aggiornato; senza, la strategia gira con stoploss -1 (liquidazioni!)
- Plot ufficiali (`plot-profit`, `plot-dataframe`): generarli su debian e lasciarli in `/opt/freqtrade/user_data/plot/` — Marco li guarda via sftp (vedi memoria plot-delivery)
