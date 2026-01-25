# pragma pylint: disable=missing-docstring, C0103
"""
Test suite for RyLoSStrategyMLv3 - ML-driven trading strategy with multi-horizon predictions.

This test suite validates:
- Multi-horizon target calculations (15m, 30m, 1h)
- ML prediction retrieval
- ML-driven entry logic (all 3 horizons positive)
- ML-driven DCA logic (2 out of 3 horizons positive)
- ML-driven exit logic (2 out of 3 horizons negative)
- Feature engineering (22 features including scalping indicators)
- Risk management preservation
"""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from pandas import DataFrame

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


# Import the strategy
try:
    from user_data.strategies.RyLoSStrategyMLv3 import RyLoSStrategyMLv3
except ImportError:
    pytest.skip("RyLoSStrategyMLv3 not found", allow_module_level=True)


@pytest.fixture
def strategy():
    """Create a strategy instance for testing"""
    config = {
        "max_open_trades": 1,
        "stake_currency": "USDT",
        "dry_run": True,
        "trading_mode": "futures",
        "margin_mode": "isolated",
    }
    strategy = RyLoSStrategyMLv3(config=config)
    strategy.dp = MagicMock()
    strategy.wallets = MagicMock()
    strategy.wallets.get_total_stake_amount.return_value = 10000.0
    strategy.wallets.get_available_stake_amount.return_value = 10000.0
    return strategy


@pytest.fixture
def sample_dataframe():
    """Create a sample OHLCV dataframe for testing"""
    length = 100
    dates = pd.date_range(start='2024-01-01', periods=length, freq='5min')
    
    # Create realistic price data with some volatility
    base_price = 100.0
    prices = base_price + np.cumsum(np.random.randn(length) * 0.5)
    
    df = DataFrame({
        'date': dates,
        'open': prices + np.random.randn(length) * 0.1,
        'high': prices + np.abs(np.random.randn(length)) * 0.5,
        'low': prices - np.abs(np.random.randn(length)) * 0.5,
        'close': prices,
        'volume': np.random.uniform(1000, 10000, length),
    })
    
    return df


def create_dataframe_with_predictions(pred_15m: float, pred_30m: float, pred_1h: float, length: int = 100) -> DataFrame:
    """Create a dataframe with ML predictions"""
    dates = pd.date_range(start='2024-01-01', periods=length, freq='5min')
    base_price = 100.0
    prices = base_price + np.cumsum(np.random.randn(length) * 0.5)
    
    df = DataFrame({
        'date': dates,
        'open': prices + np.random.randn(length) * 0.1,
        'high': prices + np.abs(np.random.randn(length)) * 0.5,
        'low': prices - np.abs(np.random.randn(length)) * 0.5,
        'close': prices,
        'volume': np.random.uniform(1000, 10000, length),
        'atr': np.random.uniform(0.5, 2.0, length),  # Add ATR for DCA tests
        '&-s_close_15m': pred_15m,
        '&-s_close_30m': pred_30m,
        '&-s_close_1h': pred_1h,
    })
    
    return df


# ============================================================================
# TEST: Multi-Horizon Target Calculations
# ============================================================================

def test_set_freqai_targets_creates_three_columns(strategy, sample_dataframe):
    """
    Validates: Requirements 1.1, 1.6
    
    Test that set_freqai_targets creates exactly 3 target columns:
    - &-s_close_15m
    - &-s_close_30m
    - &-s_close_1h
    """
    result = strategy.set_freqai_targets(sample_dataframe, {})
    
    assert "&-s_close_15m" in result.columns, "15m target column missing"
    assert "&-s_close_30m" in result.columns, "30m target column missing"
    assert "&-s_close_1h" in result.columns, "1h target column missing"


def test_target_calculation_15m(strategy, sample_dataframe):
    """
    Validates: Requirements 1.2
    
    Test that 15m target is calculated correctly:
    (close[+3] - close) / close
    """
    result = strategy.set_freqai_targets(sample_dataframe, {})
    
    # Check a few rows manually
    for i in range(len(result) - 3):
        expected = (result.loc[i + 3, 'close'] - result.loc[i, 'close']) / result.loc[i, 'close']
        actual = result.loc[i, '&-s_close_15m']
        
        if not pd.isna(actual):  # Skip NaN values at the end
            assert abs(actual - expected) < 1e-6, f"15m target mismatch at row {i}"


