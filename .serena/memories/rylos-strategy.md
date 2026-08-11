# RyLoS Classic — dettagli implementazione (2026-07-21 sera)

File: `user_data/strategies/RyLoSStrategy.py` (tracciato nel fork con `git add -f`).

## Segnale: oscillatore 4RSI (dal Pine v3.5 di RyLoS)

```python
osc_4rsi = (RSI(2) + RSI(7) + RSI(14)) / 3 - 50   # istogramma continuo
stoch_k  = STOCHF(14, fastd=3).fastd               # %K = SMA(stoch14, 3)
```
- Entry: `osc_4rsi < osc_entry_threshold` (-40..-10) AND `stoch_k < entry_stoch_os` AND candela rossa AND `close <= EMA(68)*(1+initial_ema_dist)`
- Exit: `osc_4rsi > osc_exit_threshold` AND `stoch_k > exit_stoch_ob` AND profit > min AND candela verde
- Scelta Marco: istogramma continuo hyperoptabile al posto del conteggio discreto del Pine

## Meccaniche passivbot (da config dd39)

- **DCA trailing entry**: discesa >= distanza dinamica dal fill E rimbalzo >= `dca_trailing_retracement_pct` dal minimo. Distanza = `dca_distance * (1 + ATR%*atr_mult) * (1 + exposure_ratio*dca_we_weight)`
- **Close grid**: clip parziali `close_grid_qty_pct` a prezzo > avg*(1+markup); dopo 2 clip chiude tutto (fix moncherino); `close_grid_enabled` hyperoptabile. **~89% del P&L viene da qui**
- **Trailing close**: max dall'ultimo fill >= avg*(1+threshold), prezzo <= max*(1-retracement) → chiude tutto (~1% P&L)
- **4RSI overbought exit**: ~10% P&L, raccoglie i rimbalzi grossi
- **Unstuck**: exposure >= threshold O held > max_days, in perdita, vicino EMA → clip 5% con loss budget, cooldown 12 candele. Non chiude trade (solo riduzioni)
- **TWE**: `total_wallet_exposure_limit` (2-3) governa i limiti; leva exchange fissa 4x
- **first_order_pct 0.01-0.10** (alzato da 0.03: col 3% i trade rapidi muovevano ~0.09% di balance → gain cappato a ~1x; a 10% posizione iniziale fino a 40% nozionale)
- 27 parametri hyperopt; fissi: `ema_span_candles` 68, `dca_cooldown_candles` 2

## Pronti per il run di rifinitura (commit d120857d0, default OFF)
- **profit-lock**: realizza spike di profit non realizzato (trigger su profit ratio, bypassa cooldown; 3 param sell, `profit_lock_enabled` default False)
- **guard-stoploss**: `HyperOpt.stoploss_space()` banda -0.9..-0.4 — attivo solo con `--spaces buy sell stoploss`; default resta -1
- Comando rifinitura: come il run normale + `--spaces buy sell stoploss` (+ bound refinement attorno al candidato scelto)
- **Decisione Marco 2026-07-21: TWE max resta 3** (perimetro passivbot); il resto a discrezione — scelta: first_order_pct estendibile fino a 0.15 nel refinement (dd wall 40% fa da guardiano)
- Prima del refinement, a fine run: analisi bound saturi sul fronte, cluster density dei top 10 (anti-overfit), backtest del candidato spezzato per periodi (2025H1/H2, 2026H1, ultimi 2 mesi); dry-run amazon qualche giorno prima del live

## Tail risk noto
- stoploss = -1 → i rari `stop_loss` sono quasi-liquidazioni (stake -100%). Nella famiglia candidati 2026-07: sempre gli stessi 2 eventi (~4% lordo). Caso peggiore strutturale: liquidazione a pieno TWE ≈ -70% wallet. Opzione se Marco vuole ridurlo: stoploss hyperoptabile (-0.5/-0.25)

## Performance (critico per hyperopt)
- `disable_trade_deepcopy = True` (patch fork `strategy_wrapper.py`, deepcopy era 41% del tempo)
- `_window_extremes`: cache incrementale O(1); `_entry_fill_info` + `_max_orders_cache`; cache svuotate in `populate_entry_trend`
- **Timestamp**: `searchsorted` con `Timestamp(x).as_unit(unit_serie)` — in live le candele ccxt sono datetime64[ms] e gli ordini hanno microsecondi → senza as_unit crasha ("Cannot losslessly convert units"). In backtest non si vede
- Probe verificata: in backtest `iloc[-1]` = ultima candela CHIUSA, `current_rate` = open corrente → no lookahead
- Backtest full-range 19 mesi: ~45s

## Condizioni prima entry del 5371 (reference rapida, tutte su candela 5m CHIUSA)
1. osc_4rsi < **-10.03** (= avg(RSI2,RSI7,RSI14) - 50, cioè media RSI < 40)
2. stoch %K < **36.2** (%K = SMA3 della stoch(14) = fastd di STOCHF)
3. candela rossa (close < open)
4. close <= **EMA68 × 0.989** (1.1% sotto la EMA68 — di solito il filtro più selettivo)
+ nessun trade aperto (max_open_trades 1). Check live al volo: script ccxt+talib su amazon (fetch_ohlcv bybit 5m, escludere la candela corrente non chiusa). Su TradingView: grafico BYBIT:HYPEUSDT.P 5m, Pine con ta.ema(close,68) e banda ×0.989

