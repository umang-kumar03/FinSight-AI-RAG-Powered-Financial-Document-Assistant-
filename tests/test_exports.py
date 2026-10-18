"""Compare downloaded artifacts to the actual UI's last calculated state."""
import base64
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
import streamlit as st


def click(app, label):
    next(button for button in app.button if button.label == label).click().run(timeout=45)


def test_finance_portfolio_and_html_exports_match_ui_state():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py').run(timeout=45)
    app.sidebar.radio[0].set_value('Financial Analysis').run(timeout=45)
    click(app, 'Use sample financials')
    app.sidebar.radio[0].set_value('Portfolio Optimizer').run(timeout=45)
    click(app, 'Use sample prices')
    click(app, 'Optimize portfolio')
    with patch('streamlit.download_button', wraps=st.download_button) as downloads:
        app.sidebar.radio[0].set_value('Charts and Reports').run(timeout=45)
    assert not app.exception and not app.error
    exports = {call.args[0]: call.args[1] for call in downloads.call_args_list}
    financial = json.loads(exports['Financial report JSON'])
    assert financial['total_revenue'] == 3700
    portfolio = json.loads(exports['Portfolio report JSON'])
    assert portfolio['weights'] == app.session_state['portfolio_result']['weights']
    assert portfolio['parameters'] == app.session_state['portfolio_parameters']
    ratios = pd.read_csv(BytesIO(exports['Ratios and growth CSV']))
    pd.testing.assert_frame_equal(ratios, app.session_state['financials'], check_dtype=False)
    frontier = pd.read_csv(BytesIO(exports['Efficient frontier CSV']))
    pd.testing.assert_frame_equal(frontier, app.session_state['frontier'])
    html = exports['Interactive frontier chart HTML'].decode()
    assert 'plotly.js' in html  # The chart is self-contained, with its JS bundle.
    decoder = json.JSONDecoder()
    tail = html.rsplit('Plotly.newPlot(', 1)[1].lstrip()
    _, offset = decoder.raw_decode(tail)
    traces, _ = decoder.raw_decode(tail[offset:].lstrip(' ,\n'))
    def values(array):
        if isinstance(array, dict):
            return np.frombuffer(base64.b64decode(array['bdata']), dtype=array['dtype'])
        return np.asarray(array)
    np.testing.assert_allclose(values(traces[0]['x']), frontier.annual_volatility)
    np.testing.assert_allclose(values(traces[0]['y']), frontier.annual_return)
