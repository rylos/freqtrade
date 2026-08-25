"""
BudgetRyLoSHyperOptLoss

Come RobustRyLoSHyperOptLoss, ma il drawdown mark-to-market e' trattato come un
VINCOLO invece che come un obiettivo.

⭐ Indicazione di Marco del 2026-08-25: «mi interessa il DD vero, mark to market
fino al 30% accettabile e con rendimento alto. Se fa 10 di DD vero e 100 di
profitto preferisco un 25 di DD vero con molto piu' profitto». Cioe' il 30% e'
un BUDGET da spendere, non un male da minimizzare.

La loss robusta faceva il contrario, con due termini che punivano il drawdown
anche molto sotto il tetto:
  - `mtm * 1.5`, penalita' lineare sul picco
  - `quota_profonda * 4.0`, penalita' su ogni frazione di tempo oltre il -10%
Il secondo pesava di piu' ed era il piu' sbagliato: per una strategia a cui si
concede il 30%, stare fra il 10 e il 25% sotto il picco e' funzionamento
normale, non un difetto.

Tre cambi:
1. Sparisce la penalita' lineare sul picco. Sotto il tetto tutti i drawdown
   valgono uguale: 12% e 27% sono entrambi dentro il budget.
2. La soglia del "tempo profondo" sale dal 10% al 25%, e resta solo per evitare
   che una configurazione VIVA appena sotto la squalifica.
3. Il profitto torna a peso pieno (4.0, era 2.0 nella variante robusta).

Restano invariati: la squalifica secca sopra il 29%, il segmento peggiore con
peso 14, e la punizione dei segmenti con mediana negativa — la regolarita' della
crescita resta un obiettivo, e' solo il drawdown a smettere di esserlo.
"""

import math
from datetime import datetime

import numpy as np
from pandas import DataFrame, DatetimeIndex, Series

from freqtrade.optimize.hyperopt import IHyperOptLoss


SORTINO_CAP = 15.0
SORTINO_WEIGHT = 0.2
# Tornato a peso pieno: con il drawdown declassato a vincolo, e' il profitto a
# dover decidere fra due candidati entrambi dentro il budget.
PROFIT_SCALE = 4.0
# Crescita: mdg pesa il DOPPIO di adg. E' l'asse anti-scalinata, e alzato a 4
# non bastava: nella rifinitura il rapporto mdg/adg scendeva da 0,55 a 0,33
# mentre l'objective migliorava, cioe' la ricerca comprava rendimento con la
# regolarita' della curva. Riferimento sano di passivbot: 0,64
ADG_REWARD_SCALE = 4.0
MDG_REWARD_SCALE = 8.0
# Il segmento peggiore e' ora il termine dominante: vale piu' della media.
MDG_PEGGIORE_SCALE = 14.0
# Penalita' per ogni segmento con mediana giornaliera negativa, piu' una
# squalifica se sono troppi: un periodo in cui la strategia PERDE non e'
# equivalente a un periodo piatto, ed e' esattamente cio' che il fuori campione
# ci ha mostrato (fold A: -11,6% su cinque mesi).
SEGMENTO_NEGATIVO_SCALE = 25.0
MAX_SEGMENTI_NEGATIVI = 2
SQUALIFICA_SEGMENTI = 60.0
N_SLICES = 10
TRADE_FREQUENCY_REWARD_SCALE = 2.0
# Drawdown REALE (mark-to-market)
MTM_LIMITE = 0.29
MTM_SQUALIFICA_FLAT = 50.0
MTM_SQUALIFICA_RAMPA = 200.0
MTM_SCALE = 0.0  # azzerata: sotto il tetto il drawdown non e' piu' un costo
                  # chi scende meno, altrimenti la ricerca scivola su profili
                  # troppo calmi che rendono un ottavo (misurato: ep862, 23,6%
                  # di drawdown reale e +1.499% contro +12.117% del seme)
# Tempo passato in profondita': non basta il massimo, conta quanto ci si resta
TEMPO_SOTTO_SOGLIA = 0.25
TEMPO_SCALE = 2.0
# Recupero e durate (invariati, sono in tempo assoluto)
RECOVERY_LOG_SCALE = 0.3
MAX_RECOVERY_DAYS = 15.0
RECOVERY_GUARDRAIL_SCALE = 0.1
RECOVERY_PENALTY_CAP = 8.0
HELD_PENALTY_CAP = 4.0
MAX_POSITION_HELD_DAYS = 6.0
HELD_DAYS_PENALTY_SCALE = 0.6
HELD_DAYS_GUARDRAIL_SCALE = 0.05
TAIL_DAYS_THRESHOLD = 3.0
TAIL_HOURS_SHARE_SCALE = 2.0
MAX_AVG_DURATION_HOURS = 5.0
DURATION_PENALTY_SCALE = 1.0


