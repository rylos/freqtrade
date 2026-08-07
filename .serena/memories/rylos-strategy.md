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

## ⭐ CANDIDATO LIVE: T4G (dal 2026-07-31, tag `rylos-t4g-baseline`)
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
