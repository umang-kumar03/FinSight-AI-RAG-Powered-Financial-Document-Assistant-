# Executed tests and acceptance status

Run date: **2026-10-18**. Repository used with user confirmation:
`umang-kumar03/FinSight-AI-RAG-Powered-Financial-Document-Assistant-`.
The requested `mamta-kumari28` URL was not accessible (Git returned
“Repository not found”). No source was fetched from that inaccessible URL.

## Actual results

| Execution | Passed | Skipped | Failed/errors | Evidence |
|---|---:|---:|---:|---|
| Python 3.11.17, constrained dependencies, host Tesseract enabled | 69 | 2 live Gemini tests | 0 | [Console](test-output-python311.txt), [JUnit](test-results-python311.xml) |
| Python 3.12.14, same dependency constraints, host Tesseract enabled | 69 | 2 live Gemini tests | 0 | [Console and coverage](test-output-python312.txt), [JUnit](test-results-python312.xml), [coverage JSON](coverage-python312.json) |
| Python 3.11 Docker image, non-root appuser, standard requirements | 68 | 1 optional OCR test and 2 live Gemini tests | 0 | [Latest console](test-output-docker-latest.txt) |

There are **71 collected tests** in the latest suite; repetitions across environments
are not additional distinct tests. The retained Docker JUnit/console files without
`latest` in their names describe the earlier 68-test image run, not this latest run. The Python 3.12 coverage run executed **488 of 524 source
statements (93.13%)** in `src/`. Coverage is execution evidence, not proof of
correctness or a model accuracy metric. The Streamlit entrypoint is exercised by
four actual AppTest workflow tests; it is outside the `--cov=src` denominator.
A [final host UI rerun](test-output-ui-final.txt) also passed all four tests after
adding the displayed covariance/risk tables.

Executed commands included:

```sh
python -m pip install -r requirements.txt
python -m pip check
python scripts/make_sample_data.py
pytest -q --junitxml=docs/test-results-python311.xml
pytest -q --junitxml=docs/test-results-python312.xml --cov=src \
  --cov-report=term-missing --cov-report=json:docs/coverage-python312.json
python scripts/evaluate.py
```

Separate Python 3.11 and 3.12 virtual environments were used. Optional
`requirements-ocr.txt` was installed on the host; the real scanned-image PDF test
rendered a page and verified recognized text contained `1500`. The standard
Docker image intentionally omits the optional OCR adapter/executable, hence its
additional skip. Both live tests are skipped without an available key.

## What was exercised

- Real PDF extraction, page references, text cleaning, chunk metadata/limits,
  malformed/oversized/encrypted/blank-file rejection and raw grid-table extraction.
- Real session-path-isolated persistent Chroma indexes, deduplication, deletion,
  document filters, lexical retrieval, unsupported-query handling, rollback and
  capacity limits. Offline PDF → chunks → embeddings → Chroma → cited excerpts
  works end to end without an API.
- Gemini embedding/answer adapters through mocked transports, response citation
  validation, sanitized failures, wrapped rate-limit retries and exhausted retry
  messages. These mocks **do not validate a real Google account or model call**.
- CSV and XLSX parsing, date ordering, net-income preservation/derivation,
  margins/current ratio/debt-equity/ROA/interest coverage, growth, zero-denominator
  handling, invalid inputs and CSV formula neutralization.
- Long-only fully invested min-variance and max-Sharpe solutions, cap constraints,
  efficient frontier feasibility, singular covariance, bad data and infeasible
  parameters. Independent checks include equal independent variances giving
  half/half allocation and a 10,001-point two-asset grid checking max Sharpe.
- All seven UI sections, loading real local sample data, financial metrics,
  portfolio solving/report actions, PDF chat with page citation, deletion/history
  clearing, and a safe missing-key error.

## Running app and actual output examples

The app started successfully with Python 3.11 on an internal local port. Both
`/_stcore/health` (`ok`) and the HTML entrypoint returned HTTP 200. A real Chromium
browser loaded the UI, navigated to financial analysis and portfolio optimization,
clicked sample actions, and captured:
[dashboard](screenshots/dashboard.png),
[financial analysis](screenshots/financial_analysis.png), and
[portfolio](screenshots/portfolio.png).
The original `home.png` is retained as the earlier project's screenshot.
These are real captures of fictional sample data, not generated mockups.
A second real-browser check uploaded two actual PDF files, asked the revenue
question with source excerpts, uploaded XLSX financials (3700 revenue and 1200
net income), and uploaded CSV prices and solved the portfolio. All four checks
passed; the resulting [PDF chat capture](screenshots/pdf_chat.png) is included.
[Browser check output](browser-validation.txt) records the observed outcome.

`scripts/evaluate.py` produced the files in [examples](examples). The sample
financial total revenue is **3700**, total expenses **2500**, and net income
**1200**; these follow directly from the three bundled fictional periods.
Portfolio outputs are actual solver results on seeded synthetic prices, not
historical market performance. The two labeled retrieval fixtures returned the
expected source/page at rank 1; `retrieval_evaluation.json` records the executed
values. Two trivial fixtures do **not** support a general retrieval accuracy,
semantic quality, or financial decision claim.