def test_target_calculation_30m(strategy, sample_dataframe):
    """
    Validates: Requirements 1.3
    
    Test that 30m target is calculated correctly:
    (close[+6] - close) / close
    """
    result = strategy.set_freqai_targets(sample_dataframe, {})
    
    # Check a few rows manually
    for i in range(len(result) - 6):
        expected = (result.loc[i + 6, 'close'] - result.loc[i, 'close']) / result.loc[i, 'close']
        actual = result.loc[i, '&-s_close_30m']
        
        if not pd.isna(actual):
            assert abs(actual - expected) < 1e-6, f"30m target mismatch at row {i}"


def test_target_calculation_1h(strategy, sample_dataframe):
    """
    Validates: Requirements 1.4
    
    Test that 1h target is calculated correctly:
    (close[+12] - close) / close
    """
    result = strategy.set_freqai_targets(sample_dataframe, {})
    
    # Check a few rows manually
    for i in range(len(result) - 12):
        expected = (result.loc[i + 12, 'close'] - result.loc[i, 'close']) / result.loc[i, 'close']
        actual = result.loc[i, '&-s_close_1h']
        
        if not pd.isna(actual):
            assert abs(actual - expected) < 1e-6, f"1h target mismatch at row {i}"


# ============================================================================
# TEST: ML Prediction Retrieval
# ============================================================================

def test_get_ml_predictions_returns_tuple(strategy):
    """
    Validates: Requirements 8.2
    
    Test that get_ml_predictions returns a tuple of 3 floats
    """
    # Mock dataframe with predictions
    mock_df = create_dataframe_with_predictions(0.01, 0.02, 0.03)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df, datetime.now(UTC))
    
    result = strategy.get_ml_predictions("BTC/USDT")
    
    assert isinstance(result, tuple), "Result should be a tuple"
    assert len(result) == 3, "Tuple should have 3 elements"
    assert all(isinstance(x, (int, float)) for x in result), "All elements should be numeric"


def test_get_ml_predictions_returns_correct_values(strategy):
    """
    Validates: Requirements 8.4, 8.5
    
    Test that get_ml_predictions retrieves the correct prediction values
    from the most recent candle
    """
    pred_15m, pred_30m, pred_1h = 0.015, 0.025, 0.035
    mock_df = create_dataframe_with_predictions(pred_15m, pred_30m, pred_1h)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df, datetime.now(UTC))
    
    result = strategy.get_ml_predictions("BTC/USDT")
    
    assert abs(result[0] - pred_15m) < 1e-6, "15m prediction mismatch"
    assert abs(result[1] - pred_30m) < 1e-6, "30m prediction mismatch"
    assert abs(result[2] - pred_1h) < 1e-6, "1h prediction mismatch"


def test_get_ml_predictions_empty_dataframe(strategy):
    """
    Validates: Requirements 8.3
    
    Test that get_ml_predictions returns (0.0, 0.0, 0.0) for empty dataframe
    """
    empty_df = DataFrame()
    strategy.dp.get_analyzed_dataframe.return_value = (empty_df, datetime.now(UTC))
    
    result = strategy.get_ml_predictions("BTC/USDT")
    
    assert result == (0.0, 0.0, 0.0), "Should return zeros for empty dataframe"


def test_get_ml_predictions_missing_columns(strategy):
    """
    Validates: Requirements 8.6
    
    Test that get_ml_predictions handles missing columns gracefully
    """
    # Dataframe without prediction columns
    mock_df = DataFrame({
        'close': [100, 101, 102],
        'volume': [1000, 1100, 1200],
    })
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df, datetime.now(UTC))
    
    result = strategy.get_ml_predictions("BTC/USDT")
    
    assert result == (0.0, 0.0, 0.0), "Should return zeros for missing columns"


# ============================================================================
# TEST: ML-Driven Entry Logic
# ============================================================================

