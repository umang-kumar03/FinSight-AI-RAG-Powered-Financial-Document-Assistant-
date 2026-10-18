"""FinSight AI: session-isolated document research and financial analysis."""
from dataclasses import replace
from pathlib import Path
import logging
import tempfile

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import Settings
from src.documents import extract_tables
from src.embeddings import GeminiEmbeddings, LocalEmbeddings
from src.errors import ServiceError, ValidationError
from src.finance import clean_financials, csv_report, financial_summary, json_report, read_table
from src.portfolio import ASSUMPTIONS, efficient_frontier, estimate_moments, optimize, validate_prices
from src.rag import RAGService

ROOT = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('finsight.ui')

st.set_page_config(page_title='FinSight AI', page_icon='📊', layout='wide')
st.title('📊 FinSight AI')
st.caption('Financial documents, transparent calculations, and portfolio research')


def settings():
    configured = Settings.from_env()
    # Streamlit secrets are read in memory only; never copied to .env or logs.
    try:
        secret = st.secrets.get('GOOGLE_API_KEY', '')
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        secret = ''
    return replace(configured, api_key=secret or configured.api_key)


def rag():
    mode = st.session_state.get('embedding_mode', 'Offline lexical')
    configured = settings()
    identity = (mode, configured.embedding_model)
    if st.session_state.get('rag_identity') != identity:
        provider = GeminiEmbeddings(configured) if mode == 'Gemini semantic' else LocalEmbeddings()
        # Never use a globally cached index: different browser sessions must not share documents.
        if 'workspace' not in st.session_state:
            st.session_state.workspace = tempfile.TemporaryDirectory(prefix='finsight-session-')
        st.session_state.rag_service = RAGService(st.session_state.workspace.name,
                                                provider, configured)
        st.session_state.rag_identity = identity
        st.session_state.messages = []
    else:
        st.session_state.rag_service.settings = configured
    return st.session_state.rag_service


def load_sample_financials():
    path = ROOT / 'data/samples/financials.csv'
    st.session_state.financials = clean_financials(read_table(path.read_bytes(), path.name))


def load_sample_prices():
    path = ROOT / 'data/samples/prices.csv'
    st.session_state.prices = read_table(path.read_bytes(), path.name)
    st.session_state.pop('portfolio_result', None)


def show_sources(sources):
    for i, source in enumerate(sources, 1):
        with st.expander(f"[S{i}] {source['source']} — page {source['page']}"):
            st.text(source['text'])
            st.caption('Retrieval score is a ranking signal, not an accuracy estimate.')


def dashboard():
    st.header('Research workspace')
    left, right = st.columns(2)
    left.metric('Indexed documents', len(rag().documents()))
    right.metric('Financial periods', len(st.session_state.get('financials', [])))
    st.info('Start with the fictional sample data, or upload your own PDF, CSV, or XLSX.')
    a, b, c = st.columns(3)
    if a.button('Load sample documents'):
        with st.spinner('Indexing fictional reports…'):
            for name in ['annual_report.pdf', 'risk_note.pdf']:
                rag().ingest((ROOT / 'data/samples' / name).read_bytes(), name)
        st.success('Two sample documents indexed. Open PDF Chat Assistant.')
    if b.button('Load sample financials'):
        load_sample_financials()
        st.success('Fictional financial data loaded.')
    if c.button('Load sample prices'):
        load_sample_prices()
        st.success('Synthetic prices loaded.')
    st.subheader('How to use the workspace')
    st.markdown('1. Add PDFs in **Document Library**.\n'
                '2. Ask questions in **PDF Chat Assistant** and inspect citations.\n'
                '3. Upload statements in **Financial Analysis** or prices in **Portfolio Optimizer**.\n'
                '4. Download calculated outputs in **Charts and Reports**.')
    st.warning('Offline mode returns document excerpts, not Gemini answers. '
               'Gemini mode sends retrieved text to Google; enable it only for documents you may share.')


