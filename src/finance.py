"""Validated tabular financial analysis. All amounts must use a common currency."""
from io import BytesIO
import json
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd

from src.errors import ValidationError

MAX_ROWS = 100_000
MAX_COLUMNS = 100


def normalized_columns(columns):
    if any(pd.isna(column) or not str(column).strip() for column in columns):
        raise ValidationError('Column names must be nonempty.')
    names = [str(column).strip().lower().replace(' ', '_') for column in columns]
    if len(set(names)) != len(names):
        raise ValidationError('Column names must be unique after normalization.')
    return names


def read_table(data: bytes, filename: str) -> pd.DataFrame:
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValidationError('Upload a nonempty CSV or XLSX of at most 20 MB.')
    try:
        if filename.lower().endswith('.csv'):
            headers = pd.read_csv(BytesIO(data), header=None, nrows=1).iloc[0].tolist()
            columns = normalized_columns(headers)
            frame = pd.read_csv(BytesIO(data), nrows=MAX_ROWS + 1)
        elif filename.lower().endswith('.xlsx'):
            # Bound the uncompressed size to reject common spreadsheet zip bombs.
            with ZipFile(BytesIO(data)) as archive:
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValidationError('Spreadsheet uncompressed contents exceed 100 MB.')
            headers = pd.read_excel(BytesIO(data), engine='openpyxl', header=None, nrows=1).iloc[0].tolist()
            columns = normalized_columns(headers)
            frame = pd.read_excel(BytesIO(data), engine='openpyxl', nrows=MAX_ROWS + 1)
        else:
            raise ValidationError('Supported formats are .csv and .xlsx (first sheet only).')
    except ValidationError:
        raise
    except (ValueError, OSError, BadZipFile, UnicodeError, KeyError, IndexError, pd.errors.ParserError):
        raise ValidationError('Table could not be read. Check its format and encoding.') from None
    if frame.empty or len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise ValidationError('Table must have 1–100,000 rows and at most 100 columns.')
    if len(columns) != len(frame.columns):
        raise ValidationError('Each row must match the table header columns.')
    frame.columns = columns
    return frame.dropna(how='all').reset_index(drop=True)


def clean_financials(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy().reset_index(drop=True)
    frame.columns = normalized_columns(frame.columns)
    if frame.empty or not {'revenue', 'expenses'}.issubset(frame.columns):
        raise ValidationError('Financial data needs revenue and expenses columns.')
    numeric = {'revenue', 'expenses', 'net_income', 'assets', 'liabilities', 'equity',
               'current_assets', 'current_liabilities', 'debt', 'cash',
               'interest_expense', 'operating_income'}
    for column in numeric & set(frame.columns):
        # Accept comma grouping, but reject missing/nonnumeric values rather than inventing data.
        frame[column] = pd.to_numeric(frame[column].astype(str).str.replace(',', '', regex=False),
                                      errors='coerce')
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValidationError(f'{column} must contain finite numeric values in every row.')
    if (frame[['revenue', 'expenses']] < 0).any().any():
        raise ValidationError('Revenue and expenses must be nonnegative; net income may be negative.')
    dates = None
    if 'period' in frame:
        periods = frame['period'].astype(str).str.strip()
        parsed = pd.to_datetime(periods, errors='coerce', format='mixed', utc=True)
        if parsed.isna().any() or parsed.duplicated().any():
            raise ValidationError('period must contain distinct valid dates or years.')
        order = parsed.argsort().to_numpy()
        frame = frame.iloc[order]
        dates = pd.DatetimeIndex(parsed.iloc[order])
        frame['period'] = frame['period'].astype(str)
    else:
        frame['period'] = [f'Period {i + 1}' for i in range(len(frame))]
    if 'net_income' not in frame:
        with np.errstate(over='ignore', invalid='ignore'):
            frame['net_income'] = frame['revenue'] - frame['expenses']
    if not np.isfinite(frame['net_income'].to_numpy()).all():
        raise ValidationError('Net income exceeds the supported numeric range.')
    frame['profit_margin'] = safe_ratio(frame['net_income'], frame['revenue'])
    if {'current_assets', 'current_liabilities'}.issubset(frame):
        frame['current_ratio'] = safe_ratio(frame['current_assets'], frame['current_liabilities'])
    if {'debt', 'equity'}.issubset(frame):
        frame['debt_to_equity'] = safe_ratio(frame['debt'], frame['equity'])
    if 'assets' in frame:
        frame['return_on_assets'] = safe_ratio(frame['net_income'], frame['assets'])
    if 'equity' in frame:
        frame['return_on_equity'] = safe_ratio(frame['net_income'], frame['equity'])
    if {'operating_income', 'interest_expense'}.issubset(frame):
        frame['interest_coverage'] = safe_ratio(frame['operating_income'], frame['interest_expense'])
    # A zero or negative prior period makes percentage growth undefined here.
    previous = frame['revenue'].shift(1)
    frame['revenue_growth'] = safe_ratio(frame['revenue'] - previous, previous)
    frame['profit_growth'] = safe_ratio(frame['net_income'] - frame['net_income'].shift(1),
                                        frame['net_income'].shift(1))
    # YoY matches the same reporting date one calendar year earlier, never just the prior row.
    if dates is not None:
        previous_dates = dates - pd.DateOffset(years=1)
        for column, label in [('revenue', 'revenue_yoy_growth'), ('net_income', 'profit_yoy_growth')]:
            by_date = pd.Series(frame[column].to_numpy(), index=dates)
            previous_year = pd.Series(by_date.reindex(previous_dates).to_numpy(), index=frame.index)
            frame[label] = safe_ratio(frame[column] - previous_year, previous_year)
    return frame.reset_index(drop=True)


def safe_ratio(numerator, denominator):
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        return numerator.div(denominator.where(denominator > 0)).replace([np.inf, -np.inf], np.nan)


def financial_summary(frame: pd.DataFrame) -> dict:
    if frame.empty:
        raise ValidationError('Financial data is empty.')
    with np.errstate(over='ignore', invalid='ignore'):
        total_revenue = float(frame.revenue.sum())
        total_profit = float(frame.net_income.sum())
        total_expenses = float(frame.expenses.sum())
    if not all(np.isfinite(v) for v in [total_revenue, total_profit, total_expenses]):
        raise ValidationError('Financial totals exceed the supported numeric range.')
    return {
        'periods': len(frame),
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'total_net_income': total_profit,
        'aggregate_profit_margin': total_profit / total_revenue if total_revenue > 0 else None,
        'net_income_method': 'Uploaded net_income when provided; otherwise revenue minus expenses.',
        'assumptions': 'Common currency; distinct, non-overlapping reporting periods. '
                       'Balance-sheet ratios use period-end values, not averages. '
                       'Undefined ratios and growth are blank, not zero.',
    }


def json_report(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=False).encode('utf-8')


def escape_spreadsheet_text(value):
    if isinstance(value, str) and (value.startswith(('\t', '\r', '\n'))
                                  or value.lstrip().startswith(('=', '+', '-', '@'))):
        return "'" + value
    return value


def csv_report(frame: pd.DataFrame) -> bytes:
    # Headers are untrusted too (for example, uploaded asset names).
    safe = frame.copy()
    safe.columns = [escape_spreadsheet_text(str(column)) for column in safe.columns]
    for column in safe.select_dtypes(include=['object', 'string']).columns:
        safe[column] = safe[column].map(escape_spreadsheet_text)
    return safe.to_csv(index=False).encode('utf-8')
