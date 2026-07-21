"""
SortinoRyLoSHyperOptLoss

Sortino-based loss function mirroring the passivbot eq8 scoring set
(top config dd39 for HYPE): growth + sortino as reward, and the same
risk axes passivbot minimizes — drawdown, equity recovery days,
position held days — as continuous penalties.

Design notes (from passivbot optimizer research on grid/DCA strategies):
- On DCA strategies that close almost only in profit, realized-PnL Sortino is
  degenerate: downside deviation tends to 0 and the ratio explodes. The ratio
  is capped and a log profit bonus acts as tie-breaker inside the cap.
- passivbot scoring objectives mapped here:
  adg -> profit bonus | sortino_ratio -> capped sortino
  drawdown_worst -> guardrail penalty (>45%)
  strategy_eq_recovery_days_max -> continuous log penalty (limit 12d in
  passivbot) | position_held_days_max -> continuous log penalty + hard
  guardrail >20d
- Trade frequency reward (log trades/day) biases toward scalping: more
  trades, shorter durations.
"""

import math
from datetime import datetime

from pandas import DataFrame, date_range

from freqtrade.data.metrics import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss


# Rebalanced 2026-07-21: profit-first entro rischio accettato.
# Il profitto totale è l'asse dominante (log * 4: 10x ~ 9.6 punti,
# 100x ~ 18.5); il Sortino resta come termine di qualità (peso 0.5).
SORTINO_CAP = 15.0
SORTINO_WEIGHT = 0.5
PROFIT_SCALE = 4.0
# Drawdown: gratis fino al 30% (accettato), morbido 30-40%, SQUALIFICA
# oltre 40% — "un dd max oltre 40% non lo selezionero' mai, anche se ha
# valori ottimi": penalità flat 50 punti (> di qualsiasi score raggiungibile,
# che al massimo vale ~28) + rampa, così nessun profitto può comprarla.
DD_FREE_THRESHOLD = 0.30
DD_SOFT_SCALE = 20.0
MAX_RELATIVE_DRAWDOWN = 0.40
DD_DISQUALIFY_FLAT = 50.0
DD_DISQUALIFY_RAMP = 200.0
DD_1PCT_FREE_THRESHOLD = 0.20
DD_MEAN_1PCT_SCALE = 10.0
# Recovery (equity REALIZZATA: si muove a gradini di trade chiusi, quindi
# soglie più larghe del limit 12gg mark-to-market di passivbot)
RECOVERY_LOG_SCALE = 0.3
MAX_RECOVERY_DAYS = 30.0
RECOVERY_GUARDRAIL_SCALE = 0.1
# Anti-bag
MAX_POSITION_HELD_DAYS = 20.0
HELD_DAYS_PENALTY_SCALE = 0.6
HELD_DAYS_GUARDRAIL_SCALE = 0.2
# Scalping: reward frequenza rafforzato + penalità durata media oltre 5h
MAX_AVG_DURATION_HOURS = 5.0
DURATION_PENALTY_SCALE = 0.5
# Continuous risk axes (passivbot scoring: recovery_days_max, held_days_max)
TRADE_FREQUENCY_REWARD_SCALE = 1.5
# Growth axes (passivbot adg_w / mdg_w): recency-weighted mean and median
# daily gain over 10 trailing slices (full, last 1/2, ... last 1/10).
# mdg is the anti-staircase axis: a flat-then-jump equity has high mean but
# ~zero median, and none of the other terms catches it.
N_TRAILING_SLICES = 10
MDG_REWARD_SCALE = 1.0