def library():
    st.header('Document Library')
    st.caption('PDF only · 20 MB/file · 100 pages/file · 20 documents · 5,000 total chunks')
    uploaded = st.file_uploader('Upload PDFs', type=['pdf'], accept_multiple_files=True)
    ocr = st.checkbox('OCR blank/scanned pages (optional host setup required)')
    if st.button('Index uploaded PDFs', disabled=not uploaded):
        for file in uploaded:
            try:
                with st.spinner(f'Indexing {file.name}…'):
                    rag().ingest(file.getvalue(), file.name, ocr=ocr)
                st.success(f'Indexed {file.name}')
            except (ValidationError, ServiceError) as exc:
                st.error(str(exc))
    if uploaded:
        selected = st.selectbox('Inspect tables from an uploaded PDF', range(len(uploaded)),
                                format_func=lambda i: uploaded[i].name)
        if st.button('Extract tables'):
            with st.spinner('Extracting text tables…'):
                file = uploaded[selected]
                tables = extract_tables(file.getvalue(), file.name)
                if not tables:
                    st.info('No grid-based tables detected; this is not an accounting parser.')
                for i, table in enumerate(tables):
                    frame = pd.DataFrame(table['rows'])
                    st.caption(f"{table['source']} · page {table['page']}")
                    st.dataframe(frame)
                    st.download_button('Download table CSV', csv_report(frame),
                                       file_name=f'table-{i+1}.csv', key=f'table-{i}')
    docs = rag().documents()
    if not docs:
        st.info('No indexed documents in the selected embedding mode.')
    for doc in docs:
        left, right = st.columns([4, 1])
        left.write(f"{doc['name']} · {doc['pages']} readable pages · {doc['chunks']} chunks")
        if right.button('Delete', key=f"delete-{doc['id']}"):
            rag().delete_document(doc['id'])
            st.session_state.messages = []
            st.rerun()
    if st.button('Clear this session workspace'):
        service = rag()
        # Delete collections first; release handles before removing their temporary files.
        for collection in service.client.list_collections():
            service.client.delete_collection(collection.name)
        st.session_state.pop('rag_identity', None)
        st.session_state.pop('rag_service', None)
        st.session_state.messages = []
        st.success('All indexed text and chat history cleared for this session.')


def chat():
    st.header('PDF Chat Assistant')
    service = rag()
    docs = service.documents()
    if not docs:
        st.info('Upload PDFs in Document Library or load sample documents on the Dashboard.')
    mode = st.radio('Answer mode', ['Offline excerpts', 'Gemini answer'], horizontal=True)
    st.caption('Offline retrieval is lexical. Choose Gemini semantic embeddings in Settings '
               'for meaning-based search. Switching embeddings requires re-indexing your documents.')
    selection = st.selectbox('Search scope', ['All documents'] + [d['id'] for d in docs],
                            format_func=lambda v: next((d['name'] for d in docs if d['id'] == v), v))
    history = st.session_state.setdefault('messages', [])
    if st.button('Clear chat history'):
        st.session_state.messages = []
        history = st.session_state.messages
    for message in history:
        with st.chat_message(message['role']):
            # Render untrusted document/model content as plain text.
            st.text(message['content'])
            if message.get('sources'):
                show_sources(message['sources'])
    question = st.chat_input('Ask about your documents', disabled=not docs, max_chars=2000)
    if question:
        with st.chat_message('user'):
            st.text(question)
        with st.spinner('Retrieving supporting pages…'):
            answer = service.answer(question, mode='gemini' if mode == 'Gemini answer' else 'offline',
                                    history=history,
                                    document_id=None if selection == 'All documents' else selection)
        payload = answer.to_dict()
        history.extend([{'role': 'user', 'content': question},
                        {'role': 'assistant', 'content': answer.text, 'sources': payload['sources']}])
        st.session_state.messages = history[-40:]
        with st.chat_message('assistant'):
            st.text(answer.text)
            show_sources(payload['sources'])


