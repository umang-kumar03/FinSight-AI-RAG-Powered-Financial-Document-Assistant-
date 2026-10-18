The original repository only rendered a landing page. This change adds a connected Streamlit research workspace for document retrieval, financial statement analysis, and portfolio optimization while retaining the original project identity and screenshot.

Implemented: bounded multi-PDF ingestion and page citations; LangChain splitting; session-isolated persistent Chroma; offline lexical excerpts and optional Gemini semantic embeddings/answers; document filtering/deletion; raw PDF table extraction and optional OCR; CSV/XLSX financial ratios and growth; CVXPY minimum-variance/maximum-Sharpe portfolios, caps, covariance and efficient frontier; charts and downloadable reports; secure configuration and sanitized API errors/retries. Includes fictional sample inputs, actual generated output examples, and five upstream source reviews with licensing notes.

Validation: Python 3.11 and 3.12 each passed 69 tests with two live-Gemini skips. The non-root Python 3.11 Docker image passed 68 tests with optional OCR and two live Gemini checks skipped, plus HTTP health/HTML checks. Real host OCR passed. Four Streamlit UI tests and real Chromium uploads of PDFs/XLSX/CSV passed. Source coverage was 488/524 statements (93.13%); this is not a model accuracy claim. Evidence is in docs/testing_report.md and the checked-in console/JUnit artifacts.

Screenshots: https://github.com/umang-kumar03/FinSight-AI-RAG-Powered-Financial-Document-Assistant-/tree/feat/complete-finsight-ai/docs/screenshots

Setup: Python 3.11 or 3.12; python -m venv .venv; activate it; pip install -r requirements.txt; streamlit run app.py. Use Dashboard sample buttons. Docker and Streamlit Community Cloud instructions are in docs/deployment.md.

Remaining limits: real Gemini account/model integration needs a securely configured GOOGLE_API_KEY and the opt-in live test. Offline mode is lexical retrieval/excerpts, not semantic or generated QA. Public hostile-upload hosting needs authentication, parser isolation, quotas and retention/security review. Hosted CI and cloud deployment are not claimed as verified. No source was copied from researched projects. No merge, production deployment, registry push or environment publication was performed.

Follow-up: added a safe live-verification CLI and credential-isolation regression tests, rerendered all seven pages, checked sample calculations again, and documented exact Windows commands. The reported credential save still has not made GOOGLE_API_KEY available to this session; live checks are explicitly not run.
