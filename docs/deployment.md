# Local development and deployment

## Local / VS Code

Use Python 3.11 (also tested on 3.12). Open the repository folder in VS Code,
install Microsoft's Python extension, and select `.venv` with **Python: Select
Interpreter** after creating it:

```sh
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
python scripts/make_sample_data.py
pytest -q
streamlit run app.py
```

The checked-in constraints file records resolved dependencies. Refresh it only
with a full test run on supported Python versions. Use a dedicated environment;
no system Python or CUDA is required. All fixture companies/prices are synthetic.

For Gemini, copy `.env.example` to `.env` and set `GOOGLE_API_KEY` securely.
Only Gemini embeddings and answers need this key. No financial data API,
Chroma server, or brokerage credential is required. Offline mode works without
credentials and is labeled as lexical retrieval/excerpts in the UI. Configure
`GEMINI_MODEL` / `GEMINI_EMBEDDING_MODEL` if your account uses different models.
Google quota, billing, access, and model availability remain account-dependent.

Never put `.env`, Streamlit secrets, or API keys in Git, images, screenshots,
reports, logs, or issue/PR text. Gemini sends retrieved document text to Google.

## Docker

```sh
docker build -t finsight-ai .
docker run --rm -p 8501:8501 finsight-ai
# Optional Gemini credentials (not copied into the image):
docker run --rm -p 8501:8501 --env-file .env finsight-ai
```

Open the published port in your local browser. The image uses `python:3.11-slim`,
installs the constrained requirements and runs Streamlit on `0.0.0.0:8501`.
The Docker HEALTHCHECK polls Streamlit's `/_stcore/health` with a Python request.
That endpoint verifies server readiness; functional checks are the automated
backend/UI tests. `.dockerignore` excludes local secrets, virtual environments,
Chroma data and outputs. Session indexes are ephemeral; do not mount a shared
index directory for unrelated users.

Modern Docker BuildKit is required for the optional CA secret mount. Ordinary
builds need no secret. Behind a TLS-inspecting corporate proxy, preserve certificate
verification and supply the organization's trusted certificate bundle:

```sh
docker build --build-arg HTTPS_PROXY --build-arg HTTP_PROXY \
  --secret id=custom_ca,src=/path/to/trusted-ca-bundle.pem -t finsight-ai .
```

The bundle is mounted only for installation, not copied into a layer. Configure
proxy DNS according to your infrastructure; do not hardcode onboarding proxy
addresses in application code or disable TLS verification. Runtime Gemini requests
behind such a proxy also need the host's supported trusted-CA configuration.

## Streamlit Community Cloud

1. Push the branch to a GitHub repository you can deploy.
2. Sign in to Community Cloud, connect the repository, and choose `app.py`.
3. Select Python 3.11 in Advanced settings and enter this in Secrets, with the
   real value entered only through the secure UI:

   ```toml
   GOOGLE_API_KEY = "your-google-api-key"
   ```

4. Deploy when authorized. `requirements.txt` and its relative constraint file
   are installed from the repository root. Offline pages work without a key.
5. Test a small non-confidential PDF in Gemini mode, citations, financial sample,
   and portfolio sample after deployment. Review actual logs without printing keys.

Uploaded documents and chat are session-specific and not durable across restarts.
Community Cloud resource limits may require smaller files and fewer concurrent
sessions; this environment has not published a cloud app or load-tested hosting.
Do not expose confidential documents publicly. Apply authentication and the
production controls in architecture.md before serving untrusted users.

## Optional scanned-PDF OCR

The standard image supports text PDFs and raw table extraction. Scanned pages
need both `pip install -r requirements-ocr.txt` and the host executable Tesseract
(e.g. Ubuntu `sudo apt-get install tesseract-ocr`). On Community Cloud, add an
operator-reviewed `packages.txt` and OCR requirements if OCR is required; they
are not automatically enabled by this project. English OCR quality depends on
the scan; layout and numerical errors require human checking.

## Tests, outputs, and live integration

```sh
pytest -q --junitxml=test-results.xml --cov=src --cov-report=term-missing
python scripts/evaluate.py
# Explicitly opt in after securely configuring a usable key:
RUN_LIVE_GEMINI=1 pytest -q -m live
```

Live tests incur API calls and may incur costs. The default suite skips the live
provider test without explicit opt-in; mocks are not proof of provider access.
OCR tests skip if the optional package/executable is unavailable. CI runs both
Python versions, produces test/coverage artifacts and offline examples, and builds
and health-checks Docker. No workflow deploys or merges automatically.
