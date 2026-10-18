# Public Community Cloud deployment review

This change keeps all seven pages publicly accessible without login. It adds
application safeguards for a small public research demo. It does **not** establish
production security, tenant separation at the operating-system level, financial
accuracy of model answers, or a guaranteed spending cap.

## Review findings and implemented controls

| Area | Finding | Change |
|---|---|---|
| Chroma | Existing collections were session-specific, but model switching could multiply storage limits | Random 128-bit workspace namespaces; in-memory collections on every OS; shared session lock and aggregate document/chunk limits; at most two model collections |
| Session state | Clear removed indexes/chat but retained financial/portfolio results | Clear removes all private result keys, rotates upload widgets and download filenames, and preserves a separate API quota identity |
| Cleanup | Finalizer-only cleanup could retain indexes; active operations could race deletion | Idle/lifetime expiry, one background reaper, bounded active-workspace admission, serialized close/index/query, weak ownership callbacks, visible retryable failures |
| PDFs | Signature checking alone and parsing in the web process | Strict PDF structural parsing, encrypted/active/embedded-payload rejection, text/page/object/decompression bounds, child-process timeout, Linux memory/CPU caps, two process-wide parsing slots |
| Upload buffers | Multiple uploads could accumulate before indexing | Per-file transport limit plus immediate selected-file count and combined-byte validation; rejected selections rotate out of UI state |
| Gemini | Unbounded shared-key usage and output length | Atomic process-wide and per-session rate/concurrency/daily request/token reservations; every retry charged; explicit SDK single-attempt calls; bounded embedding batches, prompt size, output tokens and history |
| Logs/tracing | Provider failures and optional tracing may contain private text | Sanitized application errors/categories; parser stderr not forwarded; parser environment excludes API secrets; private LangChain calls disable LangSmith tracing; no document or credential logging added |
| Hosting | Python selection/configuration needed to be explicit | Python 3.11 marker, direct pinned-compatible SDK/tracing dependencies, explicit CORS/XSRF protection and disconnected-session TTL; no external database/login added |

## Configuration

All settings below are server controlled. Put them in top-level Community Cloud
Secrets (TOML), or environment variables for local/Docker deployment. The API key
is not requested through the public UI and is never put into URLs or exports.
Environment variable names match the uppercase Settings fields; only model names
use `GEMINI_MODEL` and `GEMINI_EMBEDDING_MODEL`.

```toml
# Enter the real key only in the hosting provider's secure Secrets UI.
GOOGLE_API_KEY = "replace-in-secure-settings-only"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_EMBEDDING_MODEL = "models/gemini-embedding-001"
GEMINI_ENABLED = true
GEMINI_REQUESTS_PER_MINUTE = 30
GEMINI_SESSION_REQUESTS_PER_MINUTE = 6
GEMINI_CONCURRENCY = 2
GEMINI_SESSION_CONCURRENCY = 1
GEMINI_DAILY_REQUESTS = 500
GEMINI_DAILY_TOKENS = 500000
GEMINI_SESSION_DAILY_REQUESTS = 50
GEMINI_SESSION_DAILY_TOKENS = 50000
GEMINI_MAX_INPUT_TOKENS = 16000
GEMINI_MAX_OUTPUT_TOKENS = 1024
MAX_ACTIVE_WORKSPACES = 16
MAX_UPLOAD_BYTES = 20971520
MAX_BATCH_UPLOAD_BYTES = 41943040
MAX_PDF_PAGES = 100
MAX_PDF_TEXT_CHARS = 500000
MAX_DOCUMENTS = 20
MAX_CHUNKS = 5000
PDF_TIMEOUT_SECONDS = 20
PDF_WORKER_MEMORY_MB = 512
SESSION_IDLE_SECONDS = 1800
SESSION_LIFETIME_SECONDS = 7200
```

`GEMINI_ENABLED = false` is the emergency switch and an option for a completely
offline demo. Zero request/token/concurrency allowances reject AI requests; they
do not mean unlimited. Invalid negative/noninteger environment allowances fail
configuration instead of silently falling back. Operator settings should be
reviewed together: increasing the transport limit also requires changing
`.streamlit/config.toml`'s `maxUploadSize`. Settings do not auto-scale with host RAM.

## Quotas and budget semantics

- Counters live in a module singleton, protected by a lock, independently of
  Streamlit reruns and user data. Neither provider credentials nor document text
  is stored in these counters. The session ID is generated on the server.
- Each actual application SDK attempt reserves one request and text input units;
  answer attempts also reserve the full output cap. Failed attempts and retries
  are not refunded. Three application attempts at most; SDK retries are disabled
  by setting its attempt count to one. Embeddings use explicitly bounded batches
  of at most eight chunks, not an unaccounted large SDK batch.
