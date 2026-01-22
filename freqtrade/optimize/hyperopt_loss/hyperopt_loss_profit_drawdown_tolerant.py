"""
ProfitDrawdownTolerantHyperOptLoss

Loss function che massimizza profit con penalità drawdown solo sopra 30%
"""

from datetime import datetime

from pandas import DataFrame

from freqtrade.data.metrics import calculate_max_drawdown
from freqtrade.optimize.hyperopt import IHyperOptLoss


class ProfitDrawdownTolerantHyperOptLoss(IHyperOptLoss):
    """
    Defines the loss function for hyperopt.

    Massimizza profit totale con penalità drawdown solo se supera 30%
    """

    @staticmethod
    def hyperopt_loss_function(
        results: DataFrame,
        min_date: datetime,
        max_date: datetime,
        starting_balance: float,
        *args,
        **kwargs,
    ) -> float:
        """
        Objective function, returns smaller number for more optimal results.

        Massimizza profit con penalità drawdown solo sopra 30%
        """
        total_profit = results["profit_abs"].sum()
        
        # Calcola max drawdown
        try:
            drawdown = calculate_max_drawdown(
                results, starting_balance=starting_balance, value_col="profit_abs"
            )
            max_drawdown_pct = drawdown.relative_account_drawdown
        except (ValueError, TypeError):
            max_drawdown_pct = 0

        # Penalità drawdown progressiva
        if max_drawdown_pct > 0.40:
            # Penalità aggressiva oltre 40%
            # Formula: penalità base (30-40%) + penalità extra (oltre 40%)
            base_penalty = 0.10 * total_profit * 2  # 30-40%: penalty fissa
            excess_over_40 = max_drawdown_pct - 0.40
            extra_penalty = excess_over_40 * total_profit * 4  # 4x oltre 40%
            penalty = base_penalty + extra_penalty
        elif max_drawdown_pct > 0.30:
            # Penalità moderata tra 30-40%
            # Es: 35% DD → penalty = 0.05 * profit * 2 = 10% del profit
            drawdown_excess = max_drawdown_pct - 0.30
            penalty = drawdown_excess * total_profit * 2
        else:
            penalty = 0

        # Risultato: massimizza profit, penalizza drawdown > 30%
        result = -total_profit + penalty

        return result