class SortinoRyLoSHyperOptLoss(IHyperOptLoss):
    """
    Defines the loss function for hyperopt.

    Capped daily Sortino + log profit bonus + trade frequency reward,
    minus penalties on drawdown, equity recovery time and position
    holding time (passivbot eq8 scoring mapped to a single scalar).
    """

    @staticmethod
    def hyperopt_loss_function(
        *,
        results: DataFrame,
        trade_count: int,
        min_date: datetime,
        max_date: datetime,
        starting_balance: float,
        **kwargs,
    ) -> float:
        sortino, recovery_days_max, adg_w, mdg_w, dd_mean_1pct = (
            SortinoRyLoSHyperOptLoss._daily_metrics(
                results, min_date, max_date, starting_balance
            )
        )

        # Profitto totale = asse dominante (obiettivo: config stile 100x)
        total_profit_ratio = results["profit_abs"].sum() / starting_balance
        profit_bonus = math.log1p(max(0.0, total_profit_ratio)) * PROFIT_SCALE
        # Recency e costanza (adg_w / mdg_w passivbot, pesi minori)
        adg_bonus = math.log1p(max(0.0, adg_w * 365))
        mdg_bonus = math.log1p(max(0.0, mdg_w * 365)) * MDG_REWARD_SCALE

        # Scalping bias: più trade al giorno
        backtest_days = max((max_date - min_date).total_seconds() / 86400, 1.0)
        frequency_reward = (
            math.log1p(trade_count / backtest_days) * TRADE_FREQUENCY_REWARD_SCALE
        )

        # Drawdown guardrail (passivbot limit: drawdown_worst > 0.45)
        try:
            drawdown = calculate_max_drawdown(
                results, starting_balance=starting_balance, relative=True
            )
            max_dd = drawdown.relative_account_drawdown
        except ValueError:
            max_dd = 0.0
        # Gratis fino al 30%, morbida 30-40%, squalifica oltre 40%
        dd_penalty = max(0.0, max_dd - DD_FREE_THRESHOLD) * DD_SOFT_SCALE
        if max_dd > MAX_RELATIVE_DRAWDOWN:
            dd_penalty += DD_DISQUALIFY_FLAT + (max_dd - MAX_RELATIVE_DRAWDOWN) * DD_DISQUALIFY_RAMP
        dd_penalty += max(0.0, dd_mean_1pct - DD_1PCT_FREE_THRESHOLD) * DD_MEAN_1PCT_SCALE

        # passivbot: strategy_eq_recovery_days_max (min) — tempo sott'acqua
        recovery_penalty = math.log1p(recovery_days_max) * RECOVERY_LOG_SCALE
        recovery_penalty += (
            max(0.0, recovery_days_max - MAX_RECOVERY_DAYS) * RECOVERY_GUARDRAIL_SCALE
        )

        # passivbot: position_held_days_max (min) — continua + guardrail >20gg
        max_held_days = results["trade_duration"].max() / (60 * 24)
        held_penalty = math.log1p(max_held_days) * HELD_DAYS_PENALTY_SCALE
        held_penalty += (
            max(0.0, max_held_days - MAX_POSITION_HELD_DAYS) * HELD_DAYS_GUARDRAIL_SCALE
        )

        # Penalità durata media oltre 5h (scalping)
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
            - recovery_penalty
            - held_penalty
            - duration_penalty
        )

    @staticmethod
    def _daily_metrics(
        results: DataFrame, min_date: datetime, max_date: datetime, starting_balance: float
    ) -> tuple[float, float, float, float, float]:
        """(sortino cappato, recovery_days_max, adg_w, mdg_w, dd_mean_1pct) giornalieri"""
        resample_freq = "1D"
        slippage_per_trade_ratio = 0.0005
        days_in_year = 365
        minimum_acceptable_return = 0.0

        results.loc[:, "profit_ratio_after_slippage"] = (
            results["profit_ratio"] - slippage_per_trade_ratio
        )

        t_index = date_range(start=min_date, end=max_date, freq=resample_freq, normalize=True)
        sum_daily = (
            results.resample(resample_freq, on="close_date")
            .agg({"profit_ratio_after_slippage": "sum", "profit_abs": "sum"})
            .reindex(t_index)
            .fillna(0)
        )

        # recovery_days_max: streak massimo di giorni consecutivi sotto il picco
        equity = starting_balance + sum_daily["profit_abs"].cumsum()
        peak = equity.cummax()
        underwater = equity < peak
        groups = (~underwater).cumsum()
        recovery_days_max = (
            float(underwater.groupby(groups).sum().max()) if underwater.any() else 0.0
        )

        # dd_mean_1pct (passivbot drawdown_worst_mean_1pct): media del peggior
        # 1% dei drawdown giornalieri relativi — coda mediata, robusta a spike
        daily_dd = ((peak - equity) / peak).clip(lower=0.0)
        n_worst = max(1, int(len(daily_dd) * 0.01))
        dd_mean_1pct = float(daily_dd.nlargest(n_worst).mean())

        total_profit = sum_daily["profit_ratio_after_slippage"] - minimum_acceptable_return
        expected_returns_mean = total_profit.mean()

        # adg_w / mdg_w (passivbot): media/mediana giornaliera su 10 slice
        # trailing (intero periodo, ultima 1/2, 1/3, ... 1/10) → pesa il recente
        n_days = len(total_profit)
        adg_slices = []
        mdg_slices = []
        for k in range(1, N_TRAILING_SLICES + 1):
            tail = total_profit.iloc[n_days - max(1, n_days // k):]
            adg_slices.append(tail.mean())
            mdg_slices.append(tail.median())
        adg_w = sum(adg_slices) / len(adg_slices)
        mdg_w = sum(mdg_slices) / len(mdg_slices)

        downside = total_profit.copy()
        downside[downside > 0] = 0.0
        down_stdev = math.sqrt((downside**2).sum() / len(downside))

        if down_stdev == 0:
            # All-wins: premia la crescita ma mai oltre il cap
            sortino = SORTINO_CAP if expected_returns_mean > 0 else -20.0
        else:
            sortino = min(
                expected_returns_mean / down_stdev * math.sqrt(days_in_year), SORTINO_CAP
            )
        return sortino, recovery_days_max, adg_w, mdg_w, dd_mean_1pct
