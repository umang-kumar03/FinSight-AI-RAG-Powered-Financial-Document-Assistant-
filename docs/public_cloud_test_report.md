# Public deployment safeguards: executed test evidence

Date: 2026-10-18. These are local Linux results for this change; hosted CI results
are available on the pull request. No production-security or cloud-deployment
claim is made.

| Executed check | Result |
|---|---|
| Full suite, Python 3.11.17 | 152 passed, 0 failed, 2 skipped; no warnings |
| Full suite, Python 3.12.14 | 152 passed, 0 failed, 2 skipped; no warnings |
| Python 3.11 `pip check` | No broken requirements found |
| Python 3.11 `scripts/evaluate.py` | Generated the offline example reports successfully; no Gemini calls |
| Python 3.11 Streamlit startup | Started `app.py`; `/` returned HTTP 200 and `/_stcore/health` returned HTTP 200 with `ok` |
| All seven pages and workflows | Real Streamlit AppTest suite passed, including PDF ingestion/chat/citations, financial sample, solver/frontier and exports |
| Two browser-session AppTest instances | Distinct quota IDs; no second-session documents/reports; clear removed first-session financial/portfolio/chat results without changing the second |

Commands used (from repository root):

```sh
RUN_LIVE_GEMINI=0 /workspace/.finsight-py311/bin/python -m pytest -q --junitxml=/tmp/public-final311.xml
RUN_LIVE_GEMINI=0 .venv/bin/python -m pytest -q --junitxml=/tmp/public-final312.xml
/workspace/.finsight-py311/bin/python -m pip check
/workspace/.finsight-py311/bin/python scripts/evaluate.py
/workspace/.finsight-py311/bin/python -m streamlit run app.py --server.port=8512 --server.address=127.0.0.1
```

Raw results: [Python 3.11 output](public-cloud/linux311-output.txt),
[Python 3.11 JUnit](public-cloud/linux311-results.xml),
[Python 3.12 output](public-cloud/linux312-output.txt),
[Python 3.12 JUnit](public-cloud/linux312-results.xml).
The optional OCR test executed locally. Two live-provider tests were explicitly
skipped with `RUN_LIVE_GEMINI=0`. No real Gemini connection, model availability,
charges or provider behavior was verified in this review.

## Added/extended regression coverage

- Real simultaneous Chroma ingestion in two sessions; foreign document IDs cannot
  retrieve/delete another collection's data; closing one leaves the other usable.
- Same-session upload races cannot exceed document limits; switching model
  collections cannot bypass aggregate document/chunk limits.
- Background idle expiry, closed-index rejection, reference-cycle-free finalization,
  visible cleanup failures, bounded retry, directory removal, and private UI reset.
- PDF structural validation, forged magic header, JavaScript/attachments,
  encrypted files, oversized file/page/text/chunk/selected-file limits and a
  compressed stream exceeding the decompression bound.
- Busy parser admission, simulated timeout/error cleanup and a real timed-out
  child process being killed/reaped. Linux process disappearance is checked.
- Real concurrent quota admission, session/global rolling minute limits,
  concurrency release after failure, daily request/token limits, UTC rollover,
  bounded quota identity capacity, disabled Gemini/zero allowances, and accounting
  on each retry before provider invocation.
- Shared embedding/answer budgets, correct embedding task types and dimensions,
  SDK retry/timeout configuration, output caps, prompt-size rejection before
  invocation, provider error sanitization and disabled private LangSmith tracing.
- Cleanup remains reachable when the selected provider cannot initialize; embedding
  preference survives navigation and repeated reruns without losing isolation.
- Environment and Cloud-secret operator configuration, session quota identity
  surviving clear, complete private-state deletion and independent report state.

## Explicitly unverified boundaries

No hosted Community Cloud deployment, penetration test, sustained anonymous-load
test, malware scan, memory-erasure guarantee, multi-replica atomic quota test,
provider billing cap or external security audit was executed. Current Windows
verification belongs to the hosted CI on the PR, not this Linux machine.
Windows OCR process-tree cleanup and Linux OCR-descendant kill behavior were not
separately exercised by the child-timeout test. Resource caps are defenses, not a
proof that every malformed file is safe. Read the
[full deployment review and remaining risks](public_cloud_review.md).