def financial_analysis():
    st.header('Financial Analysis')
    st.caption('Required: revenue, expenses. Optional: period, net_income, assets, equity, '
               'debt, current_assets, current_liabilities, operating_income, interest_expense. '
               'Use distinct, non-overlapping periods and one currency.')
    upload = st.file_uploader('Financial statements (CSV/XLSX)', type=['csv', 'xlsx'])
    if st.button('Analyze uploaded financials', disabled=upload is None):
        with st.spinner('Validating and calculating ratios…'):
            st.session_state.financials = clean_financials(read_table(upload.getvalue(), upload.name))
    if st.button('Use sample financials'):
        load_sample_financials()
    frame = st.session_state.get('financials')
    if frame is not None:
        summary = financial_summary(frame)
        a, b, c = st.columns(3)
        a.metric('Revenue (all periods)', f"{summary['total_revenue']:,.2f}")
        b.metric('Net income (all periods)', f"{summary['total_net_income']:,.2f}")
        margin = summary['aggregate_profit_margin']
        c.metric('Aggregate profit margin', f'{margin:.1%}' if margin is not None else 'Undefined')
        st.plotly_chart(px.bar(frame, x='period', y=['revenue', 'expenses', 'net_income'],
                               barmode='group', title='Reported financial amounts'), width='stretch')
        st.plotly_chart(px.line(frame, x='period', y=['revenue_growth', 'profit_growth'],
                                markers=True, title='Period-over-period growth (decimal)'), width='stretch')
        st.dataframe(frame, hide_index=True)
        st.info(summary['assumptions'])
        st.caption(summary['net_income_method'])
        st.download_button('Download financial analysis', csv_report(frame), 'financial_analysis.csv')


def portfolio():
    st.header('Portfolio Optimizer')
    st.caption('Upload aligned positive adjusted prices: date, asset_a, asset_b, … '
               'At least 10 observations and 2 assets. All prices must use the same currency.')
    upload = st.file_uploader('Historical prices (CSV/XLSX)', type=['csv', 'xlsx'])
    if st.button('Load uploaded prices', disabled=upload is None):
        frame = read_table(upload.getvalue(), upload.name)
        validate_prices(frame)
        st.session_state.prices = frame
        st.session_state.pop('portfolio_result', None)
    if st.button('Use sample prices'):
        load_sample_prices()
    frame = st.session_state.get('prices')
    if frame is None:
        st.info('Upload historical prices or use the synthetic sample.')
        return
    prices = validate_prices(frame)
    st.plotly_chart(px.line(prices / prices.iloc[0], title='Prices normalized to 1'), width='stretch')
    method = st.selectbox('Objective', ['min_variance', 'max_sharpe'])
    frequency = int(st.number_input('Observations per year', min_value=1, max_value=366, value=252))
    risk_free = st.number_input('Annual risk-free rate (decimal)', min_value=-1.0, max_value=2.0,
                                value=0.02, step=0.01)
    cap = st.number_input('Maximum weight per asset', min_value=1 / len(prices.columns),
                          max_value=1.0, value=1.0, step=0.05)
    with st.expander('Historical risk, returns, covariance and correlations'):
        names, means, covariance, daily_returns = estimate_moments(frame, frequency)
        estimates = pd.DataFrame({'asset': names, 'annual_return': means,
                                  'annual_volatility': [float(covariance[i, i] ** 0.5)
                                                        for i in range(len(names))]})
        st.dataframe(estimates, hide_index=True)
        st.caption('Annualized sample covariance matrix')
        st.dataframe(pd.DataFrame(covariance, index=names, columns=names))
        st.caption('Return correlations')
        st.dataframe(daily_returns.corr())
    if st.button('Optimize portfolio'):
        with st.spinner('Solving convex portfolio problems…'):
            result = optimize(frame, method, risk_free, frequency, cap)
            frontier = efficient_frontier(frame, points=20, periods_per_year=frequency, max_weight=cap)
        st.session_state.portfolio_result = result.to_dict()
        st.session_state.frontier = frontier
        st.session_state.portfolio_parameters = {'periods_per_year': frequency,
                                                'risk_free_rate': risk_free, 'max_weight': cap}
    result = st.session_state.get('portfolio_result')
    if result:
        st.caption(f"Last calculated objective: {result['method']} · parameters: "
                   f"{st.session_state.portfolio_parameters}. Click Optimize to apply changed settings.")
        a, b, c = st.columns(3)
        a.metric('In-sample annual return estimate', f"{result['annual_return']:.2%}")
        b.metric('Annual volatility estimate', f"{result['annual_volatility']:.2%}")
        c.metric('Estimated Sharpe', f"{result['sharpe']:.3f}" if result['sharpe'] is not None else 'Undefined')
        allocation = pd.DataFrame(result['weights'].items(), columns=['asset', 'weight'])
        st.plotly_chart(px.pie(allocation, names='asset', values='weight', title='Allocation'), width='stretch')
        st.dataframe(allocation, hide_index=True)
        st.plotly_chart(px.line(st.session_state.frontier, x='annual_volatility', y='annual_return',
                                title='In-sample efficient frontier'), width='stretch')
        st.caption(f"Solver status: {result['solver_status']}")
    st.warning(ASSUMPTIONS)


