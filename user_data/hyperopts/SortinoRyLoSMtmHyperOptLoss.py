"""
SortinoRyLoSMtmHyperOptLoss

Come SortinoRyLoSAccountHyperOptLoss, piu' il vincolo che conta davvero per
Marco: il drawdown MARK-TO-MARKET, cioe' quanto scende il conto contando anche
le perdite non realizzate delle posizioni aperte.

Perche' serve dentro la loss e non solo in fase di selezione (misura del
2026-08-13/14, run sul periodo intero col tick reale di bybit):
- i candidati che la loss preferiva stavano tutti fra 47,8% e 49,8% di
  mark-to-market, mentre l'unico profilo sotto il 38% trovato (epoch 1051,
  27,62%) la loss lo classificava cinque punti PEGGIO del capolista;
- nessuno dei termini esistenti lo vede: il drawdown di conto guarda solo i
  trade CHIUSI, e una griglia DCA che non realizza le perdite lo tiene basso
  per costruzione. T5 stesso mostra 11,96% sui trade chiusi contro 41,35%
  mark-to-market;
- senza il termine, l'ottimizzatore raffina per ore una famiglia i cui
  vincitori sono inutilizzabili.

Soglia: 30% REALE (Marco: "stare sui 30 come limite sarebbe l'ideale, con
tutto il guadagnabile — 10000 che scendono a 6666 e' gia' duro da sostenere
psicologicamente"). Dentro la loss il valore e' 0.29 perche' il calcolo gira
sulle candele 5m di `processed`, che mostrano meno minimi delle 1m usate
dall'analisi offline: rapporto misurato 0.987-0.989 sui candidati normali,
0.93 nel caso peggiore (T5, dove il crollo del 2024-12-18 tocca dentro la
candela un fondo che il 5m non vede). Sopra la soglia squalifica secca, sotto
una preferenza lineare dolce.

Costo: 0,02-0,03 s per epoch (misurato), irrilevante.
"""

import math
from datetime import datetime

import numpy as np
from pandas import DataFrame, date_range

from freqtrade.data.metrics import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss


SORTINO_CAP = 15.0
SORTINO_WEIGHT = 0.2
PROFIT_SCALE = 4.0
DD_FREE_THRESHOLD = 0.15
DD_SOFT_SCALE = 20.0
MAX_RELATIVE_DRAWDOWN = 0.40
DD_DISQUALIFY_FLAT = 50.0
DD_DISQUALIFY_RAMP = 200.0
DD_1PCT_FREE_THRESHOLD = 0.20
DD_MEAN_1PCT_SCALE = 10.0
DD_ACCOUNT_SCALE = 20.0
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
TRADE_FREQUENCY_REWARD_SCALE = 2.0
N_TRAILING_SLICES = 10
ADG_REWARD_SCALE = 4.0
MDG_REWARD_SCALE = 3.0

# --- drawdown mark-to-market ---
MTM_LIMITE = 0.29          # soglia oltre la quale il candidato e' inaccettabile
MTM_SQUALIFICA_FLAT = 50.0  # piu' di qualsiasi premio raggiungibile
MTM_SQUALIFICA_RAMPA = 200.0
MTM_SCALE = 4.0            # preferenza dolce sotto soglia: fra due ammissibili vince il piu'
                           # tranquillo, ma senza pagarlo troppo in rendimento (10 punti di
                           # mtm = 0.4 di objective, circa il 10% di profitto)


