# Progetto RyLoS Classic (passivbot-style)

Strategia di trading crypto su Freqtrade: long-only su HYPE/USDT:USDT futures Bybit (user `bybit_02`), 5m, leva 4x isolata, 1 posizione.

**Dal 2026-07-21 esiste solo la strategia Classic.** MLv3, RL e FreqAI sono dismessi (preservati nel branch `develop-old` su github.com/rylos/freqtrade).

## Architettura segnale + meccaniche passivbot

- **Entry**: oscillatore 4RSI di RyLoS (istogramma continuo `avg(RSI2,RSI7,RSI14)-50` + filtro stoch %K) + candela rossa + ancora EMA (`initial_ema_dist`, span ~340min)
- **DCA**: trailing entry passivbot (discesa oltre distanza dinamica + rimbalzo confermato dal minimo); distanza adattiva ad ATR ed esposizione (`dca_we_weight`); stake progressivo (`dca_multiplier`); Emergency DCA a -12.4%
- **Exit (4 vie)**: close grid a clip parziali (markup, max 2 clip poi chiude tutto, disattivabile via hyperopt) → trailing close threshold+retracement → 4RSI overbought → unstuck (clip 5% su rimbalzi EMA per posizioni stuck, cooldown 1h)
- **Rischio**: `total_wallet_exposure_limit` hyperoptabile 2-3 (disaccoppiato dalla leva), stoploss disabilitato (-1)
- 27 parametri hyperopt (14 buy + 13 sell)

## Stato (2026-07-22 mattina)

Refinement notturno 10k epoch COMPLETATO (spaces buy sell stoploss, bound raffinati). **Candidato: epoch 5371 = +26.457% (265x), dd 11.9% realizzato / 19.2% underwater, 0 liquidazioni (guard-stoploss -0.721), sortino 2.35, 828 trade**. Backtest ufficiale: CAGR 3023%, p-value 1.6e-14, 1 solo mese negativo su 20, dd duration 5g22h. Supera passivbot dd39 (100x) di 2.6x. In dry-run su amazon (tmux ft, wallet 8200) dal 22/07 — go-live su ok esplicito di Marco. Dettagli: `mem:rylos-strategy`.

## Ottimizzazione

- Loss: `SortinoRyLoSHyperOptLoss` (vedi `mem:rylos-strategy`) — profit-first entro vincoli, mappa lo scoring passivbot eq8
- Riferimento: config passivbot dd39 (`/opt/passivbot/backtests/combined/2026-07-20T11_47_30_dd39/config.json` su debian, NON toccare) — fa >100x con dd 39%
- Target: gain ≥30x, dd max ≤30% (mai >40%), più trade possibile con durata media <5h
- Selezione candidato: euristica Pareto di Marco (filtro dd, poi adg_w/mdg_w massimi, Sortino sacrificabile)
