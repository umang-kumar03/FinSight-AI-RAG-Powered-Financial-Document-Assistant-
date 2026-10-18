import numpy as np
import pandas as pd
import pytest

from src.errors import ValidationError
from src.finance import read_table
from src.portfolio import efficient_frontier, estimate_moments, optimize, validate_prices


@pytest.fixture
def prices(samples):
    return read_table((samples / 'prices.csv').read_bytes(), 'prices.csv')


@pytest.mark.parametrize('method', ['min_variance', 'max_sharpe'])
def test_feasible_portfolios(prices, method):
    result = optimize(prices, method, risk_free_rate=0.02, max_weight=0.6)
    assert sum(result.weights.values()) == pytest.approx(1)
    assert min(result.weights.values()) >= 0
    assert max(result.weights.values()) <= 0.60001
    assert result.annual_volatility > 0
    assert result.sharpe == pytest.approx((result.annual_return - 0.02) / result.annual_volatility)


def test_min_variance_equal_variance_independent_assets():
    # Explicit deterministic return series with zero cross-covariance and equal variance.
    returns = np.tile([[.01, .01], [.01, -.01], [-.01, .01], [-.01, -.01]], (30, 1))
    prices = pd.DataFrame(np.vstack([np.ones(2), np.cumprod(1 + returns, axis=0)]), columns=['a', 'b'])
    result = optimize(prices)
    assert result.weights['a'] == pytest.approx(.5, abs=1e-4)


def test_max_sharpe_matches_brute_force_two_assets(prices):
    prices = prices[['alpha', 'beta']]
    result = optimize(prices, 'max_sharpe', 0.02)
    _, mean, cov, _ = estimate_moments(prices)
    grid = np.linspace(0, 1, 10001)
    weights = np.column_stack([grid, 1 - grid])
    ratios = (weights @ mean - .02) / np.sqrt(np.einsum('ij,jk,ik->i', weights, cov, weights))
    assert result.sharpe >= ratios.max() - 1e-5


def test_min_variance_no_worse_than_equal_weight(prices):
    result = optimize(prices)
    _, _, cov, _ = estimate_moments(prices)
    w = np.ones(3) / 3
    assert result.annual_volatility <= np.sqrt(w @ cov @ w) + 1e-6


def test_frontier_feasible_and_monotonic(prices):
    frontier = efficient_frontier(prices, points=8, max_weight=.7)
    assert len(frontier) == 8
    assert np.isfinite(frontier.to_numpy()).all()
    assert np.diff(frontier.annual_return).min() >= -1e-6
    assert np.diff(frontier.annual_volatility).min() >= -1e-5


@pytest.mark.parametrize('change', ['zero', 'nan', 'text', 'short', 'one_asset', 'duplicate_date'])
def test_invalid_prices(prices, change):
    if change == 'zero': prices.loc[0, 'alpha'] = 0
    if change == 'nan': prices.loc[0, 'alpha'] = np.nan
    if change == 'text': prices['alpha'] = 'bad'
    if change == 'short': prices = prices.head(5)
    if change == 'one_asset': prices = prices[['date', 'alpha']]
    if change == 'duplicate_date': prices.loc[1, 'date'] = prices.loc[0, 'date']
    with pytest.raises(ValidationError):
        validate_prices(prices)


def test_bad_parameters(prices):
    with pytest.raises(ValidationError): optimize(prices, 'unknown')
    with pytest.raises(ValidationError): optimize(prices, max_weight=.2)
    with pytest.raises(ValidationError): optimize(prices, risk_free_rate=float('nan'))
    with pytest.raises(ValidationError): estimate_moments(prices, 0)
    with pytest.raises(ValidationError): efficient_frontier(prices, 1)
    with pytest.raises(ValidationError): optimize(prices, 'max_sharpe', risk_free_rate=10)


def test_singular_covariance():
    prices = pd.DataFrame({'a': np.linspace(100, 110, 30), 'b': np.linspace(100, 110, 30)})
    result = optimize(prices)
    assert np.isfinite(result.annual_volatility)
