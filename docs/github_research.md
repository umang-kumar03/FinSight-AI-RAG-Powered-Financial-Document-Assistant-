# Comparable open-source projects reviewed

Review performed on 2026-10-18 using shallow HTTPS Git clones in a temporary
research directory. These are source reviews, not claims that the upstream apps
were installed, executed, or benchmarked. All FinSight implementation code is
original; no upstream source was copied. Project ideas and standard mathematical
formulations informed the decisions below. License information describes the
reviewed revision, not every historical revision.

| Project and reviewed commit | Architecture, files examined | Features/dependencies | Quality and limitations | FinSight decision |
|---|---|---|---|---|
| [LangChain Streamlit agent](https://github.com/langchain-ai/streamlit-agent), `634e1cecf23d7ca3a4c5e708944673e057765b2a` | README, Apache-2.0 license, pyproject, `streamlit_agent/chat_with_documents.py`; app-per-example structure | PyPDFLoader, recursive splitting, HuggingFace embeddings, DocArray, conversational retrieval, session history; LangChain/OpenAI, torch | Readable teaching examples; older LangChain imports and heavyweight local models. Temporary uploads and cached retrievers need careful user isolation. Pandas-agent example explicitly warns about code execution. | Separate ingestion/retrieval/UI modules, page metadata, bounded session history, per-session indexes. No arbitrary dataframe agent or code execution. |
| [Streamlit LLM examples](https://github.com/streamlit/llm-examples), `7cf260745675e41f92e7436d3777aafdab9dad9f` | README, Apache-2.0 license, requirements, `pages/1_File_Q&A.py`, `app_test.py`; small multipage apps | File Q&A, chat, provider keys, mocked AppTest tests; Streamlit, OpenAI, Anthropic, old pinned LangChain | Clear minimal UI and provider mocking. File Q&A is a single prompt, not a scalable indexed RAG system; legacy provider APIs. | Use AppTest for real UI flows and explicit mocked/live-provider separation; persist source metadata and retrieve bounded context rather than sending entire files. |
| [Chroma](https://github.com/chroma-core/chroma), `ddc17cd7c508f15f237c965e74e536ff64396ddb` | README, Apache-2.0 license, pyproject, `chromadb/api/models/Collection.py`; Python API, Rust engine, tests/examples | Persistent collections, explicit embeddings, metadata filters, query/get/delete; Python/Rust and vector-index runtime | Full infrastructure project with broad API/test surface. Embedded storage is not application authentication, tenant isolation, or encrypted cloud persistence. | Use explicit vectors, model-specific collection names, bounded batch writes, document IDs, metadata filtering/deletion, no default embedding-model download. |
| [CVXPortfolio](https://github.com/cvxgrp/cvxportfolio), `351c782b9b8b395c1a5f886b77e0d55f1bc9396e` | README.rst, GPL-3.0 license, pyproject, `cvxportfolio/policies.py`, `risks.py`; modular estimators/policies, examples/tests | Single/multi-period convex portfolio optimization, risk models, trading costs/backtesting; CVXPY, NumPy, Pandas | Mature separation of forecasting, objectives, and constraints. Much broader than an educational static portfolio tool; complex assumptions. GPL code must not be casually copied. | Independently implement static long-only CVXPY programs; explicit missing costs/backtesting and historical-estimate warnings. No upstream code incorporated. |
| [PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt), `a6638d2e06dae6f444fd022cfd4b3c528902a85b` | README, MIT license, pyproject, `pypfopt/efficient_frontier/efficient_frontier.py`, `expected_returns.py`; library, cookbook, tests | Mean/covariance estimates, minimum volatility, transformed max-Sharpe, frontier; CVXPY, SciPy, Pandas | Clear objectives and validation boundaries. Forecast estimates and solver outputs remain sensitive to historical samples; not promised investment performance. | Independent textbook max-Sharpe change of variables; cap constraints transformed consistently; validate against a two-asset brute-force grid and an analytic min-variance example. |

## Technical documentation used as reference points

- [Streamlit deployment and secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud)
- [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing)
- [LangChain Google integration](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai)
- [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings)
- [Chroma collections](https://docs.trychroma.com/docs/collections/manage-collections)
- [CVXPY portfolio example](https://www.cvxpy.org/examples/finance/portfolio_optimization.html)

These documentation URLs are references, not evidence of a live Gemini call.
The actual installed adapter signatures and local APIs are validated by tests.

## Scope and tradeoffs

The accessible selection covers document chat, UI testing, vector infrastructure,
and financial optimization. It does not constitute a survey of all financial
RAG projects. Offline embeddings are deterministic lexical hashing, **not learned
semantic embeddings**. Gemini semantic embeddings are optional and need secure
credentials; no semantic-quality numbers are claimed without a live run.
Reranking combines vector similarity, token overlap, and page diversity, not an
untested cross-encoder. Financial table extraction preserves raw grids and does
not claim to infer accounting schemas from arbitrary PDFs. No remote financial
price API is needed; uploaded prices avoid additional credentials and licensing.