def drawdown_mtm(results: DataFrame, candele: DataFrame, starting_balance: float) -> float:
    """Massimo drawdown dell'equity mark-to-market, ricostruita dai singoli fill.

    Va costruita dai fill e non da size/prezzo medio finali: l'approssimazione
    attribuisce a tutto il trade una posizione che si e' formata poco per volta
    e gonfia gli spike (misurato: +35% sugli spike, +32% sull'underwater).
    La posizione e' una sola alla volta (max_open_trades=1), quindi l'equity e'
    il saldo realizzato piu' il latente della posizione in corso, valutato al
    MINIMO di ogni candela.

    Convenzione di bordo (verificata 2026-08-14 con una seconda implementazione
    indipendente): la candela in cui avviene un fill viene contata con la
    posizione POSTERIORE al fill, ma il segmento che termina su un'uscita
    include la candela dell'uscita stessa con la posizione ancora aperta. E' il
    caso peggiore — dentro quella candela il minimo puo' essere stato toccato
    prima che l'ordine venisse eseguito — e vale fino a mezzo punto percentuale
    (misurato su ep1051: 27,32% contro 26,85% della convenzione ottimista).
    """
    if len(results) == 0 or len(candele) == 0:
        return 0.0

    tempi = candele["date"].values.astype("datetime64[ns]")
    minimi = candele["low"].values

    saldo = starting_balance
    picco = starting_balance
    peggiore = 0.0

    for t in results.sort_values("open_date").itertuples():
        ordini = sorted(t.orders, key=lambda o: o["order_filled_timestamp"] or 0)
        if not ordini:
            saldo += t.profit_abs
            picco = max(picco, saldo)
            continue
        qta = costo = 0.0
        saldo_apertura = saldo
        tappe = [np.datetime64(int(o["order_filled_timestamp"]), "ms").astype("datetime64[ns]")
                 for o in ordini]
        tappe.append(np.datetime64(t.close_date.to_datetime64(), "ns"))
        for k, o in enumerate(ordini):
            if o["ft_is_entry"]:
                qta += o["amount"]
                costo += o["cost"]
            else:
                if qta > 0:
                    quota = min(1.0, o["amount"] / qta)
                    costo -= costo * quota
                    qta = max(qta - o["amount"], 0.0)
            if qta <= 0:
                continue
            i0 = np.searchsorted(tempi, tappe[k], side="left")
            i1 = np.searchsorted(tempi, tappe[k + 1], side="right")
            if i1 <= i0:
                continue
            minimo = minimi[i0:i1].min()
            equity = saldo_apertura + (qta * minimo - costo)
            if picco > 0:
                dd = 1.0 - equity / picco
                if dd > peggiore:
                    peggiore = dd
        saldo = saldo_apertura + t.profit_abs
        picco = max(picco, saldo)

    return max(0.0, peggiore)


