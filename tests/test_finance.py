import numpy as np
import pandas as pd
import pytest

from src.errors import ValidationError
from src.finance import clean_financials, csv_report, financial_summary, json_report, read_table


@pytest.mark.parametrize('name', ['financials.csv', 'financials.xlsx'])
def test_financial_sample(samples, name):
    data = clean_financials(read_table((samples / name).read_bytes(), name))
    summary = financial_summary(data)
    assert summary['total_revenue'] == 3700
    assert summary['total_net_income'] == 1200
    assert data.loc[1, 'revenue_growth'] == pytest.approx(0.2)
    assert data.loc[2, 'profit_margin'] == pytest.approx(1 / 3)
    assert data.loc[0, 'current_ratio'] == 2
    assert data.loc[0, 'debt_to_equity'] == 0.5
    assert data.loc[0, 'return_on_assets'] == 0.15
    assert json_report(summary).startswith(b'{')


def test_derives_profit_and_sorts_periods():
    data = clean_financials(pd.DataFrame({'period': ['2025', '2024'],
                                          'revenue': ['1,200', '1000'], 'expenses': [800, 700]}))
    assert data.net_income.tolist() == [300, 400]
    assert data.revenue_growth.iloc[1] == pytest.approx(0.2)


def test_zero_denominators_and_negative_profit_growth():
    data = clean_financials(pd.DataFrame({'revenue': [0, 100], 'expenses': [20, 70],
                                          'current_assets': [1, 2], 'current_liabilities': [0, 1],
                                          'debt': [1, 2], 'equity': [-1, 2]}))
    assert pd.isna(data.profit_margin.iloc[0])
    assert pd.isna(data.revenue_growth.iloc[1])
    assert pd.isna(data.profit_growth.iloc[1])
    assert pd.isna(data.current_ratio.iloc[0])
    assert pd.isna(data.debt_to_equity.iloc[0])


@pytest.mark.parametrize('frame', [pd.DataFrame(), pd.DataFrame({'revenue': [1]}),
    pd.DataFrame({'revenue': ['bad'], 'expenses': [1]}),
    pd.DataFrame({'revenue': [np.inf], 'expenses': [1]}),
    pd.DataFrame({'revenue': [-1], 'expenses': [1]}),
    pd.DataFrame({'period': ['2024', '2024'], 'revenue': [1, 2], 'expenses': [0, 1]})])
def test_bad_financial_data(frame):
    with pytest.raises(ValidationError):
        clean_financials(frame)


@pytest.mark.parametrize('data,name', [(b'', 'x.csv'), (b'bad', 'x.pdf'), (b'not a zip', 'x.xlsx')])
def test_bad_tables(data, name):
    with pytest.raises(ValidationError):
        read_table(data, name)


def test_csv_formula_neutralization():
    output = csv_report(pd.DataFrame({'label': ['=HYPERLINK("bad")', '@SUM(A1)', 'safe'],
                                      'value': [-2, 1, 3]})).decode()
    assert "'=" in output and "'@" in output
    assert '-2' in output


def test_json_rejects_nan():
    with pytest.raises(ValueError):
        json_report({'bad': float('nan')})


def test_interest_coverage_and_missing_revenue_margin():
    data = clean_financials(pd.DataFrame({'revenue': [100], 'expenses': [80],
                                          'operating_income': [30], 'interest_expense': [10]}))
    assert data.interest_coverage.iloc[0] == 3
    zero = clean_financials(pd.DataFrame({'revenue': [0], 'expenses': [0]}))
    assert financial_summary(zero)['aggregate_profit_margin'] is None


def test_column_normalization():
    frame = read_table(b'Revenue,Expenses\n100,50\n', 'x.csv')
    assert frame.columns.tolist() == ['revenue', 'expenses']
    with pytest.raises(ValidationError, match='unique'):
        read_table(b'Revenue, revenue\n1,2\n', 'x.csv')


@pytest.mark.parametrize('kind', ['csv', 'xlsx'])
def test_exact_duplicate_headers_rejected(kind):
    from io import BytesIO
    if kind == 'csv':
        data = b'revenue,revenue,expenses\n100,200,50\n'
    else:
        buffer = BytesIO()
        pd.DataFrame([[100, 200, 50]], columns=['revenue', 'revenue', 'expenses']).to_excel(buffer, index=False)
        data = buffer.getvalue()
    with pytest.raises(ValidationError, match='unique'):
        read_table(data, 'duplicate.' + kind)


def test_csv_headers_and_control_character_injection():
    from io import BytesIO
    frame = pd.DataFrame({'=SUM(A1)': ['\tmalicious', '\rmalicious', '\nmalicious', '+1'],
                          'numeric': [-2, 1, 2, 3]})
    decoded = pd.read_csv(BytesIO(csv_report(frame)))
    assert decoded.columns[0] == "'=SUM(A1)"
    assert decoded.iloc[:, 0].str.startswith("'").all()
    assert decoded.numeric.tolist() == [-2, 1, 2, 3]


def test_yoy_requires_matching_prior_year_not_adjacent_rows():
    data = clean_financials(pd.DataFrame({
        'period': ['2023-03-31', '2023-06-30', '2024-03-31', '2025-06-30'],
        'revenue': [100, 150, 120, 300], 'expenses': [50, 75, 60, 150]}))
    assert data.revenue_yoy_growth.iloc[2] == pytest.approx(.2)
    assert pd.isna(data.revenue_yoy_growth.iloc[3])
    assert data.revenue_growth.iloc[3] == pytest.approx(1.5)


def test_missing_values_rejected():
    with pytest.raises(ValidationError, match='finite'):
        clean_financials(pd.DataFrame({'revenue': [100, None], 'expenses': [50, 60]}))


def test_aggregate_overflow_is_a_validation_error():
    data = clean_financials(pd.DataFrame({'revenue': [1e308, 1e308], 'expenses': [0, 0]}))
    with pytest.raises(ValidationError, match='numeric range'):
        financial_summary(data)


def test_sorting_preserves_uploaded_metadata_and_duplicate_row_index():
    frame = pd.DataFrame({'period': ['2025', '2024'], 'revenue': [120, 100],
                           'expenses': [60, 50], '_order': ['latest', 'prior']}, index=[0, 0])
    data = clean_financials(frame)
    assert data['_order'].tolist() == ['prior', 'latest']
    assert data.revenue_yoy_growth.iloc[1] == pytest.approx(.2)