def serie_mtm(results: DataFrame, candele: DataFrame, starting_balance: float):
    """Equity mark-to-market ricostruita dai singoli fill.

    Va costruita dai fill e non da size e prezzo medio finali: l'approssimazione
    attribuisce a tutto il trade una posizione che si e' formata poco per volta
    e gonfia gli spike (misurato: +35%). Una posizione alla volta
    (max_open_trades=1), quindi equity = saldo realizzato + latente della
    posizione in corso, valutata al MINIMO di ogni candela.

    Convenzione di bordo (verificata con una seconda implementazione): la
    candela in cui avviene l'uscita e' contata con la posizione ancora aperta.
    E' il caso peggiore — il minimo puo' essere stato toccato prima del fill —
    e vale fino a mezzo punto percentuale.
    """
    if len(results) == 0 or len(candele) == 0:
        return Series(dtype="float64"), starting_balance

    tempi = candele["date"].values.astype("datetime64[ns]")
    minimi = candele["low"].values

    istanti: list = []
    valori: list = []
    saldo = starting_balance

    for t in results.sort_values("open_date").itertuples():
        ordini = sorted(t.orders, key=lambda o: o["order_filled_timestamp"] or 0)
        if not ordini:
            saldo += t.profit_abs
            continue
        qta = costo = 0.0
        saldo_apertura = saldo
        tappe = [
            np.datetime64(int(o["order_filled_timestamp"]), "ms").astype("datetime64[ns]")
            for o in ordini
        ]
        tappe.append(np.datetime64(t.close_date.to_datetime64(), "ns"))
        for k, o in enumerate(ordini):
            if o["ft_is_entry"]:
                qta += o["amount"]
                costo += o["cost"]
            else:
                if qta > 0:
                    costo -= costo * min(1.0, o["amount"] / qta)
                    qta = max(qta - o["amount"], 0.0)
            if qta <= 0:
                continue
            i0 = np.searchsorted(tempi, tappe[k], side="left")
            i1 = np.searchsorted(tempi, tappe[k + 1], side="right")
            if i1 <= i0:
                continue
            istanti.append(tempi[i0:i1])
            valori.append(saldo_apertura + (qta * minimi[i0:i1] - costo))
        saldo = saldo_apertura + t.profit_abs
        istanti.append(np.array([np.datetime64(t.close_date.to_datetime64(), "ns")]))
        valori.append(np.array([saldo]))

    if not istanti:
        return Series(dtype="float64"), saldo
    s = Series(np.concatenate(valori), index=DatetimeIndex(np.concatenate(istanti)))
    return s.sort_index(), saldo