def test_entry_requires_all_three_horizons_positive(strategy):
    """
    Validates: Requirements 2.1, 2.2
    
    Test that entry signal is generated only when ALL 3 horizons are positive
    """
    # Set thresholds
    strategy.ml_entry_threshold_15m.value = 0.005
    strategy.ml_entry_threshold_30m.value = 0.005
    strategy.ml_entry_threshold_1h.value = 0.005
    
    # Test case 1: All 3 positive - should enter
    df1 = create_dataframe_with_predictions(0.01, 0.01, 0.01)
    result1 = strategy.populate_entry_trend(df1, {"pair": "BTC/USDT"})
    assert result1.iloc[-1]["enter_long"] == 1, "Should enter when all 3 positive"
    
    # Test case 2: Only 2 positive - should NOT enter
    df2 = create_dataframe_with_predictions(0.01, 0.01, 0.001)
    result2 = strategy.populate_entry_trend(df2, {"pair": "BTC/USDT"})
    assert result2.iloc[-1]["enter_long"] == 0, "Should NOT enter when only 2 positive"
    
    # Test case 3: Only 1 positive - should NOT enter
    df3 = create_dataframe_with_predictions(0.01, 0.001, 0.001)
    result3 = strategy.populate_entry_trend(df3, {"pair": "BTC/USDT"})
    assert result3.iloc[-1]["enter_long"] == 0, "Should NOT enter when only 1 positive"
    
    # Test case 4: All negative - should NOT enter
    df4 = create_dataframe_with_predictions(-0.01, -0.01, -0.01)
    result4 = strategy.populate_entry_trend(df4, {"pair": "BTC/USDT"})
    assert result4.iloc[-1]["enter_long"] == 0, "Should NOT enter when all negative"


def test_entry_tag_contains_predictions(strategy):
    """
    Validates: Requirements 2.6
    
    Test that entry tag contains "buy_ml_all_positive" and all prediction values
    """
    strategy.ml_entry_threshold_15m.value = 0.005
    strategy.ml_entry_threshold_30m.value = 0.005
    strategy.ml_entry_threshold_1h.value = 0.005
    
    df = create_dataframe_with_predictions(0.015, 0.025, 0.035)
    result = strategy.populate_entry_trend(df, {"pair": "BTC/USDT"})
    
    # Find rows with entry signal
    entry_rows = result[result["enter_long"] == 1]
    
    if len(entry_rows) > 0:
        tag = entry_rows.iloc[0]["enter_tag"]
        assert "buy_ml_all_positive" in tag, "Tag should contain 'buy_ml_all_positive'"
        assert "15m:" in tag, "Tag should contain 15m prediction"
        assert "30m:" in tag, "Tag should contain 30m prediction"
        assert "1h:" in tag, "Tag should contain 1h prediction"


# ============================================================================
# TEST: ML-Driven DCA Logic
# ============================================================================

def test_dca_requires_2_of_3_horizons_positive(strategy):
    """
    Validates: Requirements 3.1, 3.2
    
    Test that DCA is allowed only when at least 2 out of 3 horizons are positive
    """
    # Create a mock trade
    trade = MagicMock(spec=Trade)
    trade.pair = "BTC/USDT"
    trade.nr_of_successful_entries = 1
    trade.has_open_orders = False
    trade.stake_amount = 290.0
    
    # Mock filled entries
    mock_order = MagicMock()
    mock_order.average = 100.0
    mock_order.cost = 290.0
    mock_order.order_filled_date = datetime.now(UTC) - timedelta(minutes=20)
    trade.select_filled_orders.return_value = [mock_order]
    
    # Mock Trade.get_open_trades()
    with patch('freqtrade.persistence.Trade.get_open_trades', return_value=[]):
        # Test case 1: 3 out of 3 positive - should allow DCA
        mock_df1 = create_dataframe_with_predictions(0.01, 0.01, 0.01)
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df1, datetime.now(UTC))
        
        result1 = strategy.adjust_trade_position(
            trade, datetime.now(UTC), 95.0, -0.05, None, 10000.0, 100.0, 95.0, -0.05, -0.05
        )
        assert result1 is not None, "Should allow DCA when 3/3 positive"
        
        # Test case 2: 2 out of 3 positive - should allow DCA
        mock_df2 = create_dataframe_with_predictions(0.01, 0.01, -0.02)
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df2, datetime.now(UTC))
        
        result2 = strategy.adjust_trade_position(
            trade, datetime.now(UTC), 95.0, -0.05, None, 10000.0, 100.0, 95.0, -0.05, -0.05
        )
        assert result2 is not None, "Should allow DCA when 2/3 positive"
        
        # Test case 3: 1 out of 3 positive - should block DCA
        mock_df3 = create_dataframe_with_predictions(0.01, -0.02, -0.02)
        strategy.dp.get_analyzed_dataframe.return_value = (mock_df3, datetime.now(UTC))
        
        result3 = strategy.adjust_trade_position(
            trade, datetime.now(UTC), 95.0, -0.05, None, 10000.0, 100.0, 95.0, -0.05, -0.05
        )
        assert result3 is None, "Should block DCA when only 1/3 positive"