def reports():
    st.header('Charts and Reports')
    frame = st.session_state.get('financials')
    result = st.session_state.get('portfolio_result')
    if frame is None and result is None and not st.session_state.get('messages'):
        st.info('Analyze financials, optimize a portfolio, or ask a document question first.')
    if frame is not None:
        st.download_button('Financial report JSON', json_report(financial_summary(frame)),
                           'financial_summary.json', mime='application/json')
        st.download_button('Ratios and growth CSV', csv_report(frame), 'financial_analysis.csv')
    if result:
        report = {'assumptions': ASSUMPTIONS, 'parameters': st.session_state.portfolio_parameters,
                  **result}
        st.download_button('Portfolio report JSON', json_report(report), 'portfolio.json')
        st.download_button('Efficient frontier CSV', csv_report(st.session_state.frontier), 'frontier.csv')
        chart = px.line(st.session_state.frontier, x='annual_volatility', y='annual_return',
                        title='In-sample efficient frontier')
        st.download_button('Interactive frontier chart HTML', chart.to_html(include_plotlyjs=True).encode(),
                           'frontier.html', mime='text/html')
    if st.session_state.get('messages'):
        st.download_button('Chat with source excerpts JSON',
                           json_report({'messages': st.session_state.messages}), 'chat.json')
    st.caption('Exports contain your data. Store and share them according to your privacy requirements.')


def preferences():
    st.header('Settings')
    configured = settings()
    st.selectbox('Embedding provider', ['Offline lexical', 'Gemini semantic'], key='embedding_mode')
    st.write('Google API key: ' + ('configured' if configured.api_key else 'not configured'))
    st.code(f'Chat model: {configured.chat_model}\nEmbedding model: {configured.embedding_model}')
    st.markdown('Set `GOOGLE_API_KEY` in your local `.env` or Streamlit Community Cloud secrets. '
                'Never commit it. Offline mode needs no key. Changing embedding mode opens '
                'a separate collection; re-index PDFs for that mode.')
    st.info('PDFs are parsed in memory. Extracted text is indexed in a session-specific temporary '
            'directory. Chat is kept in session memory. Use Document Library to delete indexed data. '
            'Temporary files are not an encrypted storage service. Refresh/session expiry may '
            'discard data; no account system or durable cloud storage is configured.')
    st.warning('Do not expose this app to untrusted public uploads without authentication, '
               'parser process isolation, upload quotas, and a retention policy. '
               'Input limits and prompt instructions reduce risk but do not guarantee security.')


PAGES = {'Dashboard': dashboard, 'PDF Chat Assistant': chat, 'Document Library': library,
         'Financial Analysis': financial_analysis, 'Portfolio Optimizer': portfolio,
         'Charts and Reports': reports, 'Settings': preferences}
page = st.sidebar.radio('Workspace', list(PAGES))
st.sidebar.caption('For learning and research. Not financial advice.')
try:
    PAGES[page]()
except (ValidationError, ServiceError) as exc:
    st.error(str(exc))
except Exception as exc:
    # No stack trace or raw provider text: those can contain uploaded data or credentials.
    logger.error('Workflow failed (%s)', type(exc).__name__)
    st.error('This operation could not finish. Check the input format and local setup, then retry.')

st.divider()
st.caption('For learning and research. Not financial advice. Historical estimates are not forecasts.')
