"""Long-only historical mean/variance optimization with explicit assumptions."""
from dataclasses import asdict, dataclass

import cvxpy as cp
import numpy as np
import pandas as pd

from src.errors import ServiceError, ValidationError


@dataclass(frozen=True)
class PortfolioResult:
    method: str
    weights: dict[str, float]
    annual_return: float
    annual_volatility: float
    sharpe: float | None
    solver_status: str

    def to_dict(self):
        return asdict(self)


def validate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if 'date' in frame:
        dates = pd.to_datetime(frame.pop('date'), errors='coerce')
        if dates.isna().any() or dates.duplicated().any():
            raise ValidationError('Prices need valid, unique dates.')
        frame.index = pd.DatetimeIndex(dates)
        frame = frame.sort_index()
    if not 10 <= len(frame) <= 100_000 or not 2 <= len(frame.columns) <= 50:
        raise ValidationError('Provide 10–100,000 observations for 2–50 assets.')
    if frame.columns.duplicated().any():
        raise ValidationError('Asset names must be unique.')
    try:
        frame = frame.apply(pd.to_numeric, errors='raise').astype(float)
    except (ValueError, TypeError):
        raise ValidationError('All asset prices must be numeric.') from None
    if not np.isfinite(frame.to_numpy()).all() or (frame <= 0).any().any():
        raise ValidationError('Prices must be finite, positive, and have no missing values.')
    return frame


def estimate_moments(prices: pd.DataFrame, periods_per_year: int = 252):
    if not isinstance(periods_per_year, int) or not 1 <= periods_per_year <= 366:
        raise ValidationError('Annualization frequency must be an integer between 1 and 366.')
    prices = validate_prices(prices)
    returns = prices.pct_change(fill_method=None).dropna()
    expected = returns.mean().to_numpy() * periods_per_year
    covariance = returns.cov().to_numpy() * periods_per_year
    if not np.isfinite(expected).all() or not np.isfinite(covariance).all():
        raise ValidationError('Price changes are too large for stable risk estimates.')
    # Symmetrize and floor eigenvalues to handle singular/near-singular samples.
    values, vectors = np.linalg.eigh((covariance + covariance.T) / 2)
    covariance = (vectors * np.maximum(values, 1e-10)) @ vectors.T
    if not np.isfinite(expected).all() or not np.isfinite(covariance).all():
        raise ValidationError('Price changes are too large for stable risk estimates.')
    return prices.columns.tolist(), expected, covariance, returns


def solve(problem: cp.Problem):
    try:
        problem.solve(solver='CLARABEL')
    except cp.error.SolverError:
        try:
            problem.solve(solver='SCS', eps=1e-7, max_iters=20_000)
        except cp.error.SolverError:
            raise ServiceError('Portfolio solver failed. Check the price data.') from None
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
        raise ValidationError(f'Portfolio constraints could not be solved ({problem.status}).')


def optimize(prices, method='min_variance', risk_free_rate=0.0, periods_per_year=252,
             max_weight=1.0) -> PortfolioResult:
    if method not in {'min_variance', 'max_sharpe'}:
        raise ValidationError('Choose min_variance or max_sharpe.')
    if not np.isfinite(risk_free_rate) or not np.isfinite(max_weight):
        raise ValidationError('Risk-free rate and weight limit must be finite.')
    names, expected, covariance, _ = estimate_moments(prices, periods_per_year)
    n = len(names)
    if not 1 / n - 1e-10 <= max_weight <= 1:
        raise ValidationError('Maximum asset weight is infeasible for this number of assets.')
    if method == 'min_variance':
        weights = cp.Variable(n)
        problem = cp.Problem(cp.Minimize(cp.quad_form(weights, cp.psd_wrap(covariance))),
                             [weights >= 0, weights <= max_weight, cp.sum(weights) == 1])
        solve(problem)
        allocation = weights.value
    else:
        excess = expected - risk_free_rate
        if excess.max() <= 0:
            raise ValidationError('No asset has positive estimated excess return. '
                                  'Maximum-Sharpe mode requires a feasible positive excess return.')
        # Let y = w / (excess @ w). Fix excess @ y = 1; minimize variance in y.
        # The cap transforms to y_i <= max_weight * sum(y), preserving convexity.
        y = cp.Variable(n)
        problem = cp.Problem(cp.Minimize(cp.quad_form(y, cp.psd_wrap(covariance))),
                             [y >= 0, excess @ y == 1, y <= max_weight * cp.sum(y)])
        solve(problem)
        allocation = y.value / y.value.sum()
    allocation = np.asarray(allocation).reshape(-1)
    if not np.isfinite(allocation).all() or allocation.min() < -1e-5:
        raise ServiceError('Solver returned invalid portfolio weights.')
    allocation = np.clip(allocation, 0, 1)
    allocation /= allocation.sum()
    if allocation.max() > max_weight + 1e-5:
        raise ServiceError('Solver could not satisfy the allocation limit accurately.')
    annual_return = float(expected @ allocation)
    volatility = float(np.sqrt(allocation @ covariance @ allocation))
    return PortfolioResult(method, dict(zip(names, map(float, allocation))),
                           annual_return, volatility,
                           (annual_return - risk_free_rate) / volatility if volatility > 1e-8 else None,
                           problem.status)


def efficient_frontier(prices, points=20, periods_per_year=252, max_weight=1.0):
    if not 2 <= points <= 100:
        raise ValidationError('Frontier points must be between 2 and 100.')
    names, expected, covariance, _ = estimate_moments(prices, periods_per_year)
    base = optimize(prices, periods_per_year=periods_per_year, max_weight=max_weight)
    # Find the greatest feasible return under the same weight cap.
    w = cp.Variable(len(names))
    constraints = [w >= 0, w <= max_weight, cp.sum(w) == 1]
    maximum = cp.Problem(cp.Maximize(expected @ w), constraints)
    solve(maximum)
    targets = np.linspace(base.annual_return, float(maximum.value), points)
    rows = []
    for target in targets:
        problem = cp.Problem(cp.Minimize(cp.quad_form(w, cp.psd_wrap(covariance))),
                             constraints + [expected @ w >= target - 1e-9])
        solve(problem)
        allocation = np.clip(w.value, 0, 1)
        allocation /= allocation.sum()
        if allocation.max() > max_weight + 1e-5:
            raise ServiceError('Frontier solver could not satisfy the allocation limit.')
        rows.append({'annual_return': float(expected @ allocation),
                     'annual_volatility': float(np.sqrt(allocation @ covariance @ allocation))})
    return pd.DataFrame(rows)


ASSUMPTIONS = (
    'Historical arithmetic mean returns and sample covariance, annualized using the selected '
    'observations per year. Long-only, fully invested, static weights; no leverage, taxes, '
    'transaction costs, slippage, or rebalancing simulation. Use aligned adjusted prices in '
    'a common currency. Covariance eigenvalues are floored at 1e-10 for stability. '
    'Estimates are in-sample, not forecasts or guaranteed performance. Educational use only; '
    'not financial advice.'
)