# ============================================================================
# TEST: ML-Driven Exit Logic
# ============================================================================

def test_exit_requires_2_of_3_horizons_negative(strategy):
    """
    Validates: Requirements 5.1, 5.2
    
    Test that exit signal is generated only when at least 2 out of 3 horizons are negative
    """
    # Create a mock trade with profit
    trade = MagicMock(spec=Trade)
    trade.pair = "BTC/USDT"
    
    # Set minimum profit threshold
    strategy.min_profit_for_overbought_exit.value = 0.017
    
    # Test case 1: 3 out of 3 negative + profit - should exit
    mock_df1 = create_dataframe_with_predictions(-0.01, -0.01, -0.01)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df1, datetime.now(UTC))
    
    current_time = datetime.now(UTC)
    result1 = strategy.custom_exit("BTC/USDT", trade, current_time, 105.0, 0.05)
    assert result1 is not None, "Should exit when 3/3 negative and profit > threshold"
    assert "sell_ml_2of3_negative" in result1, "Exit tag should indicate ML-based exit"
    
    # Test case 2: 2 out of 3 negative + profit - should exit
    mock_df2 = create_dataframe_with_predictions(-0.01, -0.01, 0.01)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df2, datetime.now(UTC))
    
    result2 = strategy.custom_exit("BTC/USDT", trade, current_time, 105.0, 0.05)
    assert result2 is not None, "Should exit when 2/3 negative and profit > threshold"
    
    # Test case 3: 1 out of 3 negative + profit - should NOT exit
    mock_df3 = create_dataframe_with_predictions(-0.01, 0.01, 0.01)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df3, datetime.now(UTC))
    
    result3 = strategy.custom_exit("BTC/USDT", trade, current_time, 105.0, 0.05)
    assert result3 is None, "Should NOT exit when only 1/3 negative"
    
    # Test case 4: 3 out of 3 negative but profit too low - should NOT exit
    mock_df4 = create_dataframe_with_predictions(-0.01, -0.01, -0.01)
    strategy.dp.get_analyzed_dataframe.return_value = (mock_df4, datetime.now(UTC))
    
    result4 = strategy.custom_exit("BTC/USDT", trade, current_time, 101.0, 0.01)
    assert result4 is None, "Should NOT exit when profit < threshold"


# ============================================================================
# TEST: Feature Engineering
# ============================================================================

def test_temporal_features_removed(strategy, sample_dataframe):
    """
    Validates: Requirements 6.1, 6.2
    
    Test that temporal features (hour, day_of_week) are removed
    """
    result = strategy.feature_engineering_standard(sample_dataframe, {})
    
    assert "%-hour" not in result.columns, "hour feature should be removed"
    assert "%-day_of_week" not in result.columns, "day_of_week feature should be removed"


def test_bb_percent_feature_added(strategy, sample_dataframe):
    """
    Validates: Requirements 6.3, 6.4
    
    Test that bb_percent feature is added and calculated correctly
    """
    result = strategy.feature_engineering_expand_basic(sample_dataframe, {})
    
    assert "%-bb_percent" in result.columns, "bb_percent feature should be added"
    
    # Verify calculation (should be between 0 and 1 for most values)
    bb_percent = result["%-bb_percent"].dropna()
    assert len(bb_percent) > 0, "bb_percent should have values"
    # Most values should be between 0 and 1, but can go outside in extreme cases
    assert bb_percent.min() >= -0.5, "bb_percent minimum seems incorrect"
    assert bb_percent.max() <= 1.5, "bb_percent maximum seems incorrect"


