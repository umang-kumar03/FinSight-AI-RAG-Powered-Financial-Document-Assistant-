"""Run reproducible local RAG and financial/portfolio examples."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evaluation import evaluate_retrieval
from src.finance import clean_financials, csv_report, financial_summary, json_report, read_table
from src.portfolio import ASSUMPTIONS, efficient_frontier, optimize
from src.rag import RAGService


def main():
    root = Path(__file__).resolve().parents[1]
    samples = root / 'data' / 'samples'
    output = root / 'docs' / 'examples'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='finsight-evaluation-') as directory, \
            RAGService(directory) as service:
        for name in ['annual_report.pdf', 'risk_note.pdf']:
            service.ingest((samples / name).read_bytes(), name)
        cases = json.loads((samples / 'retrieval_cases.json').read_text())
        evaluation = evaluate_retrieval(service, cases, k=2)
        (output / 'retrieval_evaluation.json').write_bytes(json_report(evaluation))
        answer = service.answer('What was revenue in 2025?')
        (output / 'offline_answer.json').write_bytes(json_report(answer.to_dict()))
    financials = clean_financials(read_table((samples / 'financials.csv').read_bytes(), 'financials.csv'))
    (output / 'financial_analysis.csv').write_bytes(csv_report(financials))
    (output / 'financial_summary.json').write_bytes(json_report(financial_summary(financials)))
    prices = read_table((samples / 'prices.csv').read_bytes(), 'prices.csv')
    portfolios = {method: optimize(prices, method=method).to_dict()
                  for method in ['min_variance', 'max_sharpe']}
    (output / 'portfolio_results.json').write_bytes(json_report({'assumptions': ASSUMPTIONS, **portfolios}))
    frontier = efficient_frontier(prices)
    (output / 'efficient_frontier.csv').write_bytes(csv_report(frontier))
    import plotly.express as px
    px.line(frontier, x='annual_volatility', y='annual_return',
            title='Synthetic sample: in-sample efficient frontier').write_html(
                output / 'efficient_frontier.html', include_plotlyjs=True, div_id='finsight-efficient-frontier')
    print('Generated actual offline example outputs in docs/examples (no Gemini calls).')


if __name__ == '__main__':
    main()
