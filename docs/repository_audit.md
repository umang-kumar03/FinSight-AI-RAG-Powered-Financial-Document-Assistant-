# FinSight AI repository audit

Audit date: **2026-10-18**. Portfolio owner: **Umang Kumar**.

## Repository and scope

Verified origin fetch and push URLs:
`https://github.com/umang-kumar03/FinSight-AI-RAG-Powered-Financial-Document-Assistant-.git`.
A read-only Git operation confirmed `main` exists. Fetching `main` showed commit
`3bf29c0` (merge of PR #1) already contains the prior feature implementation.
This audit uses that current main as its base on local branch
**`chore/portfolio-audit`**, with no push upstream configured. No operation was
performed against mamta-kumari28. No push, PR creation, public repository creation,
cloud publication, or deployment was performed during this audit.

All 71 baseline tracked entries were inventoried before edits: Python source,
tests, dependency declarations/constraints, CI, Docker, Streamlit configuration,
README and documentation. Sample PDF/XLSX contents, CSV/JSON outputs, XML test
artifacts, PNG integrity, and standalone HTML structure were inspected. The
bundled Plotly JavaScript is a generated vendor asset, not a separately performed
upstream security audit. Prior working service boundaries and all seven UI
sections were retained. Existing screenshots remain authentic historical assets.

## Findings and fixes

| Finding | Resolution and relevant files |
|---|---|
| Persistent Chroma handles outlived temporary directories; switching embedding models left multiple live clients | Added `RAGService.close()`/context management and `SessionWorkspace` ownership. Close every cached client through Chroma's public API before removing the owned directory. Scripts/tests now close their indexes too. `src/rag.py`, `src/workspace.py`, `app.py`, scripts and fixtures |
| A new document scope could send old document excerpts as history | Reset chat on scope change; test confirms previous messages disappear. Collection and session isolation tests remain. `app.py`, `tests/test_ui.py`, `tests/test_rag.py` |
| Reconfigured credentials could reuse an old cached embedding client | Session identity tracks a key fingerprint (never its value), and the workspace replaces the embedding provider while retaining the compatible index. `app.py`, `src/workspace.py` |
| Pandas silently renamed exact duplicate CSV/XLSX headers before validation | Inspect and normalize the raw header first; reject empty/ambiguous names. `src/finance.py`, `tests/test_finance.py` |
| CSV formula protection missed column headers and leading control characters | Escape textual headers and tab/CR/LF-prefixed cells, preserving numeric negatives. JSON/CSV/HTML downloads are tested against actual UI state. `src/finance.py`, `tests/test_exports.py` |
| Only adjacent-period growth existed | Preserve it and add separately labeled YoY columns/charts matching a reporting date one calendar year earlier. Missing/nonpositive prior-year data stays undefined. `src/finance.py`, `app.py` |
| Internal sorting could overwrite an uploaded `_order` column | Sort by position without an injected column and normalize the row index; regression covers duplicate input indices. `src/finance.py` |
| Finite inputs could overflow aggregate financial totals | Reject nonfinite totals as a clear validation error. Missing values, zero divisors, losses and duplicate dates remain covered. `src/finance.py` |
| Date-indexed price frames were not sorted/validated consistently | Validate unique nonmissing dates whether supplied as a column or DatetimeIndex. Validate names, numeric parameters and boolean misuse. `src/portfolio.py` |
| Solver output could be normalized before validating feasibility | Share finite/size/budget/cap checks; verify frontier return targets. Tests cover invalid outputs, singular covariance, solver fallback/failure and infeasible constraints. The mathematical objectives are preserved. `src/portfolio.py` |
| Empty/nontext Gemini response content could cause an unhandled type error | Normalize text blocks safely and reject invalid answers through ServiceError. Citation labels/page metadata remain checked. `src/rag.py` |
| Model failures were too generic and verification could make calls merely because a key existed | Distinguish sanitized model-unavailable/auth errors. Require explicit `--live` or `RUN_LIVE_GEMINI=1`; query configured model metadata before generation. `src/embeddings.py`, `scripts/verify_live.py` |
| Runtime requirements included tools needed only for tests/sample generation | Moved pytest, pytest-cov and ReportLab into `requirements-dev.txt`; CI installs it. Runtime minimum Chroma is aligned with the pinned public close API. Lock versions are preserved. |
| Ignore lists missed alternate virtual environments, private upload folders in Docker and some SQLite sidecars | Expanded `.gitignore` and `.dockerignore`; tracked-file checks found no private runtime paths or high-confidence credential patterns. This scan is not a proof that every possible secret format is detectable. |
| Example generation rewrote input fixtures and produced a random chart div ID | Read the checked-in samples without rewriting them and use a stable HTML div ID. Regenerated actual analysis CSV now includes YoY columns. `scripts/evaluate.py`, `docs/examples/` |

No direct runtime dependency was removed solely because it is transitive. The
remaining direct packages are imported by the app/services; the constraint file
also records development/optional resolutions and does not install them by itself.

## Executed automated checks

Both supported environments used isolated virtual environments and installed
`requirements-dev.txt`. Both passed `python -m pip check`.
`RUN_LIVE_GEMINI=0` was set explicitly for this audit. Pytest's terminal statistics
were recorded directly, including its warning records:

| Environment | Passed | Failed | Skipped | Errors | Warnings |
|---|---:|---:|---:|---:|---:|
| Linux, Python 3.11.17 | 101 | 0 | 2 | 0 | 0 |
| Linux, Python 3.12.14 | 101 | 0 | 2 | 0 | 0 |

These are 103 collected tests repeated on two interpreters, not 206 distinct
checks. The two skips are the real Gemini connection and semantic-PDF RAG tests.
They require a secure key and explicit opt-in. Real host OCR ran successfully in
both suites because the optional adapter and Tesseract are installed here.
Model/provider mocks are unit tests, not evidence of an actual Gemini response.

Evidence:

- [Python 3.11 statistics](audit_results_python311.json), [console](audit_output_python311.txt), [JUnit](audit_tests_python311.xml)
- [Python 3.12 statistics](audit_results_python312.json), [console](audit_output_python312.txt), [JUnit](audit_tests_python312.xml)
- [Browser workflow results](audit_browser_validation.json)
- [Runtime-only Docker functional checks](audit_runtime_docker.json)
- [Live check status](audit_live_status.json)

During implementation, one new verifier regression initially modeled a transport
failure as an application ServiceError, causing its diagnostic assertion to fail.
It was corrected to use a realistic SDK-style HTTP 404 error; its assertions
remain active and now verify the full sanitization path. Final suite results above
contain no unresolved failures. No meaningful tests were disabled.

Coverage includes real PDF extraction/page references, indexing/deduplication,
provider and browser-session isolation, clear/delete lifecycle, scoped chat,
financial formulas, zero/missing/duplicate inputs, calendar YoY, deterministic
portfolio checks, fallback/failure handling, and export contents. Maximum Sharpe
is checked against an independent 10,001-point two-asset grid, and minimum variance
against an analytic equal-variance case. These are correctness tests, not model
accuracy or investment performance claims.

## Browser and runtime evidence

A real Chromium browser uploaded two bundled PDFs and asked an offline revenue
question, uploaded XLSX financials and displayed the new YoY chart, uploaded CSV
prices, ran **both** objectives, downloaded and checked the maximum-Sharpe JSON,
opened Settings, and cleared the document workspace. All passed. AppTest also
renders all seven sections and checks export bytes against the displayed state.
New screenshots are actual captures using fictional inputs:
[dashboard](screenshots/audit_dashboard.png) and
[financial analysis](screenshots/audit_financial_analysis.png).

The runtime-only `python:3.11-slim` Docker image built with TLS verification intact.
The environment's trusted CA was passed through an optional BuildKit secret, not
copied into a layer. A non-root container passed internal health/HTML requests,
real offline PDF RAG, XLSX financial/YoY checks, both optimizers and a 20-point
frontier. pytest and ReportLab were confirmed absent from that runtime image.
Private `.env`, virtual environment, Git metadata and upload folder were absent.
The complete pytest suite ran on the host, not in this runtime-only image.

Accumulated images from the earlier implementation exhausted local Docker disk
space during startup. Obsolete images created by this work and old build cache
were removed; the current image and repository were retained. Runtime checks then
completed successfully. No user documents or source files were deleted.

## Gemini configuration and availability

`GEMINI_MODEL` and `GEMINI_EMBEDDING_MODEL` are read from environment settings.
A configuration regression proves that `GEMINI_MODEL=gemini-3.8-flash` is honored;
it is not hardcoded as an available model. The default is unchanged.

**Actual availability of gemini-3.8-flash is unknown.** This process reports no
GOOGLE_API_KEY and live calls were not enabled for this audit. The safe checker
therefore reports metadata, connection and generated-PDF stages as `not_run`.
No real Gemini failure/success, answer, quota, or accuracy result is fabricated.

To opt in later after secure configuration:

```powershell
.\.venv\Scripts\python.exe scripts\verify_live.py --live
$env:RUN_LIVE_GEMINI = "1"
.\.venv\Scripts\python.exe -m pytest -q -m live
Remove-Item Env:RUN_LIVE_GEMINI
```

The checker queries both selected model names, then executes a generated reply
and real semantic PDF workflow. Invalid model/authentication/rate-limit responses
are reported through sanitized application messages, not raw provider payloads.
A valid citation label identifies a retrieved page; it does not prove that every
model claim is factually entailed. Always inspect the source excerpts.

## Remaining limitations and readiness

- **Ready for an offline portfolio demonstration with synthetic data:** application
  startup, all seven sections, PDF retrieval/citations, financial analysis,
  optimizers, exports and cleanup were exercised successfully.
- **Live Gemini demonstration remains pending** the explicit credential-enabled
  tests. Model names and account access must be verified, especially 3.8-flash.
- **Windows was not available for execution.** Public close-before-delete ordering
  mitigates the known Chroma lifecycle issue, but an external antivirus/process
  can still lock files. Finalization is best effort and reports leftover locks.
- Public untrusted-document hosting still needs authentication, process-isolated
  parsing/time/memory limits, quotas, encrypted retention and security review.
  Prompt instructions and size/page limits are safeguards, not a security proof.
- Portfolio results are historical in-sample estimates, not forecasts. Taxes,
  costs, slippage, execution and walk-forward validation are not implemented.
- PDF tables are raw grids; arbitrary accounting layouts and OCR accuracy are not
  validated. Financial periods/currencies must be supplied consistently.
- Hosted CI execution and Streamlit Community Cloud resource limits were not
  verified in this audit. No deployment/publication was performed.

## Run and deploy

Use the exact Windows commands in [README](../README.md#windows-vs-code-setup)
or the [deployment guide](deployment.md). No activation-policy changes are needed.
Use `requirements-dev.txt` for development/tests and `requirements.txt` for the
production runtime. Bundled examples are fictional, not private user documents.

For Streamlit Community Cloud, after approving and publishing the code through
GitHub, select Python 3.11, `app.py` and the intended branch. Set GOOGLE_API_KEY
only in the secure Secrets editor; model names may be configured there as root
settings or in the environment. Review the deployment guide and validate with a
non-confidential sample. Deployment is an explicit separate action by the owner.

Local audit commits are prepared for review. **Pushing this branch requires
Umang's explicit approval**; no new PR or remote branch has been created.
