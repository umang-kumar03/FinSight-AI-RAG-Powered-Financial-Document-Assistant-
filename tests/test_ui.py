"""Streamlit workflow tests execute the real UI and real local backends."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / 'app.py'


def button(app, label):
    return next(b for b in app.button if b.label == label)


def go(app, label):
    app.sidebar.radio[0].set_value(label).run(timeout=45)
    assert not app.exception
    assert not app.error, [e.value for e in app.error]
    return app


def test_all_pages_render():
    app = AppTest.from_file(APP).run(timeout=45)
    assert app.title[0].value == '📊 FinSight AI'
    assert not app.exception and not app.error
    for page in ['Document Library', 'PDF Chat Assistant', 'Financial Analysis',
                 'Portfolio Optimizer', 'Charts and Reports', 'Settings', 'Dashboard']:
        go(app, page)


def test_financial_and_portfolio_ui():
    app = AppTest.from_file(APP).run(timeout=45)
    go(app, 'Financial Analysis')
    button(app, 'Use sample financials').click().run(timeout=45)
    assert not app.exception and not app.error
    assert app.metric[0].value == '3,700.00'
    go(app, 'Portfolio Optimizer')
    button(app, 'Use sample prices').click().run(timeout=45)
    button(app, 'Optimize portfolio').click().run(timeout=45)
    assert not app.exception and not app.error
    result = app.session_state['portfolio_result']
    assert abs(sum(result['weights'].values()) - 1) < 1e-6
    go(app, 'Charts and Reports')
    assert len(app.get('download_button')) >= 4


def test_pdf_chat_ui_and_delete():
    app = AppTest.from_file(APP).run(timeout=45)
    button(app, 'Load sample documents').click().run(timeout=45)
    assert not app.error
    go(app, 'PDF Chat Assistant')
    app.chat_input[0].set_value('What was revenue in 2025?').run(timeout=45)
    assert not app.exception and not app.error
    assert len(app.chat_message) == 2
    assert '1500' in app.session_state['messages'][-1]['content']
    assert app.session_state['messages'][-1]['sources'][0]['page'] == 1
    go(app, 'Document Library')
    button(app, 'Delete').click().run(timeout=45)
    assert not app.exception and not app.error
    assert len(app.session_state['rag_service'].documents()) == 1
    assert not app.session_state['messages']


def test_missing_gemini_key_is_safe(monkeypatch):
    from src.config import Settings
    # Isolate this negative test from real .env files and Streamlit secret bindings.
    monkeypatch.setattr('src.config.Settings.from_env', lambda: Settings())
    monkeypatch.setattr('streamlit.secrets', {})
    app = AppTest.from_file(APP).run(timeout=45)
    button(app, 'Load sample documents').click().run(timeout=45)
    go(app, 'PDF Chat Assistant')
    app.radio[0].set_value('Gemini answer').run(timeout=45)
    app.chat_input[0].set_value('revenue?').run(timeout=45)
    assert not app.exception
    assert any('GOOGLE_API_KEY' in e.value for e in app.error)


def test_scope_change_clears_previous_document_conversation():
    app = AppTest.from_file(APP).run(timeout=45)
    button(app, 'Load sample documents').click().run(timeout=45)
    go(app, 'PDF Chat Assistant')
    app.chat_input[0].set_value('revenue 2025').run(timeout=45)
    assert app.session_state['messages']
    # AppTest select options are formatted names; use underlying service id.
    actual_id = app.session_state['rag_service'].documents()[0]['id']
    app.selectbox[0].set_value(actual_id).run(timeout=45)
    assert not app.exception and not app.error
    assert not app.session_state['messages']


def test_workspace_clear_releases_index_path():
    app = AppTest.from_file(APP).run(timeout=45)
    button(app, 'Load sample documents').click().run(timeout=45)
    old_path = Path(app.session_state['workspace'].directory.name)
    go(app, 'Document Library')
    button(app, 'Clear this session workspace').click().run(timeout=45)
    assert not app.exception and not app.error
    assert not old_path.exists()
    assert not app.session_state['rag_service'].documents()


def test_two_browser_sessions_isolate_all_private_results_and_clear():
    first = AppTest.from_file(APP).run(timeout=45)
    second = AppTest.from_file(APP).run(timeout=45)
    try:
        assert first.session_state['_quota_session'] != second.session_state['_quota_session']
        button(first, 'Load sample documents').click().run(timeout=45)
        go(first, 'PDF Chat Assistant')
        first.chat_input[0].set_value('revenue 2025').run(timeout=45)
        go(first, 'Financial Analysis')
        button(first, 'Use sample financials').click().run(timeout=45)
        go(first, 'Portfolio Optimizer')
        button(first, 'Use sample prices').click().run(timeout=45)
        button(first, 'Optimize portfolio').click().run(timeout=45)
        assert not first.error and not first.exception
        assert first.session_state['financials'] is not None
        assert first.session_state['portfolio_result']
        go(second, 'Charts and Reports')
        assert not second.get('download_button')
        assert not second.session_state['rag_service'].documents()
        second.session_state['messages'] = [{'role': 'user', 'content': 'other private chat'}]
        quota_id = first.session_state['_quota_session']
        generation = first.session_state['_upload_generation']
        go(first, 'Document Library')
        button(first, 'Clear this session workspace').click().run(timeout=45)
        assert not first.error and not first.exception
        assert first.session_state['_quota_session'] == quota_id
        assert first.session_state['_upload_generation'] == generation + 1
        for key in ('financials', 'prices', 'portfolio_result', 'frontier', 'portfolio_parameters'):
            assert key not in first.session_state
        go(first, 'Charts and Reports')
        assert not first.get('download_button')
        assert second.session_state['messages'][0]['content'] == 'other private chat'
    finally:
        first.session_state['workspace'].close()
        second.session_state['workspace'].close()


def test_cloud_secrets_apply_server_side_budgets(monkeypatch):
    monkeypatch.setattr('streamlit.secrets', {'GEMINI_ENABLED': False,
                                            'GEMINI_DAILY_TOKENS': 1234,
                                            'GEMINI_MODEL': 'operator-model'})
    app = AppTest.from_file(APP).run(timeout=45)
    try:
        go(app, 'Settings')
        assert 'operator-model' in app.code[0].value
        assert any('1,234' in caption.value for caption in app.caption)
        configured = app.session_state['workspace'].settings
        assert configured.gemini_enabled is False
        assert configured.gemini_daily_tokens == 1234
    finally:
        app.session_state['workspace'].close()