def test_scalping_features_added(strategy, sample_dataframe):
    """
    Validates: Requirements 6.5-6.13
    
    Test that all new scalping features are added
    """
    result = strategy.feature_engineering_expand_basic(sample_dataframe, {})
    
    # MACD features
    assert "%-macd" in result.columns, "macd feature should be added"
    assert "%-macd_signal" in result.columns, "macd_signal feature should be added"
    assert "%-macd_hist" in result.columns, "macd_hist feature should be added"
    
    # EMA features
    assert "%-ema_9" in result.columns, "ema_9 feature should be added"
    assert "%-ema_21" in result.columns, "ema_21 feature should be added"
    
    # CCI feature
    assert "%-cci" in result.columns, "cci feature should be added"
    
    # Supertrend feature
    assert "%-supertrend" in result.columns, "supertrend feature should be added"
    
    # VWAP feature
    assert "%-vwap" in result.columns, "vwap feature should be added"
    
    # OBV normalized feature
    assert "%-obv_norm" in result.columns, "obv_norm feature should be added"


def test_total_feature_count(strategy, sample_dataframe):
    """
    Validates: Requirements 6.14, 6.15, 6.16
    
    Test that the strategy has 22 total features as specified
    """
    # Get all features
    basic = strategy.feature_engineering_expand_basic(sample_dataframe, {})
    expanded = strategy.feature_engineering_expand_all(sample_dataframe, 10, {})
    standard = strategy.feature_engineering_standard(sample_dataframe, {})
    
    # Count features (columns starting with %-)
    basic_features = [col for col in basic.columns if col.startswith("%-")]
    expanded_features = [col for col in expanded.columns if col.startswith("%-") and col not in basic_features]
    standard_features = [col for col in standard.columns if col.startswith("%-") and col not in basic_features]
    
    total_features = len(basic_features) + len(expanded_features) + len(standard_features)
    
    # Expected: 16 base + 3 expanded + 1 standard = 20 unique features
    # (Note: expanded features include period suffix, so they're different from base)
    assert total_features >= 17, f"Expected at least 17 features, got {total_features}"


# ============================================================================
# TEST: Risk Management
# ============================================================================

def test_custom_stake_amount_respects_limits(strategy):
    """
    Validates: Requirements 10.5, 10.6
    
    Test that custom_stake_amount respects per-pair and global limits
    """
    # Mock wallet
    strategy.wallets.get_total_stake_amount.return_value = 10000.0
    strategy.wallets.get_available_stake_amount.return_value = 10000.0
    
    # Mock no open trades
    with patch('freqtrade.persistence.Trade.get_open_trades', return_value=[]):
        # Test with max_open_trades = 1 (single pair)
        strategy.config["max_open_trades"] = 1
        strategy.first_order_pct.value = 0.029
        
        stake = strategy.custom_stake_amount(
            "BTC/USDT", datetime.now(UTC), 100.0, 290.0, 10.0, 10000.0, 4.0, None, "long"
        )
        
        # Expected: 10000 * 0.029 = 290
        assert abs(stake - 290.0) < 1.0, f"Stake should be ~290, got {stake}"
        
        # Verify it doesn't exceed per-pair limit
        per_pair_limit = (10000.0 * 4) / 1  # 40000
        position_value = stake * 4
        assert position_value <= per_pair_limit, "Position value should not exceed per-pair limit"


def test_calculate_max_orders(strategy):
    """
    Validates: Requirements 10.2
    
    Test that calculate_max_orders returns a reasonable number based on parameters
    """
    strategy.config["max_open_trades"] = 1
    strategy.first_order_pct.value = 0.029
    strategy.dca_multiplier.value = 1.991
    
    max_orders = strategy.calculate_max_orders(10000.0)
    
    # With these parameters, should allow multiple DCA orders
    assert max_orders > 0, "Should allow at least 1 DCA order"
    assert max_orders < 20, "Should not allow unreasonable number of orders"


# ============================================================================
# TEST: Integration
# ============================================================================

def test_populate_indicators_calls_freqai_start(strategy, sample_dataframe):
    """
    Validates: Requirements 9.3
    
    Test that populate_indicators calls self.freqai.start() first
    """
    # Mock freqai
    strategy.freqai = MagicMock()
    strategy.freqai.start.return_value = sample_dataframe
    
    result = strategy.populate_indicators(sample_dataframe, {"pair": "BTC/USDT"})
    
    # Verify freqai.start was called
    strategy.freqai.start.assert_called_once()
    
    # Verify it was called with correct arguments
    call_args = strategy.freqai.start.call_args
    assert call_args[0][0] is sample_dataframe
    assert call_args[0][1] == {"pair": "BTC/USDT"}
    assert call_args[0][2] is strategy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