## Loss: SortinoRyLoSHyperOptLoss (pesi finali validati con audit empirico)
- **Crescita dominante**: profit totale log*4 (100x=18.5pt) + adg_w log*4 + mdg_w log*3 (recency 10 slice) + frequenza log(tpd)*2
- Sortino cappato 15, peso 0.2 (sacrificabile — feedback Marco)
- **DD = vincolo**: gratis <=30%, morbido 30-40% (*20), SQUALIFICA >40% (flat 50 + rampa 200); dd_1pct >20% *10
- Recovery log*0.3 + >30gg*0.1 cap 8; held log*0.6 + >20gg*0.2 cap 8; durata media >5h log*1
- Verifica pesi: audit correlazioni Spearman sui .fthypt reali (`/tmp/loss_audit.py` su debian) — MAI fidarsi solo di scenari sintetici (2 iterazioni di fix sono nate dall'audit: cap penalità, tie-breaker profit)
- ⚠️ **MAI analizzare i .fthypt direttamente su debian mentre l'hyperopt gira**: 2026-07-22 uno script che caricava il file in RAM con 30 job attivi ha mandato il server in OOM/thrashing (SSH giù, recuperato senza danni al run). Procedura: scp del .fthypt su pc-work e analisi in locale

## Esperimento ER BOCCIATO → KAMA anchor (2026-07-22 sera)
- **ER pump-mode rimosso** (era commit fc2f6e841): il run 10k partito senza seed si è incagliato in un bacino inferiore (best 82x vs 265x del 5371, objective -37.98 vs -43.07) e l'A/B sul suo best (ep 4038, ER on vs off) ha mostrato ER **inerte**: +8079% vs +8053%, stessi 1033 trade. Il dominio di er_exit_enabled=True nel fronte (200/200 top) era autostop evolutivo. Decisione Marco: "ER mi sembra inutile", rimosso. Run fermato a 4320 epoch
- Vincolo confermato: MAI rilassare le entry nei pump ("comprare pullback shallow sarebbe un disastro")
- **Seeding hyperopt implementato** (commit e20df7cf3, patch fork): get_default_enqueue_params() in hyperopt_optimizer.py + enqueue_trial dei default strategia in hyperopt.py → epoch 1 = seed esatto (verificato: riproduce il 5371 bit-perfetto, objective -43.07). Lezione: senza seed l'optimizer può bruciare migliaia di epoch in un bacino mediocre
- **KAMA anchor** (commit 2d63ddc0f): `ema_anchor` ora ta.KAMA con `kama_period` IntParameter(10,100, default 30, buy, optimize=True) — richiesta Marco: bounds ottimizzabili, non fissi come la vecchia EMA68. fast/slow fissi 2/30 (limite talib; hyperoptabili solo con KAMA custom, rimandato). Sanity: params 5371 + KAMA(30) = +8714%, 837 trade, underwater 22.7% (peggio della EMA68: il periodo va ri-ottimizzato attorno alla nuova ancora)
- **KAMA anchor BOCCIATO** (2026-07-22 sera): run seedato fermato a ~2000 epoch — objective −35.9 vs −43.07 del 5371/EMA, win rate 91% vs 98, il gap non si chiudeva. Strategia ripristinata dal tag (commit 9bc506bbb). Lezione: l'ancora EMA68 fissa è parte del bacino vincente; KAMA non riproporre come anchor. **Seed del run KAMA verificato a posteriori come corretto** (enqueue 19:44 coi valori 5371 + kama 30; epoch 1 = +8713.64%/837 trade, identico al sanity backtest manuale): la bocciatura è della meccanica, non di un seed contaminato — il json fantasma del run ER era stato rimosso per caso dal rm dell'A/B test
- **Run rifinitura EMA seedato COMPLETATO** (2026-07-22 21:35 → 07-23 07:02, 10k epoch): **il 5371 è rimasto imbattuto per tutte le 10.000 epoch** — miglior sfidante ep 9532 a −42.734 (237x, dd 14.04%, 1139 trade, 9.7h, sl −0.546) vs seed −43.068 (265x, dd 11.94%). Con l'euristica di Marco vince il seed su tutto tranne la durata. **Conclusione: il 5371 è un ottimo locale robusto, confermato da 10k epoch di vicinato seedato — chiuso il ciclo di refinement, il live gira sulla config giusta.** Json fantasma post-run ripulito. fthypt: strategy_RyLoSStrategy_2026-07-22_21-26-52.fthypt su debian
- ⚠️ **TRAPPOLA params json**: quando un hyperopt termina O viene interrotto (Ctrl-C), freqtrade scrive i best params del run in `user_data/strategies/RyLoSStrategy.json`, che al lancio successivo SOVRASCRIVE i default di classe → il seeding accoda i params sbagliati (successo 2026-07-22: primo run EMA seedato col best del run KAMA bocciato). **Prima di ogni lancio hyperopt: `rm -f user_data/strategies/RyLoSStrategy.json`** e verificare che epoch 1 = −43.068
- ⚠️ DISCO debian: i .fthypt pesano 4-20GB l'uno (un run 10k full-range ~16-20GB) — il 2026-07-23 hanno riempito il disco (125GB al 100%, hyperopt AKE morto con ENOSPC). Dopo ogni run analizzato: estrarre ciò che serve e CANCELLARE il .fthypt. Il 5371 è al sicuro nel repo (candidates json + tag), i fthypt sono usa-e-getta
- ⚠️ OOM debian 2026-07-22: mai analizzare i .fthypt (7.6GB!) sul server con hyperopt attivo — streaming via ssh cat | python locale, o sed -n 'Np' per righe singole (riga N = epoch N)

## Giro cross-coin CHIUSO (2026-07-23) — decisione Marco: solo HYPE
- Il 5371 NON è portabile: backtest con params HYPE → BANK -50% (uw 84%), ONDO +57% in 2.5 anni (uw 80%, PF 1.05), AKE -95% (uw 98.5%). I parametri codificano la microstruttura di HYPE
- Hyperopt dedicati tentati e fermati da Marco: BANK (best +258% presto ma bocciato), ONDO (fermato), AKE (fermato). **Decisione finale: "nessuno di questi è maturo come HYPE, preferisco non rischiare" — si resta solo su HYPE, non riproporre coin nuovi senza sua richiesta**
- Ricerca coin: script /tmp/new_listings.py su amazon (ccxt launchTime, filtro equity/ETF/STOCK — bybit 2026 lista soprattutto TradFi perp). Shortlist scartata: AKE, ERA, ZAMA, WLFI, MIRA
- tmux ft-hyperopt debian LIBERO, fthypt ripuliti, disco 47%

## Rischio regime-change HYPE (preoccupazione Marco 2026-07-23, piano NON attivato)
- Il giro cross-coin ha mostrato che il 5371 è specializzato sulla microstruttura di HYPE → se HYPE matura/cambia, degrado possibile. Mitigante: fittato su 19 mesi multi-regime e spezzatino ok ovunque; il degrado atteso è GRADUALE (meno segnali, PF che scivola), il catastrofico resta solo il crash verticale già limitato dal guard-stop (-52% wallet max, no liquidazione)
- Piano di monitoraggio proposto (da attivare se Marco lo chiede): (1) health check mensile — backtest fresco del mese chiuso + confronto live: allarme se PF<1.5, win rate<90% o 2+ guard-stop/mese; (2) drift check live vs backtest; (3) kill-switch da concordare a mente fredda (es. dd live dal via >25% → stop e rianalisi); (4) re-hyperopt trimestrale seedato sul candidato corrente

## Esperimento ETRP BOCCIATO (2026-07-23) — moduli runtime NON riproporre
Regime filter ETRP (HeWhoMustNotBeNamed): piramide 10 EMA(20) ricorsive, strength 0..55 = coppie di medie in ordine bullish. Implementato e testato con ablazione A/B/C su base 5371 (rif. +26.457%, 828 trade, uw 19.15%):
- A solo gate entry (strength<5 blocca prima entry): +7.998%, uw 14.8% — unico che migliora l'underwater, ma costa il 70% del compounding: anche le entry nei crash nel netto pagano
- B solo DCA-bear (distanze ×2 + emergency bloccato in bear): +543%, uw 46.4% — DISASTRO, conferma sperimentale della lezione 5371-vs-9529 (chi media prima vince; allargare le distanze nei crash rompe il motore)
- C solo exit-bull (sopprimi exit 4RSI + profit-lock ×1.5 con strength≥45): +3.516%, 459 trade — dimezza i trade, il trailing non compensa (stessa lezione ER)
- Tutti ON: +150%, uw 47.7%. **Decisione: moduli runtime eliminati (git checkout). Resta nel codice solo regime_strength + gate entry default OFF come dimensione hyperopt.** Lezione: la microstruttura del 5371 gestisce i regimi meglio di qualsiasi sovrastruttura; nessun overlay (ER, KAMA, ETRP) ha mai aiutato

## Stato repo/deploy dopo la chiusura (2026-07-23 sera)
- **Repo locale e debian: strategia riportata alla 5371 pulita** (= tag rylos-5371-baseline; commit 707c7b031, pushato). Spazio allargato e gate ETRP RIMOSSI dal codice (la storia resta nel commit 1123f8b43). Debian: fthypt cancellati, /tmp ripulito, window etrp-exp chiusa, disco 47%
- ⚠️ Il db live amazon (`tradesv3.sqlite`, default senza db_url) è in modalità WAL: il mtime del file principale NON si aggiorna (scritture nel `-wal`) — per lo stato del bot interrogare SEMPRE il db via python/sqlite o Telegram /status, mai i timestamp (errore fatto 2026-07-23: dichiarato "zero trade" con un trade aperto). Primo trade live: 2026-07-23 16:35 UTC, buy_4rsi_-32 @ 58.567, first_order 536.77 USDT
- ⚠️ **AMAZON: il .py live è una versione VECCHIA (default pre-refinement, stoploss classe -1) + `user_data/strategies/RyLoSStrategy.json` = candidato 5371 esatto (verificato 2026-07-23: export 2026-07-22 05:25, stoploss -0.721) che sovrascrive i default al lancio. Su amazon quel json È la config live: MAI cancellarlo!** La regola "rm RyLoSStrategy.json" vale SOLO su debian/host hyperopt (lì è il fantasma post-run). Non aggiornare amazon con git pull né allineare il .py: config live validata così com'è

## Spazio allargato (commit 1123f8b43, 2026-07-23 — RIMOSSO col revert 707c7b031, storia nel commit)
Bound estesi sui saturi del 5371: osc_entry −40..−5 (era saturo a −10, ok Marco ad allargare le entry), entry_stoch 10..50, first_order 0.15, dca_mult 3.5, emergency −0.04, unstuck 0.8; ema_span ottimizzabile su griglia discreta [40..100] (precalcolo in populate_indicators — che in hyperopt gira UNA volta — e selezione per-epoch in populate_entry_trend), dca_cooldown 1..5, gate ETRP optimize=True default OFF. TWE resta cap 3. A defaults = 5371 bit-perfetto (sanity 828/+26.457%). Run 10k seedato COMPLETATO (2026-07-23 12:55→19:23, 6h32m): **seed 5371 imbattuto su tutte le 10.000 epoch anche con lo spazio allargato** — miglior sfidante cluster −41.163 (ep 9092: +26.809%, 865 trade, ma dd 25.56% = più del doppio; profilo diverso: EMA 56, stoch 42.7, dca_mult 1.32, close_grid ON, sl −0.574, regime OFF), gap ~1.9 punti mai chiuso. Nota: l'optimizer ha scelto regime_enabled=False anche potendo accenderlo. **TERZA conferma di robustezza (10k vicinato + 1.3k allargato + 10k allargato): capitolo hyperopt CHIUSO, il 5371 è il massimo dello spazio esplorabile.** fthypt 17GB cancellato, disco 47%, json fantasma ripulito

## Stato live e manutenzione (2026-07-26)
- **Performance live 5371**: 2 trade chiusi, entrambi vincenti, **+215,79 USDT** su wallet ~8200 (≈ +2,6% dal go-live del 22/07). Trade 1: 23/07 16:35 → 24/07 07:10, exit `sell_4rsi_29_5.5%`, +125,47. Trade 2: 24/07 21:10 → 25/07 09:50, exit `sell_4rsi_36_4.4%`, +90,32. Zero guard-stop, zero trade aperti al 26/07 21:00
- **CONSOLIDAMENTO AMAZON FATTO (2026-07-26)**: il `.py` live ha ora i default = 5371 (prima erano pre-refinement con `stoploss = -1`). Verificato che tra le due versioni cambiavano **solo i default + stoploss, zero codice**. Il json `RyLoSStrategy.json` resta e comanda al lancio; il .py è il paracadute. Backup: `RyLoSStrategy.py.bak-preconsolidamento-20260726`. Disciplina futura: a ogni deploy aggiornare ENTRAMBI
- **MERGE UPSTREAM (2026-07-26, commit `b0eabf452`)**: 25 commit di upstream/develop mergiati, zero conflitti, nessun file custom toccato (`RyLoSStrategy.py`, `hyperopt_loss_sortino_rylos.py`, patch `strategy_wrapper.py`/`hyperopt.py`/`hyperopt_optimizer.py`). Contenuto utile: `dda1fcb49` MarginModeAlreadySet ignorata (set margine isolated bybit), `145dcf642` export JSON via orjson che sanitizza NaN/Infinity (riguarda i `.fthypt`), `7f65fc438` remap ordini closed senza `average` — **irrilevante per noi: verificato sul db live che bybit popola sempre `average`**. Il resto è FreqAI/test/leverage tiers Binance. ⚠️ `69fc84835` cambia il formato datetime dell'output backtest in **RFC3339**: se uno script parsa quelle date, va adeguato
- **Regressione post-merge su debian bit-perfetta**: 828 trade, +26.457,15%, dd 11,94%, underwater 19,15%, Sortino 2,35 = identici al riferimento. Deployato anche su amazon (`2026.7-dev-b0eabf4`), riavvio a bot flat, downtime ~1 minuto
- **Candidato XMR ep5123** (commit `bccb2eeee` del 24/07, `user_data/candidates/xmr_ep5123_2026-07-24.json`): +1010% su 934gg, dd 11,1%, 2630 trade, win 98,8%; run fermato da Marco a 7560/10000 epoch, dominava ogni fascia di dd. **NON deployato** — resta HYPE l'unica coin live. Doc tecnica completa della strategia in `user_data/strategies/RyLoSStrategy.md`

## Drift check live-vs-backtest SUPERATO (2026-07-31)
Backtest della finestra out-of-sample 22-31/07 (dati riscaricati fino al 31/07 08:10 su debian e pc-work) confrontato coi 3 trade live:
- Trade 1 (23/07 16:35 → 24/07 07:10, `sell_4rsi_29`) e trade 2 (24/07 21:10 → 25/07 09:50, `sell_4rsi_36`): timestamp ed exit reason **identici**
- Trade 3: 3 entry + 7 clip unstuck in entrambi, prezzi entry a 0.1-0.2% (slippage di esecuzione)
- ⚠️ **Il confronto funziona solo passando `--dry-run-wallet` col saldo reale**: col default 10000 il backtest si ferma a 2 entry e zero clip. Dettagli e regola generale in `mem:tech`

## SCOPERTA 2026-07-31: la coda lunga distrugge valore, e mancava un meccanismo di chiusura

**Analisi P&L per fascia di durata sui 828 trade del 5371** (range esteso al 31/07):
| durata | trade | P&L | quota |
|---|---|---|---|
| < 1 giorno | 736 | +2.474.168 | **+102,2%** |
| 1-3 giorni | 67 | +175.066 | +7,2% |
| 3-7 giorni | 18 | −83.744 | −3,5% |
| > 7 giorni | 7 | −144.458 | −6,0% |
Durata mediana **2,8h**, p90 26,8h, p99 5,8gg, max 15,2gg. I 25 trade oltre 3 giorni valgono **−228.201 USDT (−9,4% del P&L)**: tutto il rendimento viene dai 736 chiusi entro 24h. Attenzione alla causalità: 19 di quei 25 chiudono in profitto, sono i 6 perdenti (guard-stop, durata mediana 43,9h, costo −585.636 = un quarto del P&L) a rovinare la fascia → la mossa giusta NON è chiudere tutto a 3 giorni ma ridurre l'esposizione con l'età.

**⚠️ L'unstuck riduce ma non chiude MAI.** Abbassare `unstuck_max_held_days` senza un meccanismo di chiusura produce rasatura perpetua: misurato un trade da **123 giorni con 215 ordini** che blocca l'unico slot (`max_open_trades=1`) → profitto 0,46x. Spiega perché l'optimizer avesse sempre scelto 16 giorni: i valori bassi, da soli, sono una trappola. **Non riproporre soglie basse senza time_exit.**

**`time_exit_enabled` / `time_exit_days` (commit `894033a56e`)**: chiude il bag per anzianità in `custom_exit`, prima degli exit condizionati al profitto (è l'unico che chiude anche in perdita). Scan della soglia col nuovo objective: 3g −39,666 | **4g −40,304** | 5g −37,426 | 6g −37,621 | 7g −38,763 | 8g −39,615 (curva irregolare: ogni taglio cambia la catena di compounding).
**5371 + time_exit 4g = nuovo candidato di riferimento**: profitto +18.827% (0,78x), **max holding 4,0gg contro 15,2**, **trade oltre 7 giorni 0 contro 7**, ore-capitale immobilizzate oltre 3g −24% (2595 vs 3406), guard-stop 11 (−9% del lordo) contro 13 (−14%), durata media 10,1h vs 11,1h, dd 8,84% vs 8,57%. Le 24 chiusure per anzianità sono quasi tutte in perdita (−1,5% .. −37,4%) ma nessuna pesa oltre il 2% del lordo.

## Esperimento 4 idee — BOCCIATE (2026-07-31)
Nato dal trade 3 live (griglia esaurita in 4h20, poi giorni fermo mentre il prezzo oscilla senza toccare né exit né stop). Commit `e7ae7d262`, backup tag `rylos-5371-pre-4idee-20260731`. **Tutte e 4 con default neutro: a default la strategia è il 5371 bit-perfetto** (regressione su debian: 828 trade, +26.457,15%, dd 11,94%, underwater 19,15%) — è l'optimizer a decidere se accenderle:
1. `unstuck_release_ratio` (default 1.0): isteresi: oggi l'unstuck arma e disarma alla stessa soglia e si ferma col bag al 98% del tetto (live: exposure 0.668 vs 0.681)
2. `harvest_*` (default OFF): a griglia esaurita non esistono né DCA né clip in profitto; clip col markup sull'ULTIMO fill invece che sulla media, stesso budget di perdita dell'unstuck
3. `reentry_*` (default OFF): lo spazio TWE liberato dalle clip oggi resta congelato, qui torna comprabile alle condizioni di trailing entry
4. `stoploss_anchor` (default "first_entry"): freqtrade ancora il guard-stop alla PRIMA entry e non lo sposta più → dopo i DCA lo stop effettivo è più stretto del parametro ottimizzato (live: −62% dello stake invece del −72% nominale). "average" lo ri-ancora via `custom_stoploss` + `after_fill`, **l'unico contesto in cui freqtrade consente di allargare la distanza**
- ⚠️ La doc sconsiglia esplicitamente lo stop in `custom_exit` ("rate-based exits in backtesting can be inaccurate"): lo stop nativo è valutato sul **low della candela**, un callback sul prezzo corrente → in un crash il backtest mentirebbe a favore
**Esito (run cieco 1500 epoch + run seedato)**: idea 4 `stoploss_anchor="average"` BOCCIATA (0 presenze nelle prime 200 epoch pur essendo campionata al 14%) → `optimize=False`. Idea 2 `harvest` INDIFFERENTE (46% nel top-200 = 46,8% globale) → `optimize=False`. Idea 1 isteresi e idea 3 `reentry` restano nello spazio ma con default neutro: reentry all'86,5% nel top-200 è la stessa firma dell'ER (dominanza da autostop evolutivo, poi risultato inerte all'A/B) — **va falsificato con un'ablazione, non creduto sulla frequenza**. Coi default accesi a naso il combinato faceva +9.867% e underwater 27,67% contro +24.210% / 19,15% del 5371: peggio su crescita E rischio.

## Volume profile sul DCA BOCCIATO senza scrivere codice (2026-08-07)
Vaglio di 5 indicatori Pine proposti da Marco (PAVP pivot-anchored, Logistic map DGT, Vol S/R Zones fractal+volume, VP Fixed Range LonesomeTheBlue, VAPI). Analisi statica del codice:
- **Logistic map DGT**: non itera affatto la mappa (`lmap := r*abs(mapeq[i])*(1-mapeq[i])` usa il LAG i, non l'iterata precedente) e `r` = un rendimento ≈0,002, fuori dalla banda caotica 3,57-4 → è un **ROC travestito**; per giunta lo zero-cross dipende solo da `sign(avg)`, la stdev è scenografia. Segnale trend-following = segno opposto al nostro edge mean-reversion. Scartato a vista
- **VAPI LazyBear** = **Chaikin Money Flow ×100** identico alla formula. Costo zero, resta l'unico candidato "gate entry" mai testato (attenzione: `high==low` → divisione per zero)
- **PAVP**: lag 20 barre dalla conferma del pivot + ricalcolo O(n·righe) → caro. **VP Fixed Range**: causale, vettorizzabile col trucco **griglia di prezzo globale fissa + cumsum lungo il tempo → il profilo di una finestra è la differenza fra due righe** (O(n·bin) invece di O(n·finestra·bin))

**DIAGNOSTICO PRIMA DELL'IMPLEMENTAZIONE (metodo da riusare sempre)**: invece di scrivere la feature e lanciare 10k epoch, ho misurato il segnale sui **fill DCA già esistenti** dell'export T4G (`backtest-result-2026-08-06_07-16-31.zip`, 845 trade). Script: `/tmp/vp_dca_diag.py` + `/tmp/vp_dca_control.py` su debian (scratchpad sessione). Costo: 1 ora contro una notte di hyperopt + 1 giornata di codice
- Primo giro **apparentemente ottimo**: i fill DCA cadono sotto VAL nel 71,5% dei casi (baseline mercato 18,7%, lift 3,8x), densità locale di volume 6,7% contro 21,7%; trade con >50% di fill nel vuoto: bad 14,0% e profitto +1,49% contro 6,8% e +6,51%; guard-stop col 90,9% dei fill nel vuoto
- **CONTROLLO CHE LO UCCIDE**: la struttura di volume è solo un **proxy del MAE** (max adverse excursion). `corr(MAE, densità_locale) = −0,639`, `corr(MAE, frac_vuoto) = +0,533`. Correlazioni **parziali** controllando per MAE: frac_vuoto vs profitto −0,221 → **+0,034**; frac_vuoto vs durata +0,394 → **−0,010**; local vs profitto +0,154 → **−0,207 (segno invertito)**. Stratificando per terzili di MAE, denso e rado sono indistinguibili — e nel terzile alto il **denso va peggio** (bad 37,9% vs 32,1%)
- Il MAE da solo separa tutto: sotto mediana **bad 0,0%** / profitto +7,63%; sopra mediana bad 24,4% / profitto −2,08%
- **Verdetto: VP sul DCA bocciato. Overlay a 0 su 4** (ER, KAMA, ETRP, VP). Limite noto dell'analisi: misura "la struttura predice l'esito dati i nostri fill", non il controfattuale di fill piazzati altrove — ma l'assenza di informazione incrementale a parità di discesa è prova forte
- ⚠️ **Due fatti strutturali emersi**: (1) **solo il 20,2% dei trade fa DCA** (171 su 845) ma contengono **11 dei 13 guard-stop** → il DCA resta la leva giusta, sbagliato lo strumento; (2) **a MAE ≥ 18% non sopravvive nessun trade** (n=0 non-stop comparabili): quando HYPE scende così la posizione muore sempre, non è questione di *dove* si compra

## ⭐ TMF sullo stake DCA: PRIMO SEGNALE SOPRAVVISSUTO (2026-08-07, commit `ecbf0e7e1`)
Unico dei 7 indicatori vagliati a passare i controlli. **Twiggs Money Flow** (= CMF ma su true range + media di Wilder; il VAPI di LazyBear è CMF×100, la metà-volume del VSLRT è la stessa famiglia).

**Diagnostico** (`/tmp/cmf_dca_test.py`, `/tmp/tmf_vs_cmf.py`, `/tmp/cmf_robust.py` su debian): il TMF al momento di un fill DCA predice la **discesa SUCCESSIVA al fill** (non il MAE già maturato, che sarebbe circolare).
- `tmf50`: rho −0,247 grezza, **−0,228 parziale** controllando MAE-maturato + ATR% + indice del fill (`cmf20` −0,207). Ortogonale: corr con MAE +0,06, con ATR +0,06 — **al contrario del volume profile, che ne era un proxy**
- Campione indipendente (solo 1° fill DCA per trade, n=174): −0,216 (p=0,004). **Bootstrap a blocchi per trade** (2000 iter): rho medio −0,211, IC95% [−0,332, −0,080], 0,1% di iterazioni col segno sbagliato. Stabilità temporale: prima metà −0,245, seconda −0,196
- Terzili `tmf50`: discesa oltre il 5% nel **35,5% / 22,4% / 10,4%** dei fill. La separazione è quasi tutta nel terzile ALTO → il segnale dice "pressione alta = sicuro" più che "bassa = pericoloso" (è da qui che è nata la forma solo-rialzo)
- ⚠️ CMF e TMF sono **lo stesso segnale**, non due: correlazioni 0,82-0,99, e in combinazione si annullano (`cmf20` dato `tmf21` → −0,052 p=0,44). Non sommarli
- La normalizzazione **z-score mobile 576 candele** conserva tutto (−0,225 contro −0,228 del grezzo) e centra la misura; z288 la degrada (−0,140)

**Implementazione**: `TMF_PERIOD=50`, `TMF_Z_WINDOW=576`, `TMF_FILL_REFERENCE=-0.5` (i DCA scattano per definizione in pressione sotto media: senza riferimento il peso ridurrebbe lo stake in modo *sistematico* invece che differenziale), `dca_tmf_weight` DecimalParameter(0, 1, default **0.6**).

⚠️⚠️ **BUG DI DIVERGENZA LIVE/BACKTEST TROVATO PRIMA DELLA PRODUZIONE** (commit `d3a408e918`, script `live_equivalence.py` nello scratchpad). Confrontando il `tmf_z` calcolato su un dataframe corto (come in live) contro la serie intera (come in backtest) su 300 finestre casuali: con `startup_candle_count=750` l'ultimo valore differiva fino a **1,5e-1 = 9,3% di errore sul fattore di stake**. La causa NON è l'EWM in sé (residuo 2,6e-7 dopo 750 candele) né la rolling, che è piena: è che **la rolling(576) INIZIA dove l'EWM di Wilder ha solo ~174 candele di warmup**, e quel residuo contamina media e deviazione standard dello z-score. Convergenza misurata: **750 → 9,3% | 1000 → 0,084% | 1200 → 0,001% | 1500 → 3e-8**. Fissato a **1500**. Stessa classe del bug delle unità di timestamp: invisibile in backtest. **Regola generale: ogni indicatore ricorsivo annidato dentro una finestra mobile va verificato con il confronto dataframe-corto vs serie-intera, e il warmup deve coprire finestra + convergenza del ricorsivo, non solo la finestra.**

⚠️ Il warmup alto sposta lo start del backtest → **la baseline di confronto va rifatta a ogni cambio di `startup_candle_count`**. Con 1500: peso 0 = **810 trade / +14.991,72%** (Sortino 2,51); 0,4 → 15.886,49% (+6,0%); **0,6 → 16.678,64% (+11,3%, Sortino 2,62)**; 0,8 → 15.276,61%. A peso 0 con warmup 100 il T4G resta bit-perfetto (+20.579,05% verificato)

**⚠️ LA FORMA SIMMETRICA È BOCCIATA, SOLO IL RIALZO FUNZIONA**
- Simmetrica (riduce dove manca pressione): 0,2 → 17.386 | 0,4 → 17.216 | 0,6 → 16.719 | 0,8 → 14.109, **tutte sotto la baseline 18.841**, underwater fermo a 19,15% ovunque = costa senza ridurre il rischio
- **Controllo a peso negativo −0,4 → 14.242**, molto peggio del +0,4: **il segno era giusto, sbagliata la forma d'uso**. Ridurre lo stake toglie anche il beneficio di aver mediato quando il prezzo risale, e il 97% dei trade risale
- Solo-rialzo: 0,2 → 18.629 | **0,6 → 20.412 (+8,3%, Sortino 2,56 vs 2,45, dd e uw invariati)** | 0,8 → 18.904 | 1,2 → 14.372. Curva irregolare come già visto con `time_exit_days`
- **Spezzatino 4 su 5, col warmup CORRETTO 1500** (peso 0 → peso 0,6): fine 2024 204,53 → 213,72 (**+4,5%**), 2025H1 722,87 → 755,11 (**+4,5%**), **2025H2 92,37 → 83,37 (−9,7%)**, 2026H1 199,05 → 229,04 (**+15,1%**), ultimi 2 mesi 28,51 → 30,73 (**+7,8%**). Col warmup vecchio (750) il profilo era identico (2025H2 −9,3%): **la correzione del warmup non sposta il quadro**
- ✅ **SPEZZATINO #2 con confini DIVERSI (richiesto da Marco 2026-08-07): il punto debole era un ARTEFATTO DEL TAGLIO**. 6 finestre su 7 in vantaggio (T4G → +0,6): 2026 intero 193,79 → 223,26 (**+15,2%**), 2026 da marzo 95,23 → 101,77 (+6,9%), ultimi 3 mesi 61,63 → 65,26 (+5,9%), mar-set 2025 289,52 → 295,61 (+2,1%), **set2025-mar2026 154,10 → 157,58 (+2,3%)**, 2025 intero 1489,62 → 1474,54 (−1,0%), full range 15.137,77 → 16.841,01 (+11,3%). **La finestra `20250901-20260301`, che spezza a metà il semestre incriminato invece di isolarlo, è POSITIVA**; e il 2025 intero è piatto (−1,0%), non −9,7%. La divisione H1/H2 esagerava in entrambe le direzioni. **Underwater identico in tutte e 7 le finestre**, trade che cambiano di 2-3 unità
- ⚠️ Cautela sulla lettura: le finestre del secondo spezzatino sono sovrapposte/annidate, quindi "6 su 7" non sono 7 conferme indipendenti. Quello che dimostrano è la cosa specifica per cui erano state costruite: la debolezza del 2025H2 non è robusta allo spostamento dei confini. **Lezione generale: uno spezzatino con un solo set di tagli misura anche dove hai tagliato — replicarlo sempre con confini sfalsati**
- ⚠️ **Punto debole (LETTURA SUPERATA dal secondo spezzatino, tenuta per storia)**: 2025H2 è il semestre peggiore in assoluto (+92% contro +722% di H1) ed è l'unico dove la modulazione costa. Ma attenzione a NON leggerlo come "aggiunge esposizione e quindi amplifica": **a peso 0,6 dd e uw sono IDENTICI al T4G in tutti e 5 i periodi** (14,78 / 19,15 / 8,56 / 4,66 / 10,60). Il sovrappeso cade su fill che non fanno parte degli episodi di massimo underwater, quindi il rischio misurato non si muove — non stiamo comprando profitto con più rischio, stiamo comprando profitto a rischio invariato, con un costo concentrato in un semestre debole

## Sfidante hyperopt epoch 2013: ABLAZIONE SUPERATA, SPEZZATINO NO (2026-08-07)
Run seedato (T4G + tmf 0,6, range `20241205-20260807`, warmup 1500). **A 2.070 epoch il seed è stato battuto** — prima volta nella storia del progetto (il 5371 era rimasto imbattuto per tre run).
- **epoch 2013**: objective −35,28821 contro −35,06187 del seed, profitto **25.659,88%** contro 16.841,01%, dd 3,23% contro 4,66%, 844 trade, `dca_tmf_weight` **0,734**, `stoploss` −0,706
- ⚠️ **I "61 epoch che battono il seed" sono UNA SOLA configurazione ricampionata 61 volte** (metriche identiche al centesimo): l'optimizer converge su un punto e lo ripete. Non contare le epoch come evidenza
- ⚠️ **La tabella "miglior objective per fascia di peso" è inutilizzabile**: la fascia [0,7-0,9) ha 1.052 epoch contro le 26 della fascia [0,0-0,1). Confrontare i massimi fra fasce campionate 40 volte diversamente è la trappola ER/reentry
- ✅ **ABLAZIONE VERA SUPERATA** (stessi 27 parametri, cambia solo il peso): 0,734 → 25.659,88% / dd 3,23% / uw 22,81% / Sortino 3,79; **peso 0 → 18.301,61% / dd 3,92% / uw 23,12% / Sortino 3,28**. Togliendo il TMF si perde il 29% di profitto e peggiorano dd e Sortino. **È la prima dimensione nuova a superare l'ablazione** (l'ER era risultato inerte)
- ❌ **SPEZZATINO FALLITO — solo 3 periodi su 5** (criterio fissato prima di guardare: 4 su 5): fine 2024 196,00 vs 204,53 (**−4,2%**), 2025H1 958,11 vs 722,87 (+32,5%), **2025H2 83,85 vs 92,37 (−9,2%)**, 2026H1 321,56 vs 199,05 (+61,5%), ultimi 2 mesi 34,16 vs 28,51 (+19,8%)
- ❌ **E peggiora l'underwater in 4 periodi su 5**: 15,98 vs 10,60 | **22,81 vs 14,78 (+54%)** | 20,52 vs 19,15 | 11,17 vs 8,56 | 4,02 vs 4,66. Col filtro di Marco (drawdown prima di tutto) è squalificato. Trade negli ultimi 2 mesi 42 contro 54 (−22%)
- **Sfidante epoch 5323** (a 6.120 epoch, objective **−36,27466**, profitto 31.626,77%, dd 3,25%, 838 trade, peso **0,734** di nuovo, sl −0,683). **Ablazione MOLTO più debole del 2013**: peso 0,734 → 31.626,77 / uw 21,26 / Sortino 3,52; peso 0 → 26.274,75 / uw 20,93 / **Sortino 3,73**. Togliendo il TMF si perde il 17% di profitto ma MIGLIORANO Sortino e underwater — e il 5323 senza TMF fa già 26.275% contro i 16.841% del seed: **il suo vantaggio viene soprattutto dagli altri parametri**, non dalla dimensione nuova
- **RIESAME DEL 2013 SUI CONFINI SFALSATI (richiesto da Marco)**: passa da 3 su 5 a **5 su 6**. La bocciatura per conteggio di periodi era anch'essa dipendente dal taglio — il criterio va applicato simmetricamente, non solo quando conviene
- ⚠️⚠️ **MA L'OBIEZIONE VERA RESISTE ED È UN'ALTRA: l'UNDERWATER**. Finestra mar-set 2025: T4G **11,97%**, 5323 **21,26%**, 2013 **22,81%** — quasi il doppio, con entrambi i candidati, e il pattern si ripete in tutte le finestre 2025 di entrambi gli spezzatini. **Il conteggio dei periodi si ribalta spostando i confini; la penalità di underwater no.** È quello il segnale robusto, ed è il motivo per cui entrambi gli sfidanti restano scartati col filtro di Marco
- Delta contro T4G sui confini sfalsati (5323 | 2013): 2026 intero +62,4% | +70,5%; 2026 da marzo +35,0% | +35,8%; ultimi 3 mesi +17,8% | +16,8%; **mar-set 2025 −24,6% | −43,5%**; set2025-mar2026 +29,4% | +30,9%; 2025 intero +56,2% | +22,9%
- **Verdetto: entrambi gli sfidanti SCARTATI** (2013 e 5323)
- **Verdetto storico: sfidante 2013 SCARTATO** — è una configurazione più aggressiva, non migliore. Nota che il profilo è l'opposto dell'ep9981 (lì il vantaggio era tutto nel 2025H1 e il semestre recente peggiorava; qui il vantaggio è nei periodi recenti), ma il criterio di squalifica è lo stesso: non regge ovunque e alza il rischio

## Funding rate come predittore del MAE: BOCCIATO (2026-08-07)
- **Robustezza ai parametri strutturali: 7 perturbazioni su 7 sopra la baseline** (ref −0,3/−0,4/−0,6, finestra 288/2016, periodo 21/100), fra +0,9% e +7,9%, segno mai invertito. **Attesa onesta al netto del bias di selezione: +4-5%, non +8,3%**
- Il rischio non si muove MAI: dd 4,66% e uw 19,15% identici in ogni variante e ogni periodo

**La QUANTITÀ di volume non aggiunge nulla alla DIREZIONE (2026-08-07, `/tmp/vol_magnitude_dca.py`)** — domanda di Marco. Testate 4 misure di volume grezzo ai 226 fill DCA (vol/SMA89, vol/SMA20, z-score del log-volume su 576, volume cumulato 1h):
- Da sole sembrano predire, e **all'opposto dell'intuizione della capitolazione**: terzile a volume ALTO → discesa dopo 3,92%, oltre 5% nel 32,9% dei casi, profitto trade **−0,44%**; terzile BASSO → 3,02%, 18,7%, **+6,47%**. Volume grosso in discesa non è esaurimento dei venditori, è distribuzione
- **Ma controllando anche per il TMF crollano tutte**: vol/SMA89 −0,054 (p=0,42), z-score +0,022 (p=0,74), vol 1h −0,120 (p=0,07). Mentre **il TMF controllando per il volume resta −0,228 (p=0,0006), immutato**. Sui 30 fill peggiori (discesa media 9,67% contro 2,26%) l'unico discriminante è il TMF (p=0,0030), non la quantità (p=0,14)
- Meccanicamente ovvio a posteriori: volume alto in discesa **è** pressione in vendita, cioè TMF negativo. Non sono due informazioni. **Conclusione: non esiste un secondo segnale di volume da sfruttare — quello che i volumi avevano da dire è già tutto nel TMF**

**Metodo riusabile (il vero guadagno della serata)**: calcolare il segnale candidato al momento del fill → correlarlo con l'esito **successivo** → correlazione parziale sui confondenti → campione indipendente + bootstrap a blocchi + stabilità temporale → solo allora scrivere codice. Costo ~1 ora contro una notte di hyperopt. Ha ucciso VP e funding in un'ora, e ha salvato il TMF.

## ⛔ RISULTATO STRUTTURALE: il MAE NON è predicibile all'entry (2026-08-07)
Domanda di Marco: "con tutti i trade peggiori e tutti gli indicatori, non riesci a evitarli?". Risposta misurata su 803 trade (`/tmp/entry_mae_diag.py` su debian), target = MAE, **non** i guard-stop (13 eventi: qualunque filtro fittato su 13 casi è rumore garantito).
- **9 feature all'ultima candela chiusa prima della prima entry**: `osc_4rsi` +0,045 | `stoch_k` +0,051 | distanza EMA68 −0,042 | ATR% +0,040 | ATR10/ATR50 +0,041 | `tmf_z` +0,009 | ret24h −0,079 | ret7d +0,013 | vol realizzata 24h +0,034. **Massimo |rho| 0,079, nessuna passa Bonferroni (p<0,0056)**
- **Quintili senza alcun andamento**: P(MAE>10%) oscilla fra 6% e 13% senza ordine su tutte le feature
- **Ora del giorno Kruskal p=0,386, giorno della settimana p=0,637**: niente
- ⛔ **Sui 13 guard-stop NESSUNA delle 9 variabili li distingue nemmeno a p<0,10**. Non sono un sottoinsieme riconoscibile: sono entry identiche a tutte le altre seguite da un mercato diverso
- **Conseguenza operativa**: la coda è un **costo strutturale**, non un difetto filtrabile. Le uniche leve che funzionano sono quelle che agiscono **senza predire** — time exit (cappa la durata), TWE/`dca_we_weight` (limitano quanto si è carichi quando arriva), guard-stoploss (tronca) — e sono tutte già in strategia e già ottimizzate. **Non riproporre filtri di entry per evitare i trade peggiori.**
- Spiega retroattivamente perché 5 overlay su 6 sono falliti: cercavano tutti di predire una cosa che da OHLCV+volume non è predicibile. E spiega perché il TMF invece regge: **non predice l'esito dell'entry**, predice la continuazione a brevissimo orizzonte dopo un fill DCA — pretesa molto più modesta e locale
- Limite: 9 feature dalla famiglia OHLCV+volume. Non esclude che order flow, open interest o cross-asset predicano — ma quelli non sono backtestabili con i dati che abbiamo

## Funding rate come predittore del MAE: BOCCIATO (2026-08-07)
Ipotesi: pullback con funding molto positivo = long affollati → liquidazioni → discese più profonde. Sarebbe stato il primo segnale a **predire** il MAE invece di misurarlo. Script `/tmp/funding_test.py` su debian (806 trade, funding preso strettamente prima della prima entry, 6 feature: last/24h/72h/7d/cum7d/percentile-90gg).
- **Nessuna correlazione col MAE**: massimo +0,082 (`f_pct`, p=0,020) — con 6 feature la soglia di Bonferroni è p<0,0083, nessuna passa. Le parziali (controllando ret7d + ret24h + ATR%) sono **identiche alle grezze** → stavolta non è un confondente, è proprio assenza di segnale
- **Quintili non monotoni**: Q4 il peggiore (MAE>10% 16,2%, bad 8,1%), **Q5 = funding più alto il MIGLIORE** (bad 0,6%, profit +7,25%) → il contrario dell'ipotesi
- **Guard-stop col segno rovesciato**: funding medio 0,0128% contro 0,0158% del resto (entrano con funding più BASSO). Mann-Whitney nella direzione ipotizzata p=0,35
- Residuo marginale: trade con MAE>10% hanno funding 0,0169% vs 0,0156%, p=0,054 — effetto minuscolo, uno fra molti test, non azionabile
- ⚠️ **Il funding come COSTO è irrilevante**: 13.259 su 2.061.695 di lordo = **0,64%**. Ripartizione per durata: <1g −0,021% su stake (24% del totale), 1-3g −0,143% (27%), **>3g −0,236% (49% del totale su soli 27 trade)** → l'unica leva sul funding è la durata, e il time exit T4G la sta già tirando. In live pesò molto (62,7 su 867) solo per il trade 3 patologico da 8 giorni. Niente da ottimizzare
- **Metodo confermato**: il test costa ~1 ora e vale per qualsiasi segnale candidato — calcolarlo alla prima entry, correlarlo col MAE successivo, poi correlazione parziale sui confondenti. Da rifare prima di ogni implementazione

## Loss: taratura delle penalità temporali (2026-07-31, commit `b54c0a2800`)
- ⚠️ **Le soglie erano fuori dal dominio reale**: guardrail held a 20 giorni (max reale 15,2) e recovery a 30 (reale 15,9) → entrambi MAI scattati; col cap a 8 la penalità held valeva ~1,7 punti contro i ~18 del premio profitto
- Prima taratura SBAGLIATA (cap 15, guardrail 0,4, tail scale 12): swing 7,4 punti. **Il premio profitto è log(profit)×4, quindi 8x di profitto valgono solo ~8 punti** → la loss preferiva l'epoch 436 (+3.105%, dd 15,2%, 39 giorni sott'acqua) al seed (+24.210%, dd 8,57%, 15 giorni). Lezione: qualsiasi penalità nuova va dimensionata contro la scala logaritmica del premio profitto
- Taratura corretta: `HELD_PENALTY_CAP` 4, `MAX_POSITION_HELD_DAYS` 6, `HELD_DAYS_GUARDRAIL_SCALE` 0.05, `TAIL_HOURS_SHARE_SCALE` 2.0, `MAX_RECOVERY_DAYS` 15. Swing ~1,6 punti = tie-breaker fra configurazioni comparabili, tollera al massimo ~1,5x di profitto in meno
- Nuovo termine `TAIL_HOURS_SHARE_SCALE`: quota di ORE-TRADE oltre 3 giorni sul monte-ore totale (5371: 17,5%) — il max_held guarda un solo trade, questo misura quanto capitale resta immobilizzato

## Quanto tempo può stare fermo senza trade (misurato 2026-08-11)
Domanda nata dal live: 31 ore senza un'entry, è normale? Sì. Backtest T5 sul range intero (817 trade, 2024-12-10 → 2026-08-06), vuoto = `open_date` del trade N+1 meno `close_date` del trade N (con `max_open_trades=1` è esattamente il tempo a conto flat).

| mediana | p75 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|
| 4,0 h | 9,2 h | 15,5 h | 21,9 h | 41,2 h | **70,8 h (2,95 gg)** |

- Vuoti > 24h: 34 su 816 (4,2%). > 48h: 5 (0,6%). **Mai oltre 3 giorni** in 20 mesi
- I cinque più lunghi: 09-12/04/2026 (70,8h), 02-04/07/2026 (54,8h), 25-27/10/2025 (52,3h), 04-06/08/2026 (50,6h — successo davvero sul bot live), 02-04/05/2026 (49,1h)
- ⚠️ **Le attese si allungano strutturalmente**: mediana per trimestre 1,2h (2024Q4) → 5,2h (2026Q1) → 8,7h (2026Q3); trade/mese da ~90 (dic 2024-gen 2025) a 13-45 nel 2026. Non è un guasto: è HYPE meno volatile e quattro condizioni da soddisfare insieme. **Va tenuto presente quando si confronta la frequenza live con quella del backtest full-range: la media è dominata dal 2025.**
- **Soglia operativa: oltre 72 ore di flat siamo fuori da tutto lo storico** → allora vale la pena verificare che il bot stia davvero valutando le candele (errore silenzioso dell'exchange, dataprovider fermo). Sotto, non c'è niente da indagare
- Script `~/oi_research/gaps.py` su debian (output `gaps.out`), cancella da sé l'export del backtest

## ⭐ ANATOMIA DELLE PERDITE DI T5 e tentativo di tagliare i guard-stop (2026-08-10)
Domanda di Marco: «riusciamo a tagliare gli stoploss rimasti, o è impossibile?». Risposta misurata sull'export T5 `backtest-result-2026-08-09_22-37-15.zip` + **44 backtest** (due scansioni). **Esito: si può, ma non conviene. Deciso di lasciare tutto com'è.**

### Dove stanno davvero le perdite (dati di riferimento, riusare questi)
27 trade in perdita su 817, **−450.369 in totale**:
| famiglia | n | P&L | ratio medio | durata mediana |
|---|---|---|---|---|
| guard-stop | 10 | **−202.052** | −44,3% | 55h |
| **time_exit** | 9 | **−194.507** | −13,4% | **144h** (= tetto duro) |
| 4rsi | 8 | −53.810 | −7,7% | 107h |
- ⚠️ **I guard-stop sono meno della metà del problema.** Le uscite per anzianità costano quasi altrettanto, e **non sono crash**: MAE 2,19% / 3,77% / 4,37% / 7,02%, posizioni appena sott'acqua uccise dall'orologio. Muoiono tutte a 144h perché `TIME_EXIT_HARD_MULT = 2.0` × `time_exit_days = 3` = tetto duro a 6 giorni, che chiude tutto **incondizionatamente**
- ⚠️⚠️ **Nel 2026 i guard-stop sono ZERO.** Tutti e 10 stanno fra 2024-12 e 2025-12. Le perdite del periodo recente sono interamente time_exit; il 2026Q3 chiude in negativo (−14.336) solo per quelle, e la peggior perdita non-stop di tutto il backtest è un time_exit del 2026-07-15 da −54.736. **Questo fatto spiega tutto il resto** (vedi sotto)
- **Curva di sopravvivenza per profondità**: scendendo ≥5% sotto il carico medio vince ancora il 78,5% (n=107); ≥8% il 54,5% (n=33); ≥10% il 38,1% (n=21); ≥12% il 20,0% (n=10); **≥15% nessun trade ci arriva mai** — il guard-stop scatta prima
- ⛔ **Tagliare più in profondo NON conviene**: chiudere tutti quelli che toccano il 10% realizzerebbe ~−295.000 contro i −214.000 che quei trade producono davvero (a 12%: −223.000 vs −191.000). **Il guard-stop è già piazzato dove il recupero smette di esistere** — i vincitori oltre il 12% portano +1.829 in tutto. Non riproporre di stringere la soglia
- Il **peggior trade è inchiodato a −49,3%** in tutte e 44 le configurazioni provate: la profondità della coda la fissa il guard-stop, non il time exit
- Carico: stake mediano dei guard-stop **2,41×** il normale e **10 su 10 hanno fatto DCA** — ma il quintile di stake più alto genera +1.077.546 su ~2,1M di lordo, quindi strozzare la taglia costa molto più di quanto salvi (coerente con l'ablazione B dell'ETRP)

### Scansione 1: `time_exit_days` × `time_exit_qty_pct` (16 backtest, nessuna modifica al codice)
Baseline riprodotta bit-perfetta (817 trade, +22.312,23%). **T5 (3, 0,50) resta il migliore col criterio di Marco**: filtrando su underwater ≤12% restano le quattro `days=3` più `(6, 0,25)`, e fra quelle il Sortino è 3,57 (T5) contro 3,43 / 2,95 / 1,72.
- ⭐ **RISULTATO STRUTTURALE — sono vasi comunicanti**: allungando `days` le uscite per anzianità crollano da 9 a 1 ma il costo dei guard-stop sale da −202.052 a −324.576. Le perdite **si spostano di casella, non spariscono**. Quelle perdite non le crea il meccanismo, le crea il mercato
- La **chiusura secca** (`qty = 1,00`) è un disastro: +14.547% e underwater 31,21% contro 11,97%. Lo scarico graduale vale moltissimo
- `(4, 0,75)` ha il Sortino migliore (4,14) e la coda più bassa (−247.521) ma underwater **35,55%**: minimizza le perdite concentrando il rischio, profilo già scartato due volte
- **Nota utile**: quei due parametri erano stati tarati prima che l'unstuck fosse spento e il crash guard aggiunto. Non si sono spostati

### Scansione 2: il tetto duro (11 varianti, braccio ISOLATO con `--strategy-path`)
Metodo: copia della strategia in `~/oi_research/arm/`, patch per variante, **i file veri mai toccati** (md5 `.py` `15717b2b…` e `.json` `2b6d6c5a…` verificati alla fine). Controllo riproduce T5 esatto.
- ⛔ **Slegare `TIME_EXIT_HARD_MULT` non serve**: `mult_1.5/3.0/4.0/6.0` peggiorano tutte
- ⛔ **Dare più tempo ai poco-sott'acqua non serve**: le `grazia_*` (tetto ×2 se `current_profit > −X`) peggiorano tutte
- ⭐ **Funziona la direzione OPPOSTA — `anticipo`**: dimezzare il tetto quando la posizione è sotto una soglia di profondità. A −0,25: **guard-stop da 10 a 7**, profitto **+7,8%** (+24.045% vs +22.312%), e **underwater, drawdown, Sortino e peggior trade identici al centesimo**
- Il meccanismo NON è "perdo meno": la coda totale peggiora (−487.093 vs −396.559). Il guadagno viene dai **trade in più** (830 vs 817) — con `max_open_trades=1` chiudere prima un bag condannato **libera l'unico slot**. Stessa lezione del time exit originale, applicata alla profondità invece che all'età

### ❌ E perché `anticipo` è stato comunque BOCCIATO
Criteri fissati **prima** di guardare: (a) soglia non isolata, (b) ≥4 periodi su 5 in **entrambi** i set di confini, (c) underwater mai peggiore.
- ✅ **(a) passa**: altopiano largo da 0,18 a 0,25 (profitto +23.615 / +24.357 / +23.997 / +24.045, stop sempre 7, underwater sempre 11,97%). Il massimo è a **0,20**, non a 0,25
- ✅ **(c) passa**: underwater identico al centesimo in **tutti e dieci** i sotto-periodi
- ❌ **(b) fallisce: 2 su 5 in ENTRAMBI i set.** E il verso non è casuale, è **temporale**: vince ovunque nel 2025 (2025H1 +13,8%, 2025H2 +11,7%, 2025 intero +20,3%) e perde ovunque nel 2026 (2026H1 −9,5%, 2026 intero −9,6%, 2026 da marzo −14,1%)
- **Spiegazione meccanica, ed è il punto**: nel 2026 non c'è **nessun** guard-stop, quindi un meccanismo che converte guard-stop in uscite anticipate non ha niente da prevenire — continua però a tagliare posizioni profonde che poi si sarebbero riprese. **Nessuna soglia può sistemarlo**: il problema non è dove tagli, è che non c'è più niente da salvare
- **Lettura alternativa onesta (decisione di Marco, presa: NO)**: è un'assicurazione che paga nei periodi con crash e costa ~10% del rendimento quando non ce ne sono. Differenza col crash guard, che era stato accettato su base analoga: **il crash guard quando non serve non costa niente**, questo un premio lo paga, e lo paga proprio nel periodo su cui il bot gira adesso. Se un giorno si volesse l'assicurazione, il candidato è `anticipo_0.20`
- 📌 **SECONDA VOLTA IN UN GIORNO che l'aggregato sul range intero è bello e lo spezzatino lo uccide** (l'altra è `rel_24h`). Il +7,8% era dominato dal 2025 esattamente come quel bootstrap era dominato dalla prima metà. **Lo spezzatino a confini sfalsati non è una formalità: è il test che decide.**
- Script: `~/oi_research/stop_anatomy.py`, `stop_anatomy2.py`, `scan_timeexit.py`, `scan_hard.py`, `scan_anticipo.py` su debian; risultati in `scan_timeexit.json` e `scan_hard.json`

## Smart Money Concepts (LuxAlgo): SCARTATO all'analisi statica (2026-08-10)
Vaglio senza scrivere codice, come per il volume profile. Tolto il vocabolario è un pacchetto di rotture di estremi su un'unica primitiva (pivot fractal a N barre): **BOS = breakout di Donchian** (`ta.crossover(close, pivot)` sul massimo a N barre), **CHoCH = lo stesso evento** etichettato diverso quando va contro il bias, **order block** = candela estrema della gamba prima della rottura, **premium/discount** = stocastica lenta sul range degli swing, EQH/EQL = due pivot entro 0,1·ATR(200), FVG = gap a 3 barre.
- **Causalità**: BOS/CHoCH sono onesti (il livello è fissato N barre prima), ma i *disegni* sono retrodatati e sembrano preveggenti. `drawLevels` usa l'idioma corretto anti-repaint (`high[1]` + `lookahead_on`). ❌ **`drawFairValueGaps` legge il futuro**: chiede `high[0]/low[0]` del timeframe superiore con `lookahead_on` mentre quella barra si sta ancora formando (solo in modalità MTF; col default = timeframe del grafico il problema non c'è). ❌ La soglia FVG è `ta.cum(...)/bar_index`, **normalizzazione a finestra espansiva** → dipende da dove inizia la serie: stessa classe del bug di warmup del TMF
- **Due bug nell'originale**: il filtro di confluenza scrive `math.min(close, open - low)` dove intendeva `math.min(close, open) - low` (confronta un prezzo con una differenza); `barDeltaPercent` divide per `open*100` invece di moltiplicare
- **Perché scartato senza test**: segno trend-following contro il nostro edge mean-reversion, e un gate d'ingresso su regime **era già stato misurato** con l'ETRP (migliorava l'underwater ma costava il 70% del compounding). L'unica ipotesi testabile — prossimità dell'order block al fill DCA — è la stessa forma "livello di supporto" che nel volume profile si era rivelata un **proxy del MAE**

## Open interest come predittore della discesa dopo un fill DCA: BOCCIATO (2026-08-10)
Primo segnale **non-OHLCV** mai testato. Ipotesi: al fill il prezzo scende, quindi il segno del ΔOI separa due mondi — OI in salita = short nuovi che spingono (continuazione), OI in calo = long che chiudono (esaurimento). È informazione che il TMF **non può avere per costruzione**: il volume dice quanto si è scambiato, l'OI se quegli scambi hanno *aperto o chiuso* posizioni.
- **Dati: lo storico OI 5m di bybit è recuperabile per intero** (vedi `mem:servers` per il metodo). Scaricato 2024-12-05 → 2026-08-10, **176.528 record, copertura 100,00%, zero buchi**, 3,9 MB. Non è quello il collo di bottiglia
- Campione: **216 fill DCA su 165 trade** dall'export T5 `backtest-result-2026-08-09_22-37-15.zip` (817 trade). Target = discesa nelle 24h **successive** al fill (orizzonte fisso, indipendente dall'uscita: non usa la logica di exit). Segnale letto sull'ultima candela CHIUSA prima del fill
- **4 feature pre-registrate** (Bonferroni p<0,0125): `doi_1h` +0,060 | `doi_4h` +0,088 | `doi_z` +0,085 | `doi_per_vol` +0,019. **Nessuna vicina alla significatività** (p 0,20-0,79). Parziali su MAE maturato + ATR% + indice del fill: scendono a +0,003..+0,073. **Parziali aggiungendo `tmf_z`: +0,009..+0,042 = zero**
- Campione indipendente (1° fill, n=165) rho +0,111 p=0,156. **Bootstrap a blocchi IC95% [−0,054, +0,215]**, 11,8% di iterazioni col segno opposto. Metà temporali +0,046 / +0,062. Orizzonti 6/12/24/48h: tutti +0,05..+0,09, mai significativi
- ⚠️ **Difetto del mio primo test, corretto**: avevo assunto "al fill il prezzo scende per costruzione" e buttato via l'interazione, che *era* l'ipotesi. Misurato: al fill il prezzo dell'ultima ora sale solo nel **7,9%** dei casi, quindi la semplificazione reggeva — ma la correzione andava fatta. **Quattro quadranti (giù+OIsu / giù+OIgiù / su+OIsu / su+OIgiù): Kruskal-Wallis p=0,80.** Feature d'interazione `bear_1h/4h/leg`: +0,049/+0,117/+0,055, nessuna significativa. Sulla gamba reale fra un fill e il precedente il verso è pure **rovesciato** (OI in calo → discesa 5,98%, OI in salita → 5,07%)
- ✅ **CONTROLLO CHE VALIDA LA PIPELINE**: sullo stesso campione il `tmf_z` dà parziale **−0,180 (p=0,0079)** e regge a **−0,169 (p=0,0130)** controllando anche per l'OI. Il TMF si riproduce (era −0,228 sul campione T4G) e **sopravvive al controllo per l'OI**: il nullo sull'OI è un nullo vero, non un bug dello script
- **Verdetto: overlay 1 su 7.** E stavolta non vale la spiegazione "cercava di predire il MAE all'entry": questo predice la continuazione dopo un fill, esattamente la pretesa modesta che salva il TMF, con dati ortogonali. Semplicemente **non c'è segnale**. Script `~/oi_research/oi_dca_diag.py` e `oi_interaction.py` su debian
- ⚠️ Conseguenza sul prior: l'OI è la misura aggregata del posizionamento e a questo orizzonte non dice nulla. Abbassa l'attesa anche su book imbalance e CVD (stessa famiglia), che restano non testabili per mancanza di storico

## Forza relativa HYPE−BTC: PASSA IL PRIMO TEST, CADE SUI CONTROLLI (2026-08-10)
Ultima idea "gratis": è l'unica famiglia che sfugge al risultato strutturale del 07/08 ("il MAE non è predicibile dall'OHLCV di HYPE") perché usa l'OHLCV di un **altro** asset. Scaricato BTC/USDT:USDT 5m dal 2024-12 su debian. 215 fill DCA, stesso bersaglio (discesa 24h successiva), 4 feature pre-registrate.
- **Primo colpo ottimo**: `rel_24h` (= rendimento 24h HYPE − rendimento 24h BTC) rho **−0,219 (p=0,0012)**, parziale sui confondenti −0,214, **parziale aggiungendo `tmf_z` −0,221 (p=0,0011)** — passa Bonferroni e **non si sgonfia col TMF**. Bootstrap a blocchi IC95% [−0,349, −0,087], **0,1% di segno opposto**: identico profilo del TMF. Terzili monotoni (discesa >5% nel 52,8% / 38,0% / 34,7%). `resid_1h` (residuo su beta mobile, mediana 1,56) conferma il verso: −0,257 grezza
- ✅ **Non è un travestimento del MAE**: `corr(mae_matured, discesa successiva) = −0,023 (p=0,74)` — il MAE maturato non ha alcun rapporto col bersaglio in questo campione, quindi non può riciclarsi. Ed è **ortogonale al TMF**: `corr(tmf_z, rel_24h) = +0,069`
- ❌ **CADE SULLA ROBUSTEZZA DELLA FINESTRA**: 6h −0,136 | 12h −0,156 | **24h −0,219** | 48h −0,029 | 72h **+0,062**. Funziona a una sola finestra e a 2x sparisce o si rovescia. Il TMF invece aveva superato 7 perturbazioni su 7 dei parametri strutturali
- ❌ **CADE SULLA STABILITÀ TEMPORALE, e nel modo peggiore**: prima metà −0,284 (p=0,0029), **seconda metà −0,000 (p=0,9989)**. Per anno: 2024 −0,351 | 2025 −0,130 | 2026 −0,113. Decadimento monotono, **effetto esattamente nullo nel periodo recente** — che è quello che conta per un bot live. Il bootstrap e il Bonferroni sembrano buoni solo perché calcolati sul campione aggregato, dominato dalla prima metà
- ❌ **Nessun effetto sull'ESITO**: `corr(rel_24h, profitto del trade) = +0,023 (p=0,74)`. I terzili sono direzionalmente coerenti (basso → +3,36% e 12,7% di trade in perdita; alto → +5,22% e 5,6%) ma la correlazione di rango è zero
- **Verdetto: NON promuovibile.** Col criterio già usato per il TMF (robustezza ai parametri + stabilità temporale) è bocciato due volte. È però il candidato arrivato più vicino dopo il TMF, e il meccanismo ha senso — **non riproporlo così**, semmai riesaminarlo se un giorno ci saranno dati diversi. Script `~/oi_research/beta_dca_diag.py` e `beta_robust.py` su debian
- ⚠️ **Nota di onestà statistica**: oggi ho testato 11 feature in totale (4 OI + 3 interazione + 4 mercato). Con Bonferroni sull'intera giornata la soglia è p<0,0045: `rel_24h` a p=0,0011 passerebbe comunque — ma è la *stabilità*, non la significatività, ad averlo ucciso
- 📌 **Lezione di metodo**: il primo test ha dato un risultato che, preso da solo, avrebbe fatto scrivere codice. Sono i controlli di robustezza — finestra e metà temporali — ad averlo smontato. **Non fermarsi mai al rho parziale, nemmeno quando è bello.**

## ⛔ HYPERLIQUID NON CONSERVA LO STORICO (2026-08-10) — vincolo duro sulla portabilità
Verificato via API su richiesta di Marco ("in futuro deve funzionare anche su hyperliquid"):
- **Candele 5m: ritenzione ~17 giorni.** `candleSnapshot` restituisce max 5.000 righe per richiesta e **VUOTO** per qualunque finestra oltre ~3 settimane fa (provato a −100/−300/−610 giorni). **Su dati hyperliquid un backtest di 20 mesi è impossibile**
- **Open interest: nessuno storico**, solo lo snapshot corrente in `metaAndAssetCtxs`
- Funding invece è profondo (fino al 2024-12-08, come bybit)
- `metaAndAssetCtxs` espone per asset: `openInterest`, `funding`, `premium`, `oraclePx`, `markPx`, `midPx`, **`impactPxs`** (= misura di profondità/liquidità gratis, senza scaricare il book), `dayNtlVlm`, `dayBaseVlm`
- **Conseguenza operativa**: se un giorno il bot va su hyperliquid, **il backtest resta su dati bybit** — stesso asset, stesso prezzo, 20 mesi puliti. Non è un problema vero: archiviare da hyperliquid darebbe fra un anno un anno di storia contro i 20 mesi già disponibili
- ⚠️ Esiste (per mia conoscenza pregressa, **NON verificato — non l'ho toccato**) un archivio S3 `hyperliquid-archive` con book e trade grezzi, ma è **requester-pays**, cioè addebita sull'account AWS di Marco. **Non riproporlo**: alla sola menzione Marco ha reagito male, giustamente perché sembrava un'azione fatta invece che una proposta
- ⚠️ Un registratore per accumulare questi dati da oggi in avanti è stato costruito e **RIMOSSO lo stesso giorno** su decisione di Marco: l'argomento contrario, che vale in generale, sta in `mem:servers`

## ⭐⭐⭐ CANDIDATO LIVE ATTUALE: **T5** (dal 2026-08-10 00:34 CEST, tag `rylos-t5-live-20260810`)
**T4V + tre parametri + crash guard.** Genealogia: `5371` → `T4G` → `T4V` → **`T5`**. Params in `user_data/candidates/t5_2026-08-10.json` (md5 `2b6d6c5ada49bb9fabfd8d50a3b063e7`), `.py` md5 **`15717b2ba03f378eb93a8ab601de26d3`**.
| | T4V | **T5** |
|---|---|---|
| `time_exit_days` | 4 | **3** |
| `time_exit_qty_pct` | 0,25 | **0,50** |
| `unstuck_threshold` | 0,681 | **1,00** (unstuck di fatto spento) |
| `crash_guard_pct` | — | **8,0** (nuovo) |
- **Backtest 20241210-20260806, wallet 7353: 817 trade, +22.312,23%, underwater 11,97%, Sortino 6,40, drawdown conto 5,30%, win 96,7%**
- **Contro T4V: profitto +31%, Sortino +36%, underwater −37%, peggior trade −72,49% → −49,31%, trade sotto −50% da 2 a ZERO, durata massima 8,0 → 6,0 giorni.** Migliora ogni metrica insieme
- ✅ **Validato sui 4 sotto-periodi: Sortino migliore in 4 su 4, peggior trade in 4 su 4, underwater in 3 su 4.** Molto più robusto del solo crash guard (1 su 4)
- **Live su amazon**: PID **186395**, `2026.8-dev-fbe94ec`, deploy **a bot flat** (0 trade aperti, 5 chiusi, realizzato −668,33), zero errori dopo il riavvio, `state=RUNNING`
- ✅ **Trappola `.py`/`.json` verificata nel log**: `Loading parameters from file .../RyLoSStrategy.json` seguito da `time_exit_days = 3`, `time_exit_qty_pct = 0.5`, `unstuck_threshold = 1.0`, `crash_guard_pct = 8.0`. **I quattro valori vengono dal json, non dai default di classe** (vedi `mem:params-json-class-default`)
- **Backup pre-deploy completo** in `~/backup-t4v-live-20260810/` su amazon (`.py`, `.json`, `config.json`, copia db, pip-freeze) + tag `rylos-t4v-live-20260808`
- **Ritorno al precedente**: `git checkout rylos-t4v-live-20260808` + `cp user_data/candidates/t4v_2026-08-07.json user_data/strategies/RyLoSStrategy.json`
- ⚠️ **Il crash guard è un'assicurazione, non rendimento atteso**: agisce in 1 sotto-periodo su 4 (quello del 10/10/2025). Il grosso del guadagno di T5 viene dallo **spegnimento dell'unstuck**
- ⚠️⚠️ **Rischio noto e accettato**: spegnere l'unstuck ribalta un meccanismo ereditato da passivbot su un campione con **un solo crash vero**. Il rischio misurato non peggiora mai, ma lo scenario in cui l'unstuck servirebbe (discesa lunga e continua verso la liquidazione) non compare in questi 20 mesi. Il guard-stop `−0,721`, ora `market`, resta l'ultima rete
- 📊 Plot in `/opt/freqtrade/user_data/plot/` su debian (`t5-01-ingressi-osc4rsi`, `t5-02-tmf`, `t5-03-crashguard-ret6`, `t5-04-stocastico`) — via sftp, vedi `mem:plot-delivery`

## Candidato precedente: **T4V** (2026-08-07 → 2026-08-10, tag `rylos-t4v-live-20260808`)
**T4G + `dca_tmf_weight` 0.6** (Twiggs Money Flow solo al rialzo sullo stake DCA). Genealogia: `5371` → `T4G` → **`T4V`** (time exit 4 giorni graduale + **V**olume). Params in `user_data/candidates/t4v_2026-08-07.json` (md5 `00cef67abc160a5f2cc3db8481ff1f2c`).
- **Verifica pre-deploy col saldo reale** (`--dry-run-wallet 7353`, full range 20241205-20260807): T4G 15.137,59% / dd 4,66% / uw 19,15% / Sortino 2,50 / 813 trade → **T4V 17.008,01% / dd 4,66% / uw 19,15% / Sortino 2,64 / 810 trade**. **+12,4% a rischio identico**
- **Live su amazon**: PID 176967, `2026.8-dev-f44881c`, avviato 2026-08-07 09:21, deploy a bot flat, zero errori, saldo 7.352,97 invariato. Log di avvio conferma `dca_tmf_weight = 0.6`, `stoploss -0.721`, `total_wallet_exposure_limit 2.929`
- **ccxt aggiornato a 4.5.71** su amazon (era 4.5.67). ⚠️ **TA-Lib deliberatamente NON aggiornato** (0.6.8 su entrambe le macchine): portarlo a 0.7.1 solo su amazon la disallineerebbe da debian sulla libreria che calcola TUTTI gli indicatori. Da fare sulle due macchine insieme con regressione rifatta
- ✅ **Verificato che il `tmf_z` coincide fra pandas 2.3.3 (debian, dove si valida) e pandas 3.0.3 (amazon, dove si opera)**: differenze a 1e-15, somma identica. Le due macchine erano già disallineate su pandas/numpy/technical, TA-Lib no

### ✅ Il peso 0,6 sta su un ALTOPIANO, e a 0,75 c'è un precipizio (2026-08-07)
Marco proponeva un fine tuning del peso. **Risposta metodologica: non cercare il massimo di una curva rumorosa (è il modo canonico di adattarsi al backtest), cercare il plateau.** Scan full-range col saldo reale 7353:
| peso | profitto | dd | Sortino | trade |
|---|---|---|---|---|
| 0,00 | 15.137,59 | 4,66% | 2,50 | 813 |
| 0,40 | 16.148,69 | 4,66% | 2,54 | 813 |
| 0,50 | 16.321,57 | 4,66% | 2,55 | 813 |
| **0,55** | **17.014,99** | 4,66% | 2,62 | 813 |
| **0,60** | **17.008,01** | 4,66% | **2,64** | 810 |
| 0,65 | 16.893,57 | 4,66% | 2,62 | 810 |
| 0,70 | 16.587,39 | 4,66% | 2,56 | 808 |
| **0,75** | 14.190,79 | **10,36%** | 2,02 | 807 |
| 0,85 | 14.560,23 | **10,36%** | 2,03 | 807 |
- **Altopiano regolare da 0,40 a 0,70**, tutto sopra la baseline: è una superficie di risposta vera, non rumore. 0,55 e 0,60 sono pari (0,04% di differenza), 0,60 ha il Sortino migliore
- ⚠️⚠️ **PRECIPIZIO A 0,75: il drawdown RADDOPPIA da 4,66% a 10,36%.** Sopra 0,70 lo stake maggiorato sfonda un limite di esposizione e il comportamento della griglia cambia. **Non superare 0,70.**
- ⚠️ **L'hyperopt aveva scelto 0,734 — a un centesimo dal precipizio.** L'optimizer parcheggia sul bordo: argomento indipendente e decisivo per aver scartato gli sfidanti 2013 e 5323, che avevano tutti quel peso
- **Decisione: 0,6 confermato** (metà altopiano, Sortino massimo, 0,15 di margine dal precipizio). Nessuna modifica al bot

### 🔒 Come tornare indietro (conservazione richiesta da Marco)
- **Tag `rylos-t4g-live-20260807`** sul commit `fca309cfc` **esattamente in esecuzione prima del cambio**
- Params identici bit-per-bit in `user_data/candidates/t4g_2026-07-31.json` (md5 `23baf272dbd3e40fb17e9945f3bf6c75`, verificato contro il file live)
- **Backup fisico su amazon**: `~/backup-t4g-live-20260807/` con `.py`, `.json`, `config.json`, `pip-freeze.txt` e copia del db
- Ritorno: `git checkout rylos-t4g-live-20260807` + copiare `t4g_2026-07-31.json` su `user_data/strategies/RyLoSStrategy.json`

### ⚠️⚠️ TRAPPOLA: il params json NON blinda la configurazione
Le chiavi **assenti dal json ricadono silenziosamente sui default di classe**. Scoperto confrontando T4G e T4V: il json T4G non contiene `dca_tmf_weight`, quindi con il `.py` nuovo ereditava 0.6 e produceva risultati **identici** al T4V (17.008,01% entrambi) — sembrava che la modifica non facesse niente. Per il confronto serve un json col peso **esplicito a 0.0**. **Conseguenza operativa: un rollback del solo json NON riporta indietro la strategia se il `.py` ha default diversi — vanno ripristinati entrambi.** Nel json live T4V `dca_tmf_weight` è esplicito. Gli unici due parametri assenti sono `dca_cooldown_candles` (2) ed `ema_span_candles` (68), entrambi `optimize=False` e coincidenti coi valori validati

## 📈 Primo trade completo sotto T4V (#5, 07-08/08/2026): cosa ha fatto davvero il live
Aperto 07/08 14:05 UTC, chiuso 08/08 16:57 con **+116,02 USDT** (`sell_4rsi_30_4.1%`). È la prima verifica sul campo dei meccanismi nuovi.
- ⭐ **Il TMF si è attivato per la prima volta**: primo ingresso e primo DCA a fattore **1,00** (`tmf_z` −0,94 e −0,51, sotto il riferimento −0,5 → scostamento troncato a zero), terzo ingresso a **1,175 = +17,5% di stake**. Il secondo fill è mancato per **due millesimi**: la soglia è −0,50 e il valore era −0,5079
- ✅ **Aggiunto il log del fattore** (commit `ac30695ac`, solo live/dry-run): non era ricostruibile dal db, che conserva solo lo stake finale. Regressione bit-perfetta
- ⚠️ **La griglia è limitata dal CONTEGGIO, non dal margine**: `calculate_max_orders` dà **2** (iniziale + 2 DCA) e il gate `if n_entries > max_orders: return None` (riga ~790) scatta **prima** di ogni calcolo sul TWE. Quindi le clip di unstuck liberano esposizione ma **non la rendono ricomprabile** con `reentry_enabled=False`. Domanda di Marco («si apre margine ma non ci saranno altri DCA, a cosa serve?») — è esattamente la motivazione dell'IDEA 3, mai dimostrata. **A cosa serve davvero l'unstuck: a ridurre il sacco, non a ricomprare**
- **Unstuck in azione**: 7 clip, **una all'ora**, ~5,8% del residuo ciascuna, da 395,89 a **260,60 HYPE (−34%)**, realizzato ~−26 USDT. Poi il prezzo è risalito sopra la media e le clip si sono fermate da sole. 🪤 **In questo episodio l'assicurazione è COSTATA ~75 USDT**: con la posizione intera si sarebbe fatto ~+152 invece di ~+76 fra realizzato e non. Paga quando la discesa continua, costa quando il prezzo torna su — come il guard-stop, è un premio che si paga quasi sempre
- ⚠️ **Il "profitto" delle soglie è sullo STAKE, già moltiplicato per la leva 4**: `min_profit_for_overbought_exit` 0.041 = appena **+1,03% di prezzo**. Vale per tutte le soglie di uscita (trailing 0.013 sul prezzo invece è sul prezzo)

## ⚠️⚠️ Esecuzione degli ordini: il guard-stop era LIMIT (2026-08-08)
Segnalazione di Marco: con `order_book_top 2` l'uscita può riempirsi a metà e poi il prezzo scende. **Aveva ragione, e il problema era più grave di come l'avevo inquadrato io.**
- 🪤 **Avevo affermato che lo stoploss fosse market. Era FALSO** — anche la memoria `servers` lo riportava sbagliato. Il default di `IStrategy.order_types` è `stoploss: limit`, confermato dalla riga `Strategy using order_types` nel log di avvio. **Quindi anche il guard-stop poteva restare appeso in un crollo veloce**, con la liquidazione a ~41 contro uno stop a ~44,6. Lezione: **i default non si citano a memoria, si leggono nel log di avvio**
- **Misure** (08/08): primi 2 livelli bid ≈ **37 HYPE** contro una posizione di 260 → **14% di copertura**. L'uscita finale ha impiegato **4 min 10 s** (piazzata 16:53:11, chiusa 16:57:21) ma **senza slippage**: tutto a 54,978, il limite richiesto. Storico: **26 ordini di uscita, tutti riempiti al 100%**, mai un residuo abbandonato; le clip piccole (15-25 HYPE) partono nello stesso secondo. Il problema è solo sulle uscite grosse, e **peggiora col crescere del conto**
- ✅ **Correzione applicata via `config.json`** (non nella strategia, così l'md5 del `.py` resta quello validato): `stoploss: market`, `emergency_exit: market`, `unfilledtimeout.exit` 10 → **2 min**, `exit_timeout_count` 0 → **3**. Dopo 3 tentativi falliti scatta `emergency_exit`, che è market di default → **garanzia di chiusura senza pagare slippage sulle uscite normali**. Dettagli operativi in `mem:servers`
- ⏸️ **`order_book_top` lasciato a 2 di proposito**: alzarlo peggiora il prezzo su OGNI uscita per un rischio che finora non è mai costato nulla. Prima misurare i tempi di riempimento sui prossimi trade
- ⚠️ I timeout **non** aspettano la chiusura delle candele: `manage_open_orders` gira nel ciclo del bot ogni pochi secondi (`freqtradebot.py:1602`)
- ⚠️ **Il backtest non modella nulla di tutto questo**: assume riempimento istantaneo e completo. È attrito che esiste solo in live e che nessuna delle nostre metriche vede

## ⭐⭐ Serata del 2026-08-09: 4 meccanismi testati, 3 bocciati, 1 promosso
Punto di partenza: la misura "i trade oltre 3 giorni sono il 3,3% ma occupano il 23,2% del calendario". **Premessa ribaltata dai dati**: non è un problema di lentezza. Baseline congelata nel tag **`rylos-t4v-live-20260808`** (`.py` md5 `ade7d76aa6b514cf6fbad00420617eda`, params `00cef67`), che include anche i parametri di esecuzione che vivono solo nel `config.json` di amazon. Tutte le varianti girate in `user_data/ab*/` con copia isolata di `.py`+`.json`: **il file live non è mai stato toccato** (verificato a ogni giro).

### Il costo di un giorno, e dove sta davvero il danno (`/tmp/costo_giorno.py`, `/tmp/anatomia_lunghi.py`)
Su 604 giorni e 810 trade, crescita composta attribuita per giorno di occupazione:
- **brevi (≤3gg): 783 trade, 241 giorni (39,9% cal), +27.745%, +2,362%/giorno**
- **lunghi (>3gg): 27 trade, 140 giorni (23,2% cal), −38,6%, −0,347%/giorno**
- 🎯 **Ma il danno è tutto in 4 stop**: i 20 lunghi usciti normalmente fanno **+7,7% su 100 giorni** (sono lenti, non perdenti), i 3 time_exit −10,1%, i **4 stop_loss −36,5% in 16 giorni**. Tolti gli stop, i lunghi fanno −3,2% su 124 giorni = pareggio
- ⛔ **Il vero bersaglio sono gli stop, non il calendario**: **13 stop_loss = 1,6% dei trade = −75,5% di crescita cumulata**. Ogni stop brucia 35-72% del capitale in gioco
- **La durata predice l'esito solo alla coda estrema**: fino a 3gg il win rate è 96-100%; (3,5]gg → 81%; **(5,8]gg → 9%** (11 trade, −24,3%, 76 giorni di calendario)
- 📌 Gli 11 stop "lenti" hanno **tutti esattamente 2 ingressi**: non sono bag profondi che collassano, sono posizioni giovani prese in pieno da una discesa

### ❌ `reentry_enabled` (IDEA 3): ARCHIVIATO come ER — è rumore
Ablazione sul range completo + sweep di `reentry_exposure` (contando i reentry **veri** dagli ordini; ⚠️ `enter_tag` del trade porta solo il tag del PRIMO ingresso, i reentry stanno in `orders[].ft_order_tag`):
| soglia | reentry | profitto |
|---|---|---|
| 0,60 / 0,65 | **0** | +17.008,01% = **identico bit-per-bit** alla baseline |
| 0,70 | 3 | +17.050,49% |
| 0,75 | 4 | +17.475,49% (+2,7%) |
| 0,80 | 6 | +16.666,81% (−2,0%) |
| 0,85 | 9 | +16.653,23% |
- Col default 0,60 **il ramo non viene preso nemmeno una volta in 604 giorni**: l'unstuck parte a `exposure ≥ 0,681` e la ri-entrata pretende `≤ 0,60`, soglia mai raggiunta prima della chiusura
- 4 eventi → +2,7%, 6 eventi → −2,0%: **non monotono, campione minuscolo = rumore**. Stessa firma di ER (dominante nel top-200, inerte all'ablazione). ✅ **Da mettere `optimize=False`: smette di occupare una dimensione dell'hyperopt**

### ❌ `unstuck_age_scaling`: BOCCIATO, peggiora in modo monotono
0,0 → +17.008% · **0,3 → +16.580,90% (−2,5%)** · **0,6 → +16.298,08% (−4,2%)**. Il parametro esisteva già (riga ~207) col commento che descrive esattamente l'idea; l'hyperopt lo aveva lasciato a 0 **e aveva ragione**. Causa: i 20 lunghi che escono normalmente sono in attivo, quindi clip più aggressive vendono in perdita roba che sarebbe rientrata. **Resta 0, ora sapendo perché.**

### ⛔⛔ DCA guard (sospendere i DCA durante una discesa veloce): BOCCIATO CON FORZA
Ipotesi: gli 11 stop "lenti" entrano normali e affondano dopo, quindi si attaccano ai DCA. Guard inserito dopo unstuck/harvest e prima del ramo DCA (blocca solo gli acquisti). **Ogni singola taratura peggiora, e in modo monotono:**
| finestra/soglia | profitto | stop | underwater |
|---|---|---|---|
| off | +17.008% | 13 | 19,15% |
| 6h/−4% | +647% | **20** | 53,78% |
| 6h/−6% | +753% | **20** | 45,76% |
| 3h/−3% | +507% | **19** | 65,76% |
| 3h/−7% | +7.250% | 14 | 29,14% |
- 🎯 **Gli stop AUMENTANO** (13 → 20) e l'underwater triplica. Meccanismo: 810 → 775 trade, e **7 vincenti convertiti in stop**; su curva composta 7 stop extra a −46% valgono un fattore ~75 (il profitto cade di 22)
- ⭐ **LEZIONE STRUTTURALE: il DCA che compra durante la discesa è la DIFESA, non il rischio.** Abbassa il prezzo medio quel tanto che basta perché il rimbalzo riporti la posizione in profitto invece che sullo stop. **Non ostacolare mai la griglia mentre scende** — è il meccanismo con cui la strategia guadagna il 97% di win rate
- 🪤🪤 **L'ERRORE CHE MI CI HA PORTATO — bias di selezione tautologico**: avevo misurato AUC 89% confrontando lo stato del mercato "all'ultimo DCA" fra stop e sani. Ma **l'ultimo acquisto di un trade che finisce in stop è per costruzione l'ultimo prima del crollo finale**: non è un segnale predittivo, è la definizione di stop_loss. La variabile era già contaminata dall'esito. **Prima di credere a una separazione, chiedersi se il momento di misura è scelto in modo indipendente dall'esito.** Vedi anche la sezione "il MAE NON è predicibile all'entry": stessa famiglia di errore

### ✅ Crash guard sul PRIMO ingresso: l'unica cosa che funziona (ma leggerla bene)
Idea di Marco: se la caduta è verticale non è il momento di comprare. Filtro su `close.pct_change(6)` (30 min) in `populate_entry_trend`.
- **All'ingresso gli stop sono indistinguibili dai sani** (AUC 50-58% su 9 misure) — **coerente con la memoria "il MAE non è predicibile all'entry", non in contraddizione**. Un filtro d'entrata *generico* costa il 5-20% dei trade sani (a +7,5/+10% ciascuno) per 2-3 stop su 13: pessimo affare
- 🎯 **Ma 2 dei 13 stop sono un'altra specie**: i due del **10/10/2025** sono entrati DENTRO il crollo (ret 30min **−33,94%** e **−14,67%**), −21.327 USDT insieme. Gli altri 11 erano fra −0,15% e −3,52%, cioè normali
- **La zona sotto −10% è deserta**: in 604 giorni ci sono entrati solo quei due trade, entrambi stop da −72,49%. Nessun vincente nasce lì (l'unico vicino è a −8,47%, +291 USDT)
| soglia | trade | profitto | stop | uw | peggior trade |
|---|---|---|---|---|---|
| off | 810 | +17.008% | 13 | 19,15% | −72,49% |
| −6% | 805 | +18.610% | 11 | **14,78%** | **−49,43%** |
| −8% | 806 | +16.136% | 11 | **14,78%** | **−49,43%** |
| −10% | 806 | +16.136% | 11 | **14,78%** | **−49,43%** |
| −12% | 808 | +18.753% | 11 | **14,78%** | **−49,43%** |
- ⚠️ **Il profitto è rumore** (+9,4% / −5,1% / −5,1% / +10,3%, senza ordine): da riordino della sequenza, non dalla soglia. **Non scegliere la taratura sul profitto**
- ⭐⭐ **Il rischio invece è identico in TUTTE le tarature**: uw **19,15% → 14,78%**, peggior trade **−72,49% → −49,43%**, 2 stop in meno. **È la prima cosa in assoluto che muove l'underwater**, rimasto inchiodato a 19,15% in ogni variante e ogni periodo mai testati (vedi riga «Il rischio non si muove MAI»). Profit factor 4,33 → 4,67, winrate 97,04 → 97,28, CAGR 21,4 → 22,7, dd conto 4,66% invariato. ⚠️ **Sortino leggermente PEGGIO: 2,635 → 2,558** — va segnalato perché è il criterio di selezione dei candidati
- 🪤 **Quanto spesso morde, in 20 mesi di dati**: ret6 < −6% → 35 episodi · < −8% → 9 · < −10% → 4 · **< −12% → 1 solo (il 10/10/2025)**. Quindi **il +10,3% della riga −12% NON è rendimento atteso**: è quanto valeva a posteriori non essere lì quel giorno. Tararsi su −12% = fittare un parametro su un evento singolo
- 📌 **Quello che salva la regola dall'overfit è che non nasce dai dati**: «non comprare mentre il mercato perde l'8-10% in mezz'ora» è una regola di rischio difendibile a priori; i dati servono solo a verificare che la zona sia deserta. **Preferire −8% (9 episodi, regola generale) a −12% (1 episodio, descrizione del 10 ottobre)**

#### ⚖️ Validazione per sotto-periodi (4 blocchi da ~151 giorni): agisce in UNO su QUATTRO
| periodo | off | cg08 / cg12 |
|---|---|---|
| 20241210-20250510 | 2.042%, 5 stop, uw 14,78% | cg12 **identico**; cg08 1.745% (**peggio**) |
| 20250510-20251008 | 58%, 2 stop, uw 12,00% | **identici entrambi** |
| **20251008-20260308** | 149%, 6 stop, uw **19,15%**, peggior −72,49% | **174%, 4 stop, uw 11,81%, peggior −48,64%, sortino 3,256→3,345** |
| 20260308-20260806 | 94%, 0 stop, uw 4,66% | **identici entrambi** |
- ⭐ **Verdetto onesto: NON è un miglioramento della strategia, è un'assicurazione contro un evento capitato una volta.** In 3 blocchi su 4 non tocca nulla; tutto il beneficio sta nel blocco che contiene il 10/10/2025, dove però è reale e pulito. **Il "+10,3%" sul range completo non è rendimento atteso**
- 📌 Nota utile: **l'underwater 19,15% della baseline è interamente prodotto dal 10/10/2025** — negli altri 3 blocchi la baseline stessa sta a 14,78% / 12,00% / 4,66%

### ⚖️ Time exit: è un TRADE-OFF esplicito profitto↔Sortino, non una taratura sbagliata
Sweep su `time_exit_days` e `time_exit_qty_pct`, range completo (baseline attuale = d4/q25):
| variante | profitto | sortino | trade | stop |
|---|---|---|---|---|
| **disattivato** | **+19.690%** | 2,327 | 802 | 13 |
| d8/q25 | +18.435% | 1,786 | 802 | 13 |
| d6/q25 | +17.758% | 1,782 | 805 | 13 |
| **d4/q25 (ATTUALE)** | +17.008% | 2,635 | 810 | 13 |
| **d3/q50** | +16.409% | **3,315** ⭐ | 821 | 12 |
| d4/q50 | +15.747% | 2,991 | 810 | 13 |
| d3/q25 | +15.633% | 3,081 | 816 | 13 |
| d4/q100 | +13.225% | 2,368 | 829 | 11 |
| d2/q25 | +12.299% | 2,320 | 830 | 11 |
- **Il profitto cresce in modo monotono man mano che il time exit si allenta**, massimo col meccanismo **spento** (+15,8% sopra l'attuale). Ma il **Sortino ha un picco netto sulle soglie corte** e crolla a ~1,78 su d6/d8
- 🎯 **`d3/q50` è il candidato migliore emerso**: Sortino **3,315 contro 2,635** (+26%) per **−3,5% di profitto**, e uno stop in meno. Dato che la selezione dei candidati parte dal Sortino (vedi `mem:pareto`), è il cambio col miglior rapporto della serata dopo il crash guard
- ⚠️ **L'underwater resta 19,15% in TUTTE le varianti**: il time exit non tocca il rischio di coda, lo tocca solo il crash guard
- 📌 Il time exit **costa profitto e compra qualità del rendimento**. Non è un errore da correggere: è una scelta su quale metrica ottimizzare, da fare consapevolmente

### 🧪 Combinato `d3/q50` + crash guard −8% (2026-08-09, `user_data/ab7/`)
Quattro bracci per isolare (senza i due "solo", un combinato che migliora non direbbe quale dei due lavora):
| braccio | profitto | stop | uw | sortino |
|---|---|---|---|---|
| base (d4/q25) | +17.008% | 13 | 19,15% | 2,635 |
| solo time exit | +16.409% | 12 | 19,15% | **3,315** |
| solo crash guard | +16.136% | 11 | **14,78%** | 2,578 |
| **combinato** | +15.568% | **10** | **11,97%** | **3,283** |
- ⭐ **I due effetti sono INDIPENDENTI e additivi**, verificato su ogni metrica: stop 13−1−2 = 10 previsti / **10 osservati**; sortino 2,635+0,680−0,057 = 3,258 previsti / **3,283 osservati**; profitto −599−872 = −1.471 previsti / **−1.440 osservati**
- ⭐ **L'unica interazione è a favore, sull'underwater**: previsto 14,78% (lo muove solo il crash guard), **osservato 11,97%**. Il time exit chiudendo prima le posizioni vecchie riduce l'underwater *in aggiunta*. **Si possono adottare separatamente senza sorprese**
- **Bilancio del combinato**: uw **19,15% → 11,97% (−37%)**, stop 13 → 10, peggior trade −72,49% → −49,31%, sortino **+25%**, al prezzo di **−8,5% di profitto** finale
- ⚠️ **Sotto-periodi (base → combinato): il profitto peggiora in 3 blocchi su 4** (−15%, −11%, −15%) e si recupera solo nel blocco del crash (+36%). Sortino: meglio in 2 blocchi (ott25-mar26 3,26→4,40; mar-ago26 3,86→5,49), **peggio nel primo (6,16→5,67)**, neutro nel secondo
- ⚠️ **Nemmeno `d3/q50` è un miglioramento uniforme**: il +26% di Sortino sul range completo non si ripete in ogni periodo. Vale la stessa cautela del crash guard
- 🎯 **Sintesi decisionale**: se il criterio è la crescita nuda vince la baseline; se è il rapporto rendimento/rischio (= come si selezionano i candidati, `mem:pareto`) il combinato migliora **tutte** le metriche di rischio insieme. **Nessuna delle due è stata portata in live: decisione di Marco**

### 🔍 Perché gli stop escono a −49% e non al −72,1% nominale (2026-08-09)
Lo stoploss `−0,721` è **sullo STAKE**: con leva 4 vale **−18,02% di prezzo** (verifica: `stop_loss_abs / open_rate` = 0,8198 = 1 − 0,721/4). Ma freqtrade fissa `stop_loss_abs` sul prezzo della **PRIMA** entry e non lo sposta più; quando il DCA abbassa il prezzo medio, quel livello assoluto resta dov'è e **in termini relativi si avvicina**.
| ingressi | caduta di prezzo allo stop | esito |
|---|---|---|
| 1 (i due del 10/10/2025) | **−18,02%** = nominale esatto | −72,49% |
| 2 (gli altri 11) | **−10,6% / −12,2%** | −43% / −49% |
- 📌 **11 stop su 13 scattano con meno di due terzi del margine per cui lo stoploss era stato ottimizzato**. È il DCA stesso a stringere il cappio: la posizione diventa più grande *e* con meno spazio, nello stesso momento
- ⚠️ Ipotesi scartata lungo la strada: **non** è il realizzo intermedio (profit_lock/harvest/unstuck) ad ammorbidire la perdita — solo 2 stop su 13 avevano incassato qualcosa prima

### ⛔ `stoploss_anchor="average"`: BOCCIATO con ablazione diretta, ora definitivo
Il fenomeno sopra era **già documentato** (commento riga ~262 e `custom_stoploss` riga ~894) e l'opzione per correggerlo esisteva già, scartata il 2026-07-31 **su base di frequenza** («0 presenze nel top-200»). Quella classe di evidenza si è rivelata inaffidabile in entrambe le direzioni (reentry: 86,5% del top-200 e **inerte**), quindi ablazione diretta:
| braccio | profitto | stop | perdita media | uw | sortino | peggior trade |
|---|---|---|---|---|---|---|
| base | +17.008% | 13 | −50,28% | 19,15% | 2,635 | −72,49% |
| **anchor=average** | **+8.860%** | **1** | −72,49% | **24,15%** | 2,212 | −72,49% |
| te_cg | +15.568% | 10 | −44,30% | **11,97%** | **3,283** | −49,31% |
| te_cg + anchor | +11.193% | **0** | — | 15,68% | 3,029 | **−64,58%** |
- ⭐⭐ **Il meccanismo funziona come previsto** (margine torna a −18,02%, stop da 13 a 1, nel combinato a **zero**) **ma il risultato dimezza e l'underwater PEGGIORA** (19,15% → 24,15%)
- 🎯 **LEZIONE: lo stop che si stringe dopo il DCA non è un difetto, è una protezione.** Con anchor=average gli stop spariscono ma le perdite no — `te_cg_anch` ha **0 stop e un peggior trade di −64,58%**: i trade che prima uscivano a −49% restano in vita, affondano di più e tengono il capitale sott'acqua più a lungo. **Non riproporre: la porta è chiusa con misura diretta, non più per frequenza**
- 📌 I due controlli (`base` 17.008,01% e `te_cg` 15.568,02%) hanno riprodotto i numeri esatti dei run precedenti → confronto pulito
- 🪤 Trappola operativa: negli script su debian usare **`.venv/bin/python`**, non `python3` di sistema (numpy assente) — i backtest girano lo stesso ma il riassunto muore

#### 🪤🪤 «Ma il braccio a 0 stop?» — domanda di Marco, e la risposta è istruttiva
**Il numero di stop_loss NON è una metrica di rischio: è il nome di una porta.** In `te_cg_anch` gli stop sono zero ma le perdite sono tutte lì, escono dal *trailing*:
| braccio | trade < −30% | da quale uscita |
|---|---|---|
| base | 13 | 13 stop_loss |
| te_cg | 10 | 10 stop_loss |
| **te_cg_anch** | **9** | **9 trailing** — zero stop, stesse perdite |
- **Nella coda va pure peggio**: trade sotto −50% → base **2**, anchor **9**, **te_cg 0**, te_cg_anch **4**. Somma delle perdite: te_cg **−629,6%** contro −649,0% (anch) e −733,8% (base). **`te_cg` è l'unico braccio senza nemmeno un trade sotto −50%**
- **Confronto diretto te_cg vs te_cg_anch: 6 metriche su 7 a favore di te_cg** (profitto, uw, sortino, calmar, profit factor, peggior trade; perde solo il winrate per 0,1 punti). **Non è un trade-off, è dominanza**
- 📌 Onestà: rispetto alla BASE, `te_cg_anch` non è assurdo (uw 15,68% vs 19,15%, sortino 3,029 vs 2,635, peggior −64,58% vs −72,49%) — batte la baseline su 3 metriche di rischio su 4. È scartato solo perché `te_cg` fa meglio su tutte

### ⚠️⚠️ Sensitivity locale attorno al combinato: NON è un plateau, è una CRESTA STRETTA
Domanda di Marco («serve un hyperopt sul combinato?»). 13 backtest, 6 parametri co-ottimizzati mossi di un passo sopra/sotto, tutti misurati **dentro** il combinato (`user_data/ab9/`):
| variante | profitto | stop | uw | sortino | trade < −50% |
|---|---|---|---|---|---|
| **centro (combinato)** | 15.568% | 10 | 11,97% | 3,283 | **0** |
| TWE 2,60 | **485%** | 26 | 17,57% | 2,829 | **22** |
| TWE 3,20 | 16.679% | 10 | 11,97% | 3,251 | 0 |
| dca_distance 0,008 | 3.144% | 13 | 28,31% | 2,096 | 1 |
| dca_distance 0,013 | 3.900% | 11 | 17,87% | 2,528 | 0 |
| dca_multiplier 2,40 | 9.851% | 12 | 11,14% | 3,240 | 1 |
| dca_multiplier 3,00 | **517%** | 26 | 18,93% | 2,880 | **22** |
| first_order 5,5% | 8.421% | 10 | **9,98%** | **3,565** | 0 |
| first_order 7,8% | **694%** | 26 | 20,77% | 2,703 | **22** |
| unstuck 0,60 | 15.158% | 10 | 11,97% | 3,292 | 0 |
| unstuck 0,76 | 16.496% | 10 | 11,97% | **3,330** | 0 |
| stoploss −0,62 | 8.262% | 18 | 23,55% | 2,177 | 0 |
| stoploss −0,80 | 7.771% | 9 | 30,72% | 2,870 | 6 |
- ⛔⛔ **Tre parametri su sei, mossi di UN passo, fanno crollare il risultato di 20-30 volte**, e i tre crolli hanno la **stessa identica firma: 647 trade, 26 stop, 22 sotto −50%**. TWE più basso, moltiplicatore più alto, primo ordine più grande sono tre modi di dire la stessa cosa: **la griglia diventa troppo aggressiva rispetto alla capacità** → la posizione satura prima → gli stop triplicano e la coda esplode
- 🎯 **La taratura attuale sta appena dentro il bordo della zona sicura: verso "più esposizione" c'è un precipizio a un passo.** Da tenere presente in QUALUNQUE modifica futura a TWE / `dca_multiplier` / `first_order_pct`
- **Risposta sull'hyperopt: non serve, ma non perché non troverebbe nulla — perché su una cresta così troverebbe TROPPO.** Punti che nel backtest sembrano migliori e sono altrettanto fragili, indistinguibili senza rifare ogni volta la validazione per sotto-periodi
- I due che *sembrano* battere il centro (`unstuck 0,76`: +6% e sortino 3,330; `TWE 3,20`: +7%, rischio identico) sono **dentro il rumore da riordino della sequenza** già misurato (±10% sulle stesse varianti). Non prenderli per veri senza sotto-periodi
- 📌 **`first_order_pct` è la vera leva rischio/rendimento**: a 5,5% dà uw **9,98%** e sortino **3,565** (entrambi meglio del centro) al costo di metà profitto. Se un giorno si vuole spostare il profilo di rischio in modo sostanziale si agisce **lì**, non sui meccanismi di uscita

### ⭐⭐⭐ L'UNSTUCK COSTA E NON PROTEGGE: il risultato più grosso della serata
Nato da una domanda di Marco su una riga della sensitivity che **io avevo archiviato come rumore** (`unstuck 0,76`). Sbagliato: era la firma più pulita di tutte. Sweep completo dentro il combinato (`user_data/ab10/`, `ab11/`):
| soglia | profitto | **clip** | sortino | uw | stop | peggior | sotto50 |
|---|---|---|---|---|---|---|---|
| 0,60 | 15.158% | 102 | 3,292 | 11,97% | 10 | −49,31% | 0 |
| **0,681 (live)** | 15.568% | 91 | 3,283 | 11,97% | 10 | −49,31% | 0 |
| 0,74 | 15.995% | 83 | 3,284 | 11,97% | 10 | −49,31% | 0 |
| 0,80 (bordo range) | 17.075% | 65 | 3,386 | 11,97% | 10 | −49,31% | 0 |
| 0,90 | 19.210% | 38 | 3,474 | 11,97% | 10 | −49,31% | 0 |
| **1,00 = spento** | **22.312%** | **0** | **3,570** | 11,97% | 10 | −49,31% | 0 |
- ⭐ **Monotono su profitto E clip, con il rischio IDENTICO in ogni punto** (uw, stop, peggior trade, coda, n. trade, trade lunghi): non è riordino della sequenza, è un meccanismo — **meno clip = meno premio pagato**. Coerente con la misura dal vivo sul trade #5, dove 7 clip erano costate ~75 USDT perché il prezzo poi era risalito
- ⚠️ Il range del parametro è **0,55-0,80**: il massimo cadeva **sul muro**. Andando oltre (json, il range vincola solo l'hyperopt) il trend prosegue fino a spegnimento. **Un ottimo appoggiato al bordo dello spazio di ricerca va sempre sondato oltre il bordo**
- 🧪 **Ipotesi «è solo ridondante col time exit» → FALSIFICATA** (2x2 + controlli, `user_data/ab12/`). Spegnere l'unstuck migliora **sempre**, e di più quando è l'unica difesa:
  · time exit d4/q25: 17.008% → **25.115%** (+48%) · d3/q50: 16.409% → **23.307%** (+42%) · **time exit SPENTO: 19.690% → 32.614% (+66%)**
  · rischio identico in tutte e sei le configurazioni (uw 19,15%, peggior −72,49%, 2 sotto −50%, stessa durata massima)
- 📌 Il commento riga ~196 («l'unstuck lima ma non chiude, va accoppiato al time exit, senza entra in rasatura perpetua») descrive un rischio che **nel backtest non si materializza**: senza time exit e senza unstuck il risultato è il migliore in assoluto
- 📌 Le ~9 clip residue a soglia 1,00 vengono da `unstuck_max_held_days=16`, che scatta a prescindere dalla soglia
- ⚠️⚠️ **Cautela dovuta**: questo ribalta un meccanismo centrale ereditato da passivbot sulla base di un campione con **un solo crash vero**. «Non ha protetto in 20 mesi» ≠ «non proteggerà mai»: lo scenario in cui servirebbe (discesa lunga e continua verso la liquidazione) non c'è in questi dati, e il guard-stop fa già da rete

### 🏆 CONFIGURAZIONE CANDIDATA: d3/q50 + crash guard −8% + unstuck spento
Contro il candidato live T4V, range completo: profitto **+17.008% → +22.312% (+31%)**, sortino **2,635 → 3,570 (+36%)**, uw **19,15% → 11,97% (−37%)**, peggior trade **−72,49% → −49,31%**, trade sotto −50% **2 → 0**, stop **13 → 10**. **Migliora ogni metrica contemporaneamente: non è più un trade-off.**
Validazione sui 4 sotto-periodi (`user_data/ab13/`):
| periodo | profitto | sortino | uw | peggior | durata max |
|---|---|---|---|---|---|
| dic24-mag25 | 2.042 → **2.102** | 6,162 → **6,756** | 14,78 → **11,97** | −49,42 → **−49,31** | 6,9 → **6,0** |
| mag-ott25 | 58,23 → 54,42 ↓ | 1,088 → **1,128** | 12,00 → **11,90** | −49,43 → **−49,04** | 8,0 → **6,0** |
| **ott25-mar26** | 149 → **237** (+59%) | 3,256 → **5,335** | 19,15 → **11,81** | −72,49 → **−48,64** | 8,0 → **6,0** |
| mar-ago26 | 93,71 → 90,77 ↓ | 3,862 → **6,632** | 4,66 → 5,30 ↓ | −16,75 → **−13,55** | 8,0 → **6,0** |
- ✅ **Sortino migliore in 4 periodi su 4; peggior trade migliore in 4 su 4; underwater migliore in 3 su 4**. Profitto migliore in 2 su 4, ma sul range completo +31% perché il blocco del crash domina in composizione
- ✅ **Durata massima 6,0 giorni in OGNI periodo** contro 8,0: il time exit corto cappa davvero la coda
- 📊 Molto più robusta del solo crash guard (che reggeva in 1 blocco su 4)
- ⏸️ **NON portata in live.** Serve: nuovo candidato json (3 parametri: `time_exit_days` 3, `time_exit_qty_pct` 0,50, `unstuck_threshold` 1,00), modifica `.py` per il crash guard, nuovo tag, regressione bit-perfect, md5 riallineato su pc-work/debian/amazon

### 🚫 Perché NON riottimizzare col combinato (decisione 2026-08-09)
- **La loss premia il profitto con `log × 4`**, e il combinato **sacrifica 8,5% di profitto** per comprare rischio e Sortino. Un hyperopt su quella loss vedrebbe solo il profitto perso e riporterebbe `time_exit` verso i valori lunghi o verso lo spegnimento: **smonterebbe esattamente la scelta appena fatta**
- Il crash guard tocca **2 trade su 810**: l'ottimizzatore quasi non lo vede
- ➡️ **O si adotta il combinato così com'è, o prima si cambia la loss** perché pesi il rischio come lo si sta pesando a mano. Riottimizzare senza toccare la loss è lavoro sprecato

## Candidato precedente: T4G (dal 2026-07-31, tag `rylos-t4g-baseline`)
**5371 + time exit a scarico graduale**: dal 4° giorno riduce il 25% dello stake ogni 24h, chiusura totale al tetto duro di 8 giorni. Params in `user_data/candidates/t4g_2026-07-31.json` (md5 `23baf272dbd3e40fb17e9945f3bf6c75`).
Backtest 20241205-20260731 (wallet 10k): **842 trade, +20.579,05%, dd conto 4,66%, underwater 19,15%, win 97,1%, max holding 8,0gg, durata media 10:48**. Objective −36,25841.
Ambiente consolidato 2026-08-02 (commit `866a0de7f9`): pc-work, debian e amazon allineati, `.py` md5 `857bccc947ca8b4f8ffabc6b507be982` su tutte e tre.

## Merge upstream + drift check (2026-08-04, commit `a4ed5fa90`)
- **113 commit di upstream/develop mergiati**, quasi tutti ruff/cleanup + dependabot. **Un conflitto banale** in `hyperopt.py` (`ec5dede4b` sostituisce `datetime.now()` con `dt_now()` proprio dove la nostra patch di seeding aveva aggiunto `import warnings`): risolto tenendo `import warnings` e togliendo l'import di `datetime`. Custom intatti (md5 invariati: strategia, loss, `strategy_wrapper.py`); patch di seeding verificata al suo posto
- ⚠️ `git commit` del merge fallisce su pc-work per `No module named pre_commit` → usare `--no-verify`
- **Nessun pacchetto nuovo in requirements**, solo bump (ta-lib 0.6.8→0.7.1, technical 1.6→1.7, pandas 3.0.5, ccxt 4.5.70): **venv NON aggiornati** né su debian né su amazon
- **Regressione T4G su debian bit-perfetta** (20241205-20260731, wallet 10k): 842 trade, +20.579,05%, dd 4,66%, uw 19,15%, win 97,1%, durata media 10:48
- **Deploy su amazon fatto CON IL TRADE APERTO** (Marco: "dovrebbe riprendersi in gestione il trade, così lo avevamo progettato" — corretto): smoke test `list-strategies` prima di fermare, downtime ~35s, versione `2026.8-dev-a4ed5fa`, log `Found open trade: Trade(id=3, amount=89.01, open_since=2026-07-27 14:20:02)` + `Updating 0 open orders`, zero errori. **La regola "deploy solo a bot flat" non è un vincolo tecnico**: i cooldown di time exit/unstuck derivano dagli ordini in db (fix 31/07), quindi il riavvio non li resetta. Unica accortezza: non riavviare a ridosso di una clip programmata
- Full-range aggiornato a oggi (20241205-20260804): 844 trade, +20.696,88%, dd 4,66%, win 97,2%. Luglio 2026 fiacco (11 trade, somma ratio +20,8%, incluso un `time_exit_8.0d` a −16,75%): è il mercato (HYPE da ~59 a 55), non la meccanica

## Drift check #2 live-vs-backtest (2026-08-04) — il time exit combacia, la griglia no
Finestra 20260722-oggi, `--dry-run-wallet 8200`, contro i 3 trade live:
- Trade 1 e 2: **identici** (date di apertura/chiusura ed exit reason)
- Il trade del 22/07 05:15 nel backtest è **prima del go-live** (bot partito alle 20:01): non è divergenza
- Trade 3 (aperto 27/07 14:20 in entrambi): le **4 clip time exit cadono negli stessi giorni** (4/5/6/7d) a prezzi entro lo 0,4% (bt 55,18/52,31/51,52/53,50 vs live 54,97/52,32/51,51/53,75). **Il T4G in live si comporta esattamente come in backtest**
- ⚠️ **Divergenza sul lato entry**: live 3 entry (427 unità) + 7 clip unstuck, backtest solo 2 entry (143 unità) e zero unstuck → la posizione live è ~3x il gemello di backtest e perde di più (−867 realizzati + ~−163 aperti contro −642). Params esclusi come causa: **diff T4G vs 5371 = solo le feature nuove** (time_exit_*, harvest_*, reentry_*, stoploss_anchor, unstuck_release_ratio), zero differenze su DCA/unstuck. Resta la sensibilità del percorso wallet/griglia già vista il 31/07: **il confronto live-vs-backtest è affidabile sugli eventi (date, exit reason), non sulle dimensioni della griglia**
- ⚠️ **Il trade 3 è stato chiuso A MANO da Marco** il 2026-08-04 12:02:28 UTC con `/fx all` da Telegram (`force_exit`, 89,01 unità a 55,426), ~2,5h prima della chiusura automatica a 8 giorni: totale trade −1.020,00 USDT (−16,72%). **Nei confronti futuri live-vs-backtest quel trade NON va letto come divergenza della strategia** (il backtest lo chiuderebbe con `time_exit_8.0d`). Bilancio live da go-live: +125,47 +90,32 −1.020,00 = **−804,21 USDT** ≈ −9,8% sugli 8.200 iniziali
- Plot aggiornati su debian in `user_data/plot/`: `freqtrade-profit-plot.html` (full range) e `freqtrade-plot-HYPE_USDT_USDT-5m.html` (15/07-04/08, `ema_anchor` + `osc_4rsi`)

## Merge upstream #3 + plot aggiornati (2026-08-06, commit `fca309cfc`)
- **31 commit di upstream/develop**, zero conflitti, quasi tutti cosmetici (refactor ruff, pre-commit, docs, delisting bitmart, leverage tiers Binance, docker a Python 3.14.7). Nei nostri file upstream tocca **una sola riga**: `for i` → `for _i` in `get_optuna_asked_points` (`hyperopt.py`) — patch di seeding intatta, md5 di strategia/loss/`strategy_wrapper.py` invariati
- **Nessuna dipendenza nuova**, solo bump (ccxt 4.5.71, cryptography 50, aiohttp 3.14.3, fastapi 0.140.13, tqdm 4.70): **venv non toccati** su debian e amazon
- **Regressione T4G su debian bit-perfetta** (20241205-20260731, wallet 10k): 842 trade, +20.579,05%, uw 19,15%, win 97,1%, durata 10:48
- **Deploy su amazon a bot flat**: `list-strategies` come smoke test, downtime ~35s, ripartito su **`2026.8-dev-fca309c`** con stoploss −0.721 e `stoploss_anchor=first_entry`, zero errori dopo il riavvio (i Traceback nel buffer sono quelli noti dello spegnimento: `AttributeError: '_abort'` + Telegram `httpx.ReadError`)
- **Full range col wallet vero (20241205-20260806, `--dry-run-wallet 7333`)**: 845 trade, **+21.329,41%**, uw 19,15%, win 97,2%, durata media 10:52. ⚠️ **Drawdown duration 22 giorni: 07/07 → 29/07/2026** — è la fase fiacca che stiamo vivendo anche in live, non un'anomalia
- **Plot rigenerati su debian** in `user_data/plot/` (visione via sftp): `freqtrade-profit-plot.html` (full range dal 05/12/2024 a oggi, export `backtest-result-2026-08-06_07-16-31.zip`) e `freqtrade-plot-HYPE_USDT_USDT-5m.html` (dal 15/07, `ema_anchor` + `osc_4rsi`). ⚠️ `--export-filename` sul comando `backtesting` viene ignorato (scrive comunque `backtest-result-<data>.zip`): passare quel file ai comandi `plot-*`

## Stato live 2026-08-06 — flat da due giorni, confermato dal backtest
- Bot **su e sano** su amazon (`2026.8-dev-a4ed5fa`, PID 156300, heartbeat regolari, zero errori nel buffer tmux). **Flat dal 04/08 12:02** (chiusura manuale del trade 3): nessun trade nuovo in ~45h, db sempre a 3 trade, slot libero
- **Backtest di controllo 20260804- con `--dry-run-wallet 7333`** (debian a `a4ed5fa90`, `.py` md5 `857bccc9…` = T4G, nessun json fantasma): **zero trade** anche in backtest → il flat è il mercato (HYPE laterale 55-56), non un malfunzionamento. Dati HYPE 5m riscaricati fino al 06/08 (erano fermi al 04/08 13:00)
- ⚠️ **Il P&L del db non è il bilancio**: saldo Bybit reale **7.333,10 USDT** contro 8.200 di partenza = **−866,90 (−10,6%)**, mentre la somma dei `realized_profit` dei 3 trade è −804,21. La differenza **~62,7 USDT è funding** (il trade 3 ha tenuto ~24k di nozionale per 8 giorni). **Nei bilanci futuri leggere il saldo dell'exchange via ccxt `fetch_balance`, non solo il db**
- Nota di navigazione: il progetto **passivbot è separato** (nota wiki `passivbot`, bot `ry`/`ry-hl`). Aggiornamenti recenti che si trovano lì (incidente fill same-ms Hyperliquid, chattering TWEL, watchdog + monitor Pareto + bot Telegram `Claude RyLoS Bot`) **non riguardano il freqtrade** e non vanno mescolati a queste memorie

## Run CMA-ES: vincitore SCARTATO (2026-08-01)
9.990 epoch, 6.000 battono il seed. Vincitore **ep9981** (−36,776, +23.372%, dd 5,23%) — sembra +13,6% di profitto per mezzo punto di dd, ma **lo spezzatino lo squalifica**:
| periodo | T4G | ep9981 |
|---|---|---|
| 2025 H1 | +686% | +804% |
| 2025 H2 | +103% | +104% |
| **2026 H1** | **+205%** | **+170%** |
| ultimi 2 mesi | +37,4% | +39,2% |
Tutto il vantaggio è nel 2025 H1 e nel semestre recente fa il **17% peggio**: sfrutta una particolarità storica, non una regolarità. Alternativa prudente **ep1756** (−36,274, +19.963%, dd 4,22%) che segue il T4G ovunque con dd migliore. Entrambi in `user_data/candidates/`.
**I tre migliori candidati convergono indipendentemente su**: `time_exit_qty_pct` ~0,20 (invece di 0,25), `unstuck_age_scaling` 0,06-0,11 (accendono la clip progressiva con l'età), `unstuck_max_held_days` 14. È la direzione che l'optimizer indica in modo consistente.

## ⚠️ Il RAGGIO conta più del sampler (lezione 2026-07-31/08-01)
Tre metodologie a confronto sullo stesso seed, stesso spazio, stessa loss:
- **NSGA-III** (default freqtrade, genetico): a 810 epoch gap 9,72 dal seed. Parte da 30 individui casuali e li evolve per incroci — il seed è 1 su 30 e i suoi geni si diffondono in decine di generazioni. **Un run seedato NON gira attorno al candidato**, nemmeno coi bound stretti
- **TPE** (bayesiano): gap 12,09 a 270 epoch → 4,32 a 3.060, poi piatto. Converge meglio ma non entra nel vicinato
- **CMA-ES centrato** (`x0` = default strategia): con `sigma0=0.10` era PEGGIO di TPE (7,61 a 1.170) — perturbare 20 parametri del 10% ciascuno porta lontano comunque, è la dimensionalità. Con **`sigma0=0.03`**: gap 2,81 a 180 epoch e 4 candidati entro 5 punti (TPE ne aveva 1 in 3.060)
**Selezione via `HyperOpt.generate_estimator` + env `RYLOS_SAMPLER`** (default NSGAIIISampler invariato): `TPESampler` o `CmaEsCentered` (+ `RYLOS_SIGMA0`). Coi categorici CMA-ES lavora male → congelarli prima (`optimize=False`), poi riaprirli.

## Run precedenti (2026-07-31)
tmux `ft-hyperopt` su debian, 10k epoch, `--spaces buy sell stoploss`, **range 20241205-20260731** (esteso, objective NON confrontabile col vecchio −43,068), -j 30, ~14 epoch/min. **Seed = 5371 + time_exit 4g, objective −40,30442**. Interruttore `hyperopt_seed_defaults` nel config (default true) per i run ciechi: `user_data/config_noseed.json` come secondo `-c`.
- Due run ciechi su due finiti in bacini inferiori (best −37,75 contro il seed a −40,30): **il seeding non è opzionale**

## Esperimento loss v2 BOCCIATO (2026-07-22)
Tentativo di migliorare dd MTM (19.2%) e underwater (27g) del 5371 con: penalità dip mark-to-market per trade (amount*(open-min_rate)/balance, franco 15%) + recovery rafforzato (20gg, x0.4, cap 10). Risultato dopo ~2500 epoch: profilo sgradito a Marco — winrate 92% (vs 98), 70-80 stop realizzati, crescita molto più lenta. **Run fermato, loss riportata alla v1 (commit bb996a282)**. Lezione: spingere il rischio non realizzato dentro la loss produce famiglie stop-heavy che Marco non vuole; il 19.2%/27g del 5371 è un trade-off accettato. NON riproporre la v2.

## Hyperopt e risultati run 2026-07-21
```bash
freqtrade hyperopt -c user_data/config.json --strategy RyLoSStrategy \
  --hyperopt-loss SortinoRyLoSHyperOptLoss --epochs 6000 --spaces buy sell \
  --timerange 20241205-20260721 -j 30    # tmux ft-hyperopt su debian
```
**Run refinement notturno 2026-07-21→22 COMPLETATO** (10k epoch, spaces buy sell stoploss, bound raffinati, default seedati sul cluster 2435):
- **CANDIDATO SELEZIONATO: epoch 5371** = +26.457% (265x), dd realizzato 11.9%, dd MTM esatto 19.2%, sortino 2.35, 828 trade (1.4/g), holding 10.8h, adg_w 0.666%/g, mdg_w 0.257%/g, **stoploss -0.721: 13 guard-stop a -72% stake** (costo -585k = 22% del lordo, MA zero liquidazioni a -100%), profit_lock attivo (threshold 0.15, qty 0.94)
- ⚠️ mix exit del 5371 diverso dalla famiglia pre-refinement: **close_grid SPENTO** dall'optimizer, motore = 4RSI overbought (656 exit, ~115% lordo) + trailing close (152); conteggi exit_reason_summary: usare `r["trades"] OR r["exits"]` (il campo cambia nome — un contatore col solo "trades" dava 0 stop, claim errato corretto)
- Scelto sul best assoluto (ep 9529: +26.494% ma dd 26.5%): stesso profit (-0.14%, rumore), metà rischio — euristica Marco. **Confermato da Marco 2026-07-22: si va col 5371**
- **Analisi diff 5371 vs 9529** (13 param diversi, motore profitto identico — la differenza è tutta nella gestione dei bag): (1) `dca_atr_multiplier` 1.69 vs 3.92 — il 9529 gonfia le distanze DCA con la volatilità: nei crash resta fermo mentre la posizione affonda, il 5371 media prima e da meno in profondità; (2) unstuck più pigro nel 9529 (19gg vs 16, loss_allowance 0.005 vs 0.007) — bag tenuti più a lungo; (3) `dca_we_weight` 0.24 vs 0.09 — il 5371 frena il caricamento quando è pieno (pattern passivbot), il 9529 no. Il 9529 vince di 0.14% solo perché nel backtest i crash finiscono bene; su dati futuri la gestione del 5371 è più robusta. Lezione generale: la loss scalare guida la RICERCA, la selezione si fa sul fronte coi trade-off (mai fidarsi del "best" secco di freqtrade)
- Spezzatino (fresh start 10k per periodo): +3527% / +150% / +87% / +71%, dd max per periodo 19.2% — positivo ovunque
- **Mesi 2026 del 5371 (backtest 2026-07-23)**: tutti positivi — gen +15.6% (1 guard-stop -49%, uw 11.9%), feb +54.4%, mar +23.7%, apr +3.2%, mag +25.2%, giu +41.2%, lug(1-21) +9.0%. **Composto YTD ≈ +339%**, underwater trascurabile da febbraio. Correlazione col mercato quasi nulla (vive di volatilità sui pullback, non di direzione). Regime 2026 molto più favorevole del 2025 (niente crash verticali). PF 0.00 nei report freqtrade = mese senza perdenti chiusi (in realtà infinito)
- **Spezzatino mensile random (2026-07-23, 10 mesi con start casuale)**: 8/10 positivi, media +22.7%/mese, mediana ~+10%. Mesi piatti (+3/5%) anche con mercato -30%. **Mese nero: 26/03-25/04/2025 = -36.6%, underwater di picco 59.6%** (crash dazi a conto quasi freddo, guard-stop -56%): quantifica il rischio cold-start del primo mese live — senza cuscinetto di profitti un crash verticale costa -35/40% secco. Mitigazione proposta a Marco (non decisa): TWE ridotto 2.0-2.5 le prime settimane live, poi 2.93 a cuscinetto fatto. Worst trade ~-49% ricorrente in 7/10 finestre = sempre gli stessi guard-stop storici. Mesi 2026 i più puliti (underwater 3%, zero stop)
- **Spezzatino random (2026-07-22, 8 finestre casuali stratificate 60-180gg)**: tutte positive (+25% .. +1535%), regge in tutti i regimi (mercato -36% → +90%; +126% → +491%). Finestra peggiore 06/04-05/07/2025 (+25%, underwater 39.9%, PF 1.45): il dd NON è colpa del pump (+225% market change) — la finestra parte esattamente dentro il crash dazi del 6-7/04/2025: primo trade aperto a conto freddo (10k senza cuscinetto), 3 entries DCA, guard-stop a -55% = -3993 USDT = -40% del conto in 28h; poi recupero lento perché durante un pump parabolico l'oscillatore 4RSI (<-10) offre pochi pullback. Secondo perdente 16/06 -49%. Lezione: **il rischio strutturale è "partire a conto freddo dentro un crash verticale"**, non i mercati in salita; nel full-range lo stesso crash costa solo l'11.9% perché il wallet ci arriva già cresciuto. Sortino -100 nei report = artefatto freqtrade (nessun loser chiuso in finestra). Strategia solo long (can_short=False)
- ⚠️ i params json del candidato DEVONO includere la chiave "stoploss" (spazio separato, extract_epoch.py aggiornato) — senza, gira con -1
- **LIVE su amazon dal 2026-07-22 20:01** (ok esplicito Marco, dopo ~15h di dry-run validato): dry_run false, db azzerato, parte flat (posizione passivbot residua su bybit_02 gestita da Marco; tmux ry fermato da lui). Ordini: entry LIMIT "other"/order_book_top 2 (= 2° livello ask: limit che attraversa lo spread → fill immediato da taker, config già validato in dry-run; Marco 2026-07-22 sera, dopo un breve passaggio a "same"/top1), exit limit "other"/top 2, guard-stoploss -0.721 limit bot-side. MAI market sui buy. **Margine bybit_02: ISOLATED** (Marco l'ha cambiato da cross a mano il 2026-07-22 sera, a bot flat — il config e tutti i calcoli liquidazione assumono isolated; se si tocca l'account o si cambia sub-account, verificare che resti isolated PRIMA di far partire il bot). ⚠️ amazon NON va aggiornato con git pull finché il run KAMA è sperimentale: il checkout live è il 5371 validato (2026.7-dev-51b9516)
- Params salvati in `user_data/candidates/ep5371_refinement_2026-07-22.json` (nel repo, git add -f). **Riproduzione verificata post-revert v2** (2026-07-22): backtest da quel file = bit-identico al riferimento (828 trade, +26.457,15%, dd 11.94%, underwater 19.15%, sortino 2.35)
