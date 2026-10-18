"""FinSight AI: session-isolated document research and financial analysis."""
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path
import logging
import time

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import Settings
from src.documents import extract_tables, validate_upload_batch
from src.embeddings import GeminiEmbeddings, LocalEmbeddings
from src.errors import ServiceError, ValidationError
from src.finance import clean_financials, csv_report, financial_summary, json_report, read_table
from src.portfolio import ASSUMPTIONS, efficient_frontier, estimate_moments, optimize, validate_prices
from src.workspace import SessionWorkspace
from src.session_state import clear_private_state, prepare_session

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
    overrides = {'api_key': secret or configured.api_key}
    # Operator-only top-level Cloud secrets; no model/budget settings from browser input.
    try:
        for item in fields(Settings):
            if item.name in {'api_key', 'session_id'}:
                continue
            key = {'chat_model': 'GEMINI_MODEL', 'embedding_model': 'GEMINI_EMBEDDING_MODEL'}.get(
                item.name, item.name.upper())
            value = st.secrets.get(key)
            if value is not None:
                if item.type is int:
                    if isinstance(value, bool) or not str(value).isdigit():
                        raise ServiceError(f'{key} must be a nonnegative integer in server settings.')
                    value = int(value)
                elif item.type is bool:
                    if str(value).lower() not in {'true', 'false', '0', '1'}:
                        raise ServiceError(f'{key} must be true or false in server settings.')
                    value = str(value).lower() in {'true', '1'}
                else:
                    value = str(value)
                overrides[item.name] = value
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    return replace(configured, **overrides, session_id=st.session_state['_quota_session'])


def rag():
    mode = st.session_state.get('embedding_mode', 'Offline lexical')
    configured = settings()
    identity = (mode, configured.embedding_model, sha256(configured.api_key.encode()).digest())
    if st.session_state.get('rag_identity') != identity:
        # Never use a globally cached index: different browser sessions must not share documents.
        if 'workspace' not in st.session_state:
            st.session_state.workspace = SessionWorkspace(settings=configured)
        provider = GeminiEmbeddings(configured) if mode == 'Gemini semantic' else LocalEmbeddings()
        st.session_state.rag_service = st.session_state.workspace.service(provider, configured)
        st.session_state.rag_identity = identity
        st.session_state.messages = []
    else:
        st.session_state.rag_service.settings = configured
        if isinstance(st.session_state.rag_service.embeddings, GeminiEmbeddings):
            st.session_state.rag_service.embeddings.settings = configured
    return st.session_state.rag_service


def download(label, data, file_name, **kwargs):
    # Streamlit download URLs are bearer links, not authenticated endpoints.
    # Random per-workspace filenames avoid predictable cross-session media IDs.
    return st.download_button(label, data,
        file_name=f'{st.session_state.workspace.namespace}-{file_name}', **kwargs)


def load_sample_financials():
    path = ROOT / 'data/samples/financials.csv'
    st.session_state.financials = clean_financials(read_table(path.read_bytes(), path.name))


