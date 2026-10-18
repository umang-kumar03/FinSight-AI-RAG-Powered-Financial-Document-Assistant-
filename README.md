# FinSight AI

A financial document assistant and portfolio optimization project.

Explore PDFs with page citations, analyze CSV/XLSX financial statements, and
calculate long-only portfolio allocations in a seven-section Streamlit workspace.
Offline mode runs without API credentials. Gemini semantic embeddings and
grounded answers are optional and require a Google API key. This is a research
application; historical calculations are not investment advice or forecasts.

## Current Progress

- [x] Streamlit home page
- [x] PDF upload and text extraction
- [x] Document Q&A using LangChain and Gemini
- [x] Semantic retrieval using ChromaDB
- [x] Maximum-Sharpe and minimum-variance optimization using CVXPY
- [x] Reports and charts

## Application Output

![FinSight AI home page](docs/screenshots/home.png)

## Deployment

### Docker

From the repository root, build and run the app:

```sh
docker build -t finsight-ai .
docker run --rm -p 8501:8501 finsight-ai
```

Open `http://localhost:8501` in your browser. The container runs `app.py`
with Python 3.11 and the dependencies in `requirements.txt`.

For Gemini integration, pass your local secret through the environment:

```sh
docker run --rm -p 8501:8501 --env-file .env finsight-ai
```

Keep `GOOGLE_API_KEY` in your local `.env` file; do not commit it or put it
in the Docker image. Offline excerpts and local calculations do not use an API key. Gemini mode requires it.

### Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud and connect your GitHub repository.
2. Create an app, choose the branch to deploy, and set the main file to `app.py`.
3. In Advanced settings, select Python 3.11 and add the Gemini secret in the
   secrets field using TOML:

   ```toml
   GOOGLE_API_KEY = "your-google-api-key"
   ```

4. Deploy the app. Community Cloud installs `requirements.txt` automatically.
   Keep the key in the app's secret settings, not in the repository.

## Architecture

The diagram shows the document and portfolio flows. Offline mode substitutes
local lexical embeddings and retrieved excerpts for the Gemini steps.
See [architecture notes](docs/architecture.md) for the service boundaries and formulas.

```mermaid
flowchart LR
    PDF[PDF] --> PyPDF[PyPDF]
    PyPDF --> Chunks[Chunks]
    Chunks --> Embeddings[Embeddings]
    Embeddings --> ChromaDB[ChromaDB]
    ChromaDB --> Gemini[Gemini]
    Prices[Prices] --> CVXPY[CVXPY]
    CVXPY --> Weights[Weights]
```


## Quick start