## Docker validation and troubleshooting

The original Docker build could not resolve the environment's network proxy.
Adding an infrastructure-local proxy hostname mapping exposed a second issue:
the builder lacked the environment's trusted CA. The final Dockerfile accepts an
optional BuildKit-mounted trusted CA bundle for installation. The image then
built successfully with certificate verification enabled. The CA file and proxy
credentials were not copied into the image. Normal networks do not need this
onboarding-specific configuration; see deployment.md.

The final image runs as **appuser, not root**. A launched container became healthy;
internal health and HTML requests passed, the full default suite ran in the
container, and `/app/.env`, `/app/.venv`, and `/app/.git` were confirmed absent.
No image was pushed to a registry and no production app was deployed.

## Remaining acceptance boundaries

| Criterion | Status |
|---|---|
| Application starts and UI calls real backend | Verified locally and in Docker |
| Core offline document retrieval/citation pipeline | Verified end to end |
| Real Gemini semantic embeddings and generated answers | **Not verified: GOOGLE_API_KEY is absent** |
| Correct sample financial calculations and portfolio optimization | Verified against assertions and independent optimization checks |
| Unit/integration/UI tests | Passing as reported above; skips are explicit |
| Optional OCR | Real host test passed; not included in standard Docker/CI runtime |
| Larger corpus retrieval study / scanned accounting accuracy | Not performed; only small synthetic fixtures |
| CI configuration | Implemented; hosted GitHub Actions execution not verified here |
| Cloud deployment, load tests, public-service security hardening | Not performed; deployment instructions provided |
| GitHub PR creation | Attempted after commits; consult delivery notes below for actual outcome |

The app is a working deployable research application. The user's full acceptance
criterion for **live Gemini RAG** remains pending secure credentials and a real
provider test. To complete that check, configure `GOOGLE_API_KEY` securely in the
environment (or `.env` locally), allow `generativelanguage.googleapis.com`, and run
`RUN_LIVE_GEMINI=1 pytest -q -m live`. Do not paste keys in chat or logs. No API
output, cloud deployment success, public security certification, or model accuracy
has been invented.

The environment draft now contains updated install/start instructions and a
`GOOGLE_API_KEY` requirement scoped to `generativelanguage.googleapis.com`.
Saving the draft did not inject a key, publish the environment, merge, or deploy.
Review/save secure configuration in environment settings; publication remains a
separate action requiring the user's approval.

## GitHub delivery outcome

Implementation commits were pushed successfully on `feat/complete-finsight-ai`.
PR creation was attempted with both `gh pr create` (GraphQL) and GitHub's REST
pull-request endpoint. Both returned **Forbidden**. Git push access works;
GitHub API access is not authorized in this environment. No PR was created or
merged, and no repository credentials were extracted or replaced.

The complete [prepared PR description](pull_request.md) includes features,
validation, screenshot links, setup and limitations. Open the comparison below
to review the pushed branch and create the PR using an account with access:

https://github.com/umang-kumar03/FinSight-AI-RAG-Powered-Financial-Document-Assistant-/compare/main...feat/complete-finsight-ai?expand=1


## Follow-up verification after credential configuration was reported saved

The user reported saving `GOOGLE_API_KEY`. Presence-only checks before and after
that message still returned **unset** in newly launched application processes.
The environment draft metadata reported `has_saved_binding: false` for
`GOOGLE_API_KEY` and no pending runtime requirement. The app also had no local
`.env` or `.streamlit/secrets.toml`. No key or credential-file contents were
printed or copied. This describes what this session could observe; it does not
establish what may have been configured in another environment or editor.

The new safe opt-in checker, `python scripts/verify_live.py`, recorded
[live-validation.json](live-validation.json) and exited 2: connection and live
semantic RAG were **not run**, because the required key was unavailable. No
unauthenticated request was described as a successful API connection. Both full
host suites were invoked with `RUN_LIVE_GEMINI=1`, but their two live tests still
skipped due to absent credentials. The application cannot complete the live
acceptance criterion until the saved key is actually injected into this process.

Two regression tests verify the checker fails closed without a key and never
includes provider exception payloads or keys in its result. The missing-key UI
test now explicitly isolates `.env` and Streamlit secret configuration, preventing
it from accidentally making real API calls on a developer machine with secrets.

All seven pages were independently re-rendered without errors:
[page-validation.json](page-validation.json). The XLSX statement totals were
checked again (revenue 3700 and net income 1200); both portfolio objectives
satisfied nonnegative weights summing to one, and the frontier contained 20 points:
[sample-validation.json](sample-validation.json). The Docker image was rebuilt
with the current test additions and its latest default suite passed as above.

[Exact Windows PowerShell and VS Code commands](deployment.md#exact-windows-powershell--vs-code-commands)
are now included. They use the virtual environment interpreter directly, avoiding
PowerShell execution-policy changes. Windows execution remains unverified; the
reported test runs took place on Linux.