class SortinoRyLoSMtmHyperOptLoss(IHyperOptLoss):
    """Loss sui ritorni di conto, con il drawdown mark-to-market come vincolo."""

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
        sortino, recovery_days_max, adg_w, mdg_w, dd_mean_1pct = (
            SortinoRyLoSMtmHyperOptLoss._daily_metrics(
                results, min_date, max_date, starting_balance
            )
        )

        total_profit_ratio = results["profit_abs"].sum() / starting_balance
        profit_bonus = math.log1p(max(0.0, total_profit_ratio)) * PROFIT_SCALE
        adg_bonus = math.log1p(max(0.0, adg_w * 365)) * ADG_REWARD_SCALE
        mdg_bonus = math.log1p(max(0.0, mdg_w * 365)) * MDG_REWARD_SCALE

        backtest_days = max((max_date - min_date).total_seconds() / 86400, 1.0)
        frequency_reward = (
            math.log1p(trade_count / backtest_days) * TRADE_FREQUENCY_REWARD_SCALE
        )

        try:
            max_dd = calculate_max_drawdown(
                results, starting_balance=starting_balance, relative=True
            ).relative_account_drawdown
        except ValueError:
            max_dd = 0.0
        try:
            dd_account = calculate_max_drawdown(
                results, starting_balance=starting_balance, relative=False
            ).relative_account_drawdown
        except ValueError:
            dd_account = 0.0

        dd_penalty = max(0.0, max_dd - DD_FREE_THRESHOLD) * DD_SOFT_SCALE
        dd_penalty += dd_account * DD_ACCOUNT_SCALE
        if max_dd > MAX_RELATIVE_DRAWDOWN:
            dd_penalty += (
                DD_DISQUALIFY_FLAT + (max_dd - MAX_RELATIVE_DRAWDOWN) * DD_DISQUALIFY_RAMP
            )
        dd_penalty += max(0.0, dd_mean_1pct - DD_1PCT_FREE_THRESHOLD) * DD_MEAN_1PCT_SCALE

        # --- il vincolo che conta: quanto scende DAVVERO il conto ---
        mtm = 0.0
        if processed:
            candele = next(iter(processed.values()))
            mtm = drawdown_mtm(results, candele, starting_balance)
        mtm_penalty = mtm * MTM_SCALE
        if mtm > MTM_LIMITE:
            mtm_penalty += MTM_SQUALIFICA_FLAT + (mtm - MTM_LIMITE) * MTM_SQUALIFICA_RAMPA

        recovery_penalty = math.log1p(recovery_days_max) * RECOVERY_LOG_SCALE
        recovery_penalty += (
            max(0.0, recovery_days_max - MAX_RECOVERY_DAYS) * RECOVERY_GUARDRAIL_SCALE
        )
        recovery_penalty = min(recovery_penalty, RECOVERY_PENALTY_CAP)

        max_held_days = results["trade_duration"].max() / (60 * 24)
        held_penalty = math.log1p(max_held_days) * HELD_DAYS_PENALTY_SCALE
        held_penalty += (
            max(0.0, max_held_days - MAX_POSITION_HELD_DAYS) * HELD_DAYS_GUARDRAIL_SCALE
        )

        durations_h = results["trade_duration"] / 60
        total_hours = float(durations_h.sum())
        tail_hours = float((durations_h - TAIL_DAYS_THRESHOLD * 24).clip(lower=0.0).sum())
        tail_share = tail_hours / total_hours if total_hours > 0 else 0.0
        held_penalty += tail_share * TAIL_HOURS_SHARE_SCALE
        held_penalty = min(held_penalty, HELD_PENALTY_CAP)

        avg_duration_hours = results["trade_duration"].mean() / 60
        duration_penalty = (
            math.log1p(max(0.0, avg_duration_hours - MAX_AVG_DURATION_HOURS))
            * DURATION_PENALTY_SCALE
        )

        return -(
            sortino * SORTINO_WEIGHT
            + profit_bonus
            + adg_bonus
            + mdg_bonus
            + frequency_reward
            - dd_penalty
            - mtm_penalty
            - recovery_penalty
            - held_penalty
            - duration_penalty
        )

    @staticmethod
    def _daily_metrics(
        results: DataFrame, min_date: datetime, max_date: datetime, starting_balance: float
    ) -> tuple[float, float, float, float, float]:
        """(sortino cappato, recovery_days_max, adg_w, mdg_w, dd_mean_1pct) di CONTO."""
        t_index = date_range(start=min_date, end=max_date, freq="1D", normalize=True)
        sum_daily = (
            results.resample("1D", on="close_date")
            .agg({"profit_abs": "sum"})
            .reindex(t_index)
            .fillna(0)
        )

        equity = starting_balance + sum_daily["profit_abs"].cumsum()
        peak = equity.cummax()
        underwater = equity < peak
        groups = (~underwater).cumsum()
        recovery_days_max = (
            float(underwater.groupby(groups).sum().max()) if underwater.any() else 0.0
        )

        daily_dd = ((peak - equity) / peak).clip(lower=0.0)
        n_worst = max(1, int(len(daily_dd) * 0.01))
        dd_mean_1pct = float(daily_dd.nlargest(n_worst).mean())

        prev = equity.shift(1)
        prev.iloc[0] = starting_balance
        daily_ret = (equity / prev - 1.0).fillna(0.0)

        n_days = len(daily_ret)
        adg_slices = []
        mdg_slices = []
        for k in range(1, N_TRAILING_SLICES + 1):
            tail = daily_ret.iloc[n_days - max(1, n_days // k) :]
            adg_slices.append(tail.mean())
            mdg_slices.append(tail.median())
        adg_w = sum(adg_slices) / len(adg_slices)
        mdg_w = sum(mdg_slices) / len(mdg_slices)

        expected_returns_mean = daily_ret.mean()
        downside = daily_ret.copy()
        downside[downside > 0] = 0.0
        down_stdev = math.sqrt((downside**2).sum() / len(downside))

        if down_stdev == 0:
            sortino = SORTINO_CAP if expected_returns_mean > 0 else -20.0
        else:
            sortino = min(expected_returns_mean / down_stdev * math.sqrt(365), SORTINO_CAP)
        return sortino, recovery_days_max, adg_w, mdg_w, dd_mean_1pct