- Input units are UTF-8 bytes plus 256 units of framing per text/request. This is a
  deliberately conservative text estimate, **not** exact provider token usage,
  currency, or a billing ledger. The prompt must fit the input allowance before
  invocation. Output tokens are capped, with thinking disabled for the default
  model; incompatible configurable model settings fail visibly.
- UTC midnight resets daily request/token counters. Rolling one-minute limits
  and concurrency limits do not reset with daily counters. No waiting queue of
  private requests is retained. Quota history is bounded to 1,000 session entries
  and rejects additional identities while full.
- Clearing documents or expiring a workspace retains the browser session quota
  ID. A new browser/WebSocket session can obtain a new identity. This is **not**
  per-person abuse prevention. The process-wide cap still applies on that process.
- Counters reset on server restart, deploy, hibernation or process replacement.
  Multiple workers/replicas have independent budgets. Other apps/scripts using
  the same key are outside this governor. Use a dedicated restricted Google
  project/key, provider-enforced quotas where available, billing alerts, and
  operator monitoring. A strict shared monetary cap needs an external atomic
  quota service/provider control; none was silently added here.
- A PDF requiring more embedding requests than the current limits can exhaust
  quota before completing indexing. Completed API work remains charged, but no
  partial vectors are committed. Prefer smaller PDFs or offline lexical mode.

## Retention and isolation boundaries

Each browser session owns a workspace, private Streamlit state, and random-named
Chroma collections. Documents/financial uploads are never written to user-chosen
paths. Searches, deletion and exports use only that session's service/state;
there is no global document/dataframe/vector/model-response cache or global
Chroma reset. The only shared mutable application resources are admission
counters, cleanup bookkeeping and Chroma's internal engine. Those do not expose a
public collection-enumeration endpoint.

Clear removes all document collections, chat, financial data, price data,
allocation/frontier results and parameters after resources close successfully.
Failed cleanup remains visible and retryable. Upload widget identities rotate;
Streamlit handles the old uploaded buffers' lifecycle. Download filenames include
a random workspace namespace to avoid predictable cross-session media IDs.
**Streamlit download URLs remain bearer links**: someone possessing a generated
link can access it while the platform retains it. Downloads, browser memory,
exports already saved by a user and shared links cannot be revoked by this app.

A daemon checks index expiry every 30 seconds. Default expiry is 30 minutes idle
or two hours maximum lifetime, waiting for active operations to release the
workspace lock. Finalization closes collections after Streamlit releases the
session; disconnected-session TTL is configured to 120 seconds. There is no
publicly supported exact disconnect callback. Remaining chat/tabular/portfolio
session state is cleared on the next interaction after expiry, or when Streamlit
releases the disconnected session. This is not guaranteed immediate erasure from
RAM, swap, host snapshots or platform buffers. No encrypted vault or durability
promise is made. Explicit persistent `RAGService(path)` indexes used by offline
scripts keep their prior behavior and upstream Windows locking caveat.

## Remaining public-hosting risks

1. There is no authentication, CAPTCHA, verified person identity or IP-based abuse
   control. Anonymous visitors can exhaust global capacity and prevent others
   from using the demo. Browser sessions are isolated application state, not a
   security sandbox for arbitrary server-side code.
2. Parser subprocesses run as the same OS user as the app. They do not receive
   credentials in their environment, but are **not** a seccomp/container sandbox:
   a parser exploit could still read host files or access the network. Memory/CPU
   rlimits apply on Linux; Windows uses the wall timeout and process-tree cleanup,
   without equivalent tested OS memory caps. No malware scanner is included.
3. Per-file HTTP transport limits and post-upload selected-file limits cannot
   prevent every resource attack before Streamlit allocates upload buffers.
   CSV/XLSX retain existing size/row/column/ZIP bounds and execute in the web
   process; numerical optimization also runs there. There is no load-tested
   process-wide RAM ceiling or guaranteed solver deadline. Sustained hostile
   traffic can still crash or slow a small Community Cloud instance.
4. Prompt instructions, no executable tools, plain-text rendering and citation
   range checks reduce exposure. They do not prove resistance to every prompt
   injection or validate the truth of generated claims or citation support.
5. Gemini receives selected document text, questions and bounded chat history.
   Review Google's policies/region/retention and Cloud hosting policies. Do not
   upload confidential, regulated, credential-bearing or irreplaceable documents.
6. Dependency locking and CI do not establish absence of vulnerabilities. No
   penetration test, hosting load test, external audit, production deployment,
   data-erasure certification or live-provider test is claimed by this review.

See [public deployment test evidence](public_cloud_test_report.md) for executed
checks and explicitly unverified areas. No login gate, merge or deployment was
performed as part of this change.
