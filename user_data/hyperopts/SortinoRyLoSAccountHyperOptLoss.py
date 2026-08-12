"""
SortinoRyLoSAccountHyperOptLoss

Variante di SortinoRyLoSHyperOptLoss con le metriche giornaliere calcolate
sui ritorni di CONTO invece che sulla somma dei profit_ratio per-trade.

Perche' (misura 2026-08-12, ramo rylos-1m):
- `profit_ratio` in freqtrade e' il profitto RELATIVO ALLO STAKE DEL SINGOLO
  TRADE, non al conto. Sommare i profit_ratio di una giornata e chiamarlo
  "rendimento giornaliero" gonfia il numero di un fattore pari all'inverso
  della frazione di wallet impegnata per trade.
  Esempio reale: best epoch 10 del run 1m -> 2261 trade a 1.66% medio, somma
  dei ratio 37.5 contro un rendimento di conto di 2.49 (fattore ~15x).
  adg_bonus valeva cosi' ~12.6 punti su un objective di -23, cioe' il termine
  piu' pesante dopo il profitto, calcolato su una scala sbagliata e ormai
  in zona satura del logaritmo (log1p di numeri grandi = poca sensibilita').
- Il fattore di gonfiaggio dipende da first_order_pct e dal numero di DCA,
  quindi NON e' una costante: distorce il confronto fra configurazioni con
  geometrie di griglia diverse, ed e' inutilizzabile per confrontare
  timeframe diversi (1m vs 5m), che e' esattamente cio' che serve ora.

Cosa cambia rispetto alla versione originale:
1. sortino / adg_w / mdg_w girano su `equity.pct_change()`, con equity =
   starting_balance + cumsum(profit_abs) giornaliero. E' il rendimento vero
   del conto, adimensionale e quindi confrontabile fra timeframe e wallet.
2. Via lo `slippage_per_trade_ratio` fisso di 5bps per trade: era una tassa
   arbitraria che cresce col numero di trade (penalizza il 1m per costruzione).
   I costi reali entrano gia' dal backtest via --fee.
3. Tutto il resto (profit_bonus, frequenza, drawdown, recovery, held, coda,
   durata media) e' identico all'originale, comprese le soglie temporali:
   sono espresse in tempo assoluto e vanno lasciate tali, altrimenti il
   confronto 1m vs 5m non sarebbe piu' alla pari.
"""

import math
from datetime import datetime

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


class SortinoRyLoSAccountHyperOptLoss(IHyperOptLoss):
    """Come SortinoRyLoS, ma sortino/adg/mdg sui ritorni di conto."""

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
            SortinoRyLoSAccountHyperOptLoss._daily_metrics(
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
            - recovery_penalty
            - held_penalty
            - duration_penalty
        )

    @staticmethod
    def _daily_metrics(
        results: DataFrame, min_date: datetime, max_date: datetime, starting_balance: float
    ) -> tuple[float, float, float, float, float]:
        """(sortino cappato, recovery_days_max, adg_w, mdg_w, dd_mean_1pct).

        Tutto sui ritorni di CONTO: equity giornaliera dal cumulato di
        profit_abs, poi variazione percentuale giorno su giorno.
        """
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

        # Rendimento giornaliero VERO del conto (composto, adimensionale)
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
