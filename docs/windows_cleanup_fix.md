# Windows workspace cleanup fix

## Reported failure and investigation

The owner reported Windows: 99 passed, 1 failed, 3 skipped. The failure was
`test_workspace_clear_never_removes_other_session`: `assert one.close()` returned
False while another session remained open. That assertion is preserved.

The pinned Chroma 1.5.9 Python `Client.close()` releases its shared-system
references, but `RustBindingsAPI.stop()` only deletes its binding object. The
matching 1.5.9 native binding has no explicit shutdown/SQLite pool close method.
The installed binding also lacks `close`. This source-confirmed shutdown gap is
consistent with the observed Windows native/SQLite lock retention; Linux permits
unlinking open files, so a Linux-only passing test did not prove Windows cleanup.
The exact native thread holding the user's file was not instrumented here.

Source inspected: [Chroma 1.5.9 bindings](https://github.com/chroma-core/chroma/blob/1.5.9/rust/python_bindings/src/bindings.rs)
and [Python stop](https://github.com/chroma-core/chroma/blob/1.5.9/chromadb/api/rust.py).
No third-party installation or private Chroma system cache was patched/reset.

## Fix

- Windows **temporary sessions** use Chroma's supported in-memory client, avoiding
  native disk handles for data which was already documented as non-durable.
  Explicit `RAGService(path)` indexes retain their persistent behavior. Linux
  sessions retain their disk-backed behavior.
- Because ephemeral clients share a process-wide engine, each workspace gets a
  random namespace and each embedding model its own collection. Closing a service
  deletes only its owned collection and closes only its client. Another session
  continues retrieving its documents. No global reset/cache clearing occurs.
- `RAGService.close()` is idempotent, releases collection/client references, and
  supports retrying client closure after its ephemeral collection was deleted.
- Workspace cleanup closes all clients before touching the owned directory.
  Failed clients remain registered and prevent directory deletion. OS deletion
  errors get five bounded attempts (0.75 seconds total backoff). Persistent locks
  still produce a warning and False; a later close can genuinely retry.
- A failed explicit close no longer consumes the workspace finalizer. The UI
  keeps an unsuccessfully cleaned workspace available for another clear attempt.
- Disposable evaluation/live-check indexes also use memory on Windows; live
  calls still require explicit opt-in. No credentials or `.env` were modified.

This does not promise that an explicitly persistent Chroma 1.5.9 database can be
deleted while other native handles are live on Windows. Retain such databases
until their owning process exits, or use a future verified upstream shutdown fix.

## Tests and evidence

Full local suites with live calls disabled:

| Platform | Python | Passed | Failed | Skipped |
|---|---|---:|---:|---:|
| Linux | 3.11.17 | 108 | 0 | 2 live-provider tests |
| Linux | 3.12.14 | 108 | 0 | 2 live-provider tests |

[3.11 output](windows-cleanup/linux311-output.txt),
[3.12 output](windows-cleanup/linux312-output.txt),
[3.11 JUnit](windows-cleanup/linux311-results.xml),
[3.12 JUnit](windows-cleanup/linux312-results.xml).
Both local suites also executed the installed optional OCR test.

Regression tests cover two simultaneously live memory sessions, owned collection
removal, no persistent files in Windows session mode, normal/idempotent close,
transient OS locks, visible exhausted cleanup, retained failed clients, retrying
partially completed closure, and rejecting reuse of a closed workspace. A
platform-selection test on Linux is not a Windows execution result.

Native Windows execution is unavailable in the local container. This PR adds
`windows-latest` Python 3.11 and 3.12 jobs to CI alongside Linux, with uniquely
named artifacts. Windows verification is pending those actual jobs; results will
be recorded after they finish. No existing test assertion was weakened or skipped.

## Exact Windows PowerShell verification

From the repository folder, preserve any local changes before switching branches:

```powershell
git fetch origin
git switch fix/windows-workspace-cleanup
git pull --ff-only origin fix/windows-workspace-cleanup
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
$env:RUN_LIVE_GEMINI = "0"
.\.venv\Scripts\python.exe -m pytest tests\test_workspace.py -q
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_LIVE_GEMINI
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Use the Dashboard sample-document button in two browser sessions, clear the first
session's Document Library, and confirm the second can still answer from its own
sample documents. No Google API key is needed for this offline verification.
The optional OCR test skips without its adapter/Tesseract; the two real Gemini
tests skip with live calls disabled. Do not merge/deploy without owner approval.