Use Python 3.11 or 3.12 from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/make_sample_data.py
pytest -q
streamlit run app.py
```

Dependency versions are constrained by `requirements-lock.txt`. In the app,
click **Load sample documents**, **Load sample financials**, or **Load sample
prices** to explore fictional data. No real company or market results are implied.

For Gemini mode, copy `.env.example` to `.env` and configure `GOOGLE_API_KEY`
securely. Select **Gemini semantic** in Settings, then index documents for that
embedding mode; choose **Gemini answer** in PDF Chat Assistant. Offline lexical
retrieval is not a semantic model, and offline excerpts are not generated answers.
Live API integration remains unverified until the opt-in live test passes with a
usable key. Model names can be changed with `GEMINI_MODEL` and
`GEMINI_EMBEDDING_MODEL`.

## Workspace and features

| Section | What you can do |
|---|---|
| Dashboard | Load fictional examples and see current session data |
| PDF Chat Assistant | Retrieve supporting pages, choose offline excerpts or cited Gemini answers, keep conversation history, filter by document |
| Document Library | Index multiple PDFs, deduplicate repeated uploads, delete documents, inspect/export detected tables, opt into scanned-page OCR |
| Financial Analysis | Upload CSV/XLSX, validate and sort data, calculate profit, ratios and growth, view interactive charts |
| Portfolio Optimizer | Upload prices, inspect correlations, solve min variance/max Sharpe, set asset caps, see frontier and allocation charts |
| Charts and Reports | Download financial/portfolio JSON, ratio/frontier CSV, standalone chart HTML, and chat with sources |
| Settings | Choose embedding provider and inspect credential presence, models, storage and privacy notes |

Uploads are bounded to 20 MB per file. PDFs are limited to 100 pages,
20 documents and 5,000 chunks per selected index. PDF text and index data are
session-specific; there is no account system or durable cloud document storage.
Optional OCR requires `requirements-ocr.txt` and Tesseract on the host. Raw table
extraction does not automatically map arbitrary statements into financial schemas.

## Input formats and calculations

Financial CSV/XLSX (first sheet) requires `revenue` and `expenses`. Optional
columns: `period`, `net_income`, `assets`, `equity`, `debt`, `current_assets`,
`current_liabilities`, `operating_income`, `interest_expense`, `cash`, `liabilities`.
Use a single currency and non-overlapping periods. Provided net income is retained;
otherwise it is revenue minus expenses. Undefined ratios are blank, not zero.

```csv
period,revenue,expenses,net_income,assets,equity
2024-12-31,1200,800,400,2400,1500
2025-12-31,1500,1000,500,3000,1900
```

Portfolio data uses `date` and one positive adjusted-price column per asset,
with at least 10 aligned observations and 2–50 assets. Prices must be in one
currency. The default annualization is 252 observations/year. Min variance and
max Sharpe use historical arithmetic means and sample covariance, long-only
fully invested weights, and an optional asset cap. The UI explains omitted costs,
solver status and assumptions; there is no trading execution or backtest claim.

See [sample inputs](data/samples), [calculation definitions](docs/architecture.md),
and [actual generated examples](docs/examples). All inputs there are synthetic.

## Tests and reproducible examples

```sh
python -m pip check
pytest -q --junitxml=test-results.xml --cov=src --cov-report=term-missing
python scripts/evaluate.py
# Optional live API test (after secure key configuration; may incur API charges)
RUN_LIVE_GEMINI=1 pytest -q -m live
```

The default tests exercise real local Chroma retrieval, PDF extraction, financial
formulas, solver constraints, an analytic min-variance case, a brute-force
max-Sharpe comparison, and Streamlit workflows. Provider transport is mocked in
unit tests; the live test is explicitly skipped without credentials and opt-in.
OCR tests skip if optional dependencies are missing. Read the [actual testing
report](docs/testing_report.md) for executed results and deployment limitations.

## Screenshots from the running app

These captures use only the fictional bundled data; the original home-page
screenshot above is retained as historical project output.

![Dashboard](docs/screenshots/dashboard.png)
![PDF chat with actual uploaded sample documents](docs/screenshots/pdf_chat.png)
![Financial analysis using fictional sample data](docs/screenshots/financial_analysis.png)
![Portfolio calculation using synthetic sample prices](docs/screenshots/portfolio.png)

## Project structure

```text
app.py                      Streamlit UI
src/                        Config, PDF parsing, embeddings, RAG, finance, portfolio
scripts/make_sample_data.py  Deterministic fictional examples
scripts/evaluate.py          Local pipeline and exported output examples
tests/                      Unit, integration, UI, optional OCR/live-provider tests
data/samples/               PDF, CSV, XLSX and retrieval labels
docs/examples/              Generated calculation/retrieval outputs and chart
docs/                       Architecture, deployment, research, checklist, test evidence
.streamlit/config.toml      Upload limits and theme
Dockerfile                  Python 3.11 image and health check
.github/workflows/ci.yml     Python 3.11/3.12 tests, reports and Docker smoke check
```

## Documentation and deployment boundary

- [Architecture and formulas](docs/architecture.md)
- [Local VS Code, Docker, Community Cloud and optional OCR](docs/deployment.md)
- [Five open-source project reviews and licensing notes](docs/github_research.md)
- [Implementation checklist](docs/implementation_checklist.md)
- [Test evidence and remaining limitations](docs/testing_report.md)

This repository prepares a deployable research app, not a certified production
financial service. Public untrusted uploads require authentication, isolated
parser workers, quotas, encrypted storage/retention and security review. Prompt
instructions and citation-label validation do not guarantee factual correctness.
No production deployment, cloud publish, merge, model accuracy or investment
performance is claimed. No upstream project source was copied; research links
and license notes are recorded in `docs/github_research.md`.
