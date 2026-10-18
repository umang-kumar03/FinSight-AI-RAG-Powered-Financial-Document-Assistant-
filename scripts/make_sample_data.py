"""Generate deterministic fictional documents, financials, and prices; no APIs."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

ROOT = Path(__file__).resolve().parents[1]


def make_samples(directory: Path = ROOT / 'data' / 'samples'):
    directory.mkdir(parents=True, exist_ok=True)
    financials = pd.DataFrame({
        'period': ['2023-12-31', '2024-12-31', '2025-12-31'],
        'revenue': [1000, 1200, 1500], 'expenses': [700, 800, 1000],
        'net_income': [300, 400, 500], 'assets': [2000, 2400, 3000],
        'liabilities': [800, 900, 1100], 'equity': [1200, 1500, 1900],
        'debt': [600, 650, 700], 'current_assets': [700, 850, 1000],
        'current_liabilities': [350, 400, 500]})
    financials.to_csv(directory / 'financials.csv', index=False)
    financials.to_excel(directory / 'financials.xlsx', index=False)
    rng = np.random.default_rng(42)
    market = rng.normal(0.0005, 0.006, size=(252, 1))
    returns = market + rng.normal([0.0003, 0.0005, 0.0001], [0.005, 0.010, 0.003], (252, 3))
    prices = pd.DataFrame(100 * np.cumprod(1 + returns, axis=0),
                          columns=['alpha', 'beta', 'gamma'])
    prices.insert(0, 'date', pd.bdate_range('2025-01-01', periods=252).strftime('%Y-%m-%d'))
    prices.to_csv(directory / 'prices.csv', index=False)
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(directory / 'annual_report.pdf'), pagesize=A4,
                             title='Fictional FinSight sample', invariant=1)
    table = Table([['Year', 'Revenue', 'Expenses', 'Net income'],
                   ['2023', '1000', '700', '300'], ['2024', '1200', '800', '400'],
                   ['2025', '1500', '1000', '500']], colWidths=[80] * 4)
    table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 1, colors.black)]))
    doc.build([Paragraph('Fictional Example Company — Annual Report', styles['Title']),
               Paragraph('Synthetic teaching data, not a real company or investment recommendation.', styles['BodyText']),
               Spacer(1, 16),
               Paragraph('Revenue increased to 1500 in 2025. Net income was 500. '
                         'Expenses were 1000. All amounts are fictional currency units.', styles['BodyText']),
               Spacer(1, 16), table])
    SimpleDocTemplate(str(directory / 'risk_note.pdf'), invariant=1).build([
        Paragraph('Fictional Risk Note', styles['Title']),
        Paragraph('The company faces liquidity risk and currency risk. '
                  'Historical returns do not guarantee future performance.', styles['BodyText'])])
    cases = [
        {'query': 'What was revenue in 2025?', 'relevant': [{'source': 'annual_report.pdf', 'page': 1}]},
        {'query': 'What liquidity risk does the company face?', 'relevant': [{'source': 'risk_note.pdf', 'page': 1}]}]
    (directory / 'retrieval_cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    return directory


if __name__ == '__main__':
    print(f'Generated fictional sample inputs in {make_samples()}')