def load_sample_prices():
    path = ROOT / 'data/samples/prices.csv'
    st.session_state.prices = read_table(path.read_bytes(), path.name)
    for key in ('portfolio_result', 'frontier', 'portfolio_parameters'):
        st.session_state.pop(key, None)


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
    configured = settings()
    st.caption(f'PDF only · {configured.max_upload_bytes // (1024*1024)} MB/file · '
               f'{configured.max_pdf_pages} pages/file · {configured.max_documents} documents · '
               f'{configured.max_chunks:,} chunks across this session')
    uploaded = st.file_uploader('Upload PDFs', type=['pdf'], accept_multiple_files=True,
                                key=f"pdf-upload-{st.session_state['_upload_generation']}")
    if st.session_state.get('_upload_notice'):
        st.warning(st.session_state.pop('_upload_notice'))
    if uploaded:
        try:
            validate_upload_batch([file.size for file in uploaded], configured)
        except ValidationError as exc:
            st.session_state['_upload_notice'] = str(exc)
            st.session_state['_upload_generation'] += 1
            st.rerun()
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
                tables = extract_tables(file.getvalue(), file.name, configured)
                if not tables:
                    st.info('No grid-based tables detected; this is not an accounting parser.')
                for i, table in enumerate(tables):
                    frame = pd.DataFrame(table['rows'])
                    st.caption(f"{table['source']} · page {table['page']}")
                    st.dataframe(frame)
                    download('Download table CSV', csv_report(frame),
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
        # Only this session's path is owned here; close every model-specific client first.
        workspace = st.session_state.get('workspace')
        removed = workspace.close() if workspace else True
        if not removed:
            st.warning('Cleanup could not finish. Session data is retained for a cleanup retry.')
        else:
            clear_private_state(st.session_state)
            st.rerun()


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
    if st.session_state.get('chat_scope') != selection:
        st.session_state.messages = []
        st.session_state.chat_scope = selection
    st.caption('Conversation history resets when the selected document scope changes.')
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
    upload = st.file_uploader('Financial statements (CSV/XLSX)', type=['csv', 'xlsx'],
                              key=f"financial-upload-{st.session_state['_upload_generation']}")
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
        if 'revenue_yoy_growth' in frame:
            st.plotly_chart(px.line(frame, x='period', y=['revenue_yoy_growth', 'profit_yoy_growth'],
                                    markers=True, title='Year-over-year growth (matching reporting dates)'),
                            width='stretch')
        st.dataframe(frame, hide_index=True)
        st.info(summary['assumptions'])
        st.caption(summary['net_income_method'])
        download('Download financial analysis', csv_report(frame), 'financial_analysis.csv')


def portfolio():
    st.header('Portfolio Optimizer')
    st.caption('Upload aligned positive adjusted prices: date, asset_a, asset_b, … '
               'At least 10 observations and 2 assets. All prices must use the same currency.')
    upload = st.file_uploader('Historical prices (CSV/XLSX)', type=['csv', 'xlsx'],
                              key=f"prices-upload-{st.session_state['_upload_generation']}")
    if st.button('Load uploaded prices', disabled=upload is None):
        frame = read_table(upload.getvalue(), upload.name)
        validate_prices(frame)
        st.session_state.prices = frame
        for key in ('portfolio_result', 'frontier', 'portfolio_parameters'):
            st.session_state.pop(key, None)
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
        download('Financial report JSON', json_report(financial_summary(frame)),
                           'financial_summary.json', mime='application/json')
        download('Ratios and growth CSV', csv_report(frame), 'financial_analysis.csv')
    if result:
        report = {'assumptions': ASSUMPTIONS, 'parameters': st.session_state.portfolio_parameters,
                  **result}
        download('Portfolio report JSON', json_report(report), 'portfolio.json')
        download('Efficient frontier CSV', csv_report(st.session_state.frontier), 'frontier.csv')
        chart = px.line(st.session_state.frontier, x='annual_volatility', y='annual_return',
                        title='In-sample efficient frontier')
        download('Interactive frontier chart HTML', chart.to_html(include_plotlyjs=True).encode(),
                           'frontier.html', mime='text/html')
    if st.session_state.get('messages'):
        download('Chat with source excerpts JSON',
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
    st.info('Your documents, Chroma collection, chat, financial data and portfolio results belong '
            'to this browser session. Clear this session workspace to remove all these results. '
            'Idle indexes expire after the configured retention interval; reconnects can lose data.')
    st.warning('This public research demo has no login. Avoid confidential or regulated documents. '
               'Gemini sends selected excerpts/history to Google. In-memory quotas are per process '
               'and reset on restart; new browser sessions can bypass per-session quotas. '
               'See README for public deployment limits and remaining risks.')
    st.caption(f'AI limits: {configured.gemini_requests_per_minute} requests/minute globally, '
               f'{configured.gemini_session_requests_per_minute}/session; '
               f'{configured.gemini_concurrency} concurrent; '
               f'{configured.gemini_daily_requests} requests and '
               f'{configured.gemini_daily_tokens:,} reserved token units/day (UTC).')



PAGES = {'Dashboard': dashboard, 'PDF Chat Assistant': chat, 'Document Library': library,
         'Financial Analysis': financial_analysis, 'Portfolio Optimizer': portfolio,
         'Charts and Reports': reports, 'Settings': preferences}
page = st.sidebar.radio('Workspace', list(PAGES))
st.sidebar.caption('For learning and research. Not financial advice.')
try:
    prepare_session(st.session_state)
    if 'workspace' not in st.session_state:
        st.session_state.workspace = SessionWorkspace(settings=settings())
    st.session_state.workspace.touched = time.monotonic()
    PAGES[page]()
except (ValidationError, ServiceError) as exc:
    st.error(str(exc))
except Exception as exc:
    # No stack trace or raw provider text: those can contain uploaded data or credentials.
    logger.error('Workflow failed (%s)', type(exc).__name__)
    st.error('This operation could not finish. Check the input format and local setup, then retry.')

st.divider()
st.caption('For learning and research. Not financial advice. Historical estimates are not forecasts.')