class BudgetRyLoSHyperOptLoss(IHyperOptLoss):
    """Metriche sull'equity reale, vincolo sul drawdown reale, premio alla linearita'."""

    @staticmethod
    def hyperopt_loss_function(
        *,
        results: DataFrame,
        trade_count: int,
        min_date: datetime,
        max_date: datetime,
        starting_balance: float,
        processed: dict[str, DataFrame] | None = None,
        **kwargs,
    ) -> float:
        candele = next(iter(processed.values())) if processed else DataFrame()
        equity, finale = serie_mtm(results, candele, starting_balance)
        if len(equity) < 10:
            return 1000.0

        # --- drawdown reale ---
        dd = (1 - equity / equity.cummax()).clip(lower=0)
        mtm = float(dd.max())
        quota_profonda = float((dd > TEMPO_SOTTO_SOGLIA).mean())

        mtm_penalty = mtm * MTM_SCALE + quota_profonda * TEMPO_SCALE
        if mtm > MTM_LIMITE:
            mtm_penalty += MTM_SQUALIFICA_FLAT + (mtm - MTM_LIMITE) * MTM_SQUALIFICA_RAMPA

        # --- serie giornaliera dell'equity reale ---
        giorni = equity.resample("1D").last().ffill()
        rend = giorni.pct_change().fillna(0.0)

        n = len(giorni)
        # adg_w: code annidate alla passivbot — pesa il recente
        adg_w = sum(rend.iloc[n - max(1, n // k) :].mean() for k in range(1, N_SLICES + 1)) / N_SLICES
        # mdg_w: SEGMENTI DISGIUNTI, ogni periodo con peso pieno. Il mercato
        # cambia regime, e quel che si vuole non e' una curva dritta sul totale
        # ma che OGNI periodo dia il suo contributo: con le code annidate un
        # periodo debole all'inizio sparisce sotto il peso di quelli recenti.
        taglio = max(1, n // N_SLICES)
        mediane = [
            rend.iloc[i * taglio : (i + 1) * taglio].median()
            for i in range(N_SLICES)
            if len(rend.iloc[i * taglio : (i + 1) * taglio]) > 0
        ]
        mdg_w = sum(mediane) / len(mediane) if mediane else 0.0
        mdg_peggiore = min(mediane) if mediane else 0.0
        # Quanto e quanti segmenti stanno sotto zero. Somma delle profondita',
        # non solo conteggio: un segmento a -0.5%/g e' peggio di uno a -0.01%/g.
        negativi = [m for m in mediane if m < 0]
        penalita_negativi = sum(abs(m) * 365 for m in negativi) * SEGMENTO_NEGATIVO_SCALE
        if len(negativi) > MAX_SEGMENTI_NEGATIVI:
            penalita_negativi += SQUALIFICA_SEGMENTI * (len(negativi) - MAX_SEGMENTI_NEGATIVI)

        # --- crescita ---
        total_profit_ratio = (finale - starting_balance) / starting_balance
        profit_bonus = math.log1p(max(0.0, total_profit_ratio)) * PROFIT_SCALE
        adg_bonus = math.log1p(max(0.0, adg_w * 365)) * ADG_REWARD_SCALE
        mdg_bonus = math.log1p(max(0.0, mdg_w * 365)) * MDG_REWARD_SCALE
        # il periodo peggiore conta: un segmento piatto o negativo pesa qui
        mdg_bonus += math.log1p(max(0.0, mdg_peggiore * 365)) * MDG_PEGGIORE_SCALE

        backtest_days = max((max_date - min_date).total_seconds() / 86400, 1.0)
        frequency_reward = (
            math.log1p(trade_count / backtest_days) * TRADE_FREQUENCY_REWARD_SCALE
        )

        # --- tempo di recupero, sull'equity reale ---
        picco = giorni.cummax()
        sotto = giorni < picco
        gruppi = (~sotto).cumsum()
        recovery_days_max = float(sotto.groupby(gruppi).sum().max()) if sotto.any() else 0.0
        recovery_penalty = math.log1p(recovery_days_max) * RECOVERY_LOG_SCALE
        recovery_penalty += (
            max(0.0, recovery_days_max - MAX_RECOVERY_DAYS) * RECOVERY_GUARDRAIL_SCALE
        )
        recovery_penalty = min(recovery_penalty, RECOVERY_PENALTY_CAP)

        # --- Sortino sui ritorni reali ---
        giu = rend.copy()
        giu[giu > 0] = 0.0
        down = math.sqrt(float((giu**2).sum()) / len(giu))
        if down == 0:
            sortino = SORTINO_CAP if rend.mean() > 0 else -20.0
        else:
            sortino = min(float(rend.mean()) / down * math.sqrt(365), SORTINO_CAP)

        # --- durate ---
        max_held_days = results["trade_duration"].max() / (60 * 24)
        held_penalty = math.log1p(max_held_days) * HELD_DAYS_PENALTY_SCALE
        held_penalty += (
            max(0.0, max_held_days - MAX_POSITION_HELD_DAYS) * HELD_DAYS_GUARDRAIL_SCALE
        )
        durate_h = results["trade_duration"] / 60
        ore = float(durate_h.sum())
        coda_ore = float((durate_h - TAIL_DAYS_THRESHOLD * 24).clip(lower=0.0).sum())
        held_penalty += (coda_ore / ore if ore > 0 else 0.0) * TAIL_HOURS_SHARE_SCALE
        held_penalty = min(held_penalty, HELD_PENALTY_CAP)

        durata_media_h = results["trade_duration"].mean() / 60
        duration_penalty = (
            math.log1p(max(0.0, durata_media_h - MAX_AVG_DURATION_HOURS))
            * DURATION_PENALTY_SCALE
        )

        return -(
            sortino * SORTINO_WEIGHT
            + profit_bonus
            + adg_bonus
            + mdg_bonus
            + frequency_reward
            - mtm_penalty
            - penalita_negativi
            - recovery_penalty
            - held_penalty
            - duration_penalty
        )
