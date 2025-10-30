"""
CalmarHyperOptLoss

This module defines the alternative HyperOptLoss class which can be used for
Hyperoptimization.
"""

import math
from datetime import datetime

from pandas import DataFrame

from freqtrade.data.metrics import calculate_calmar
from freqtrade.optimize.hyperopt import IHyperOptLoss

class CalmarRyLoSHyperOptLoss(IHyperOptLoss):
    """
    Defines the loss function for hyperopt.

    This implementation uses the Calmar Ratio calculation.
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

        Uses Calmar Ratio with exponential duration penalty.
        Duration penalty: 0 penalty up to 5h, exponential growth per hour after that (no cap).
        """
        calmar_ratio = calculate_calmar(results, min_date, max_date, starting_balance)
        trade_duration = results['trade_duration'].mean()
        
        duration_penalty = CalmarRyLoSHyperOptLoss._calculate_duration_penalty(trade_duration)
        result = -calmar_ratio / (1 + duration_penalty)
        return result
    
    @staticmethod
    def _calculate_duration_penalty(trade_duration_minutes: float) -> float:
        """
        Calculate exponential duration penalty starting from 5 hours.
        
        :param trade_duration_minutes: Average trade duration in minutes
        :return: Duration penalty factor (exponential growth per hour, no cap)
        """
        if trade_duration_minutes <= 300:  # <= 5 hours
            return 0
        
        # Ore oltre le 5
        hours_over_threshold = (trade_duration_minutes - 300) / 60
        return math.exp(hours_over_threshold) - 1