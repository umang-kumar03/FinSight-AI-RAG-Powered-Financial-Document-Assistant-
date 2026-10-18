# Implementation checklist

Baseline: connected `umang-kumar03/FinSight-AI-RAG-Powered-Financial-Document-Assistant-`,
commit `2e5e9d6`. All eight tracked text/config/source files were inspected, and the
existing screenshot asset was identified. Only a Streamlit landing page existed;
there were no backend modules, sample-data generator, or automated tests. The
requested mamta-kumari28 URL returned “Repository not found”; the user approved
continuing in the connected repository. Work is on `feat/complete-finsight-ai`.

- [x] Inspect source, README, dependencies, Docker, ignores, CI, and existing Git changes.
- [x] Research five public repositories and record source/version/license evidence.
- [x] PDF extraction, page-preserving chunks, multi-document library, Chroma retrieval.
- [x] Local lexical mode and Gemini semantic embeddings/grounded answers.
- [x] Reranking, table extraction, optional OCR, labeled retrieval evaluation.
- [x] CSV/XLSX analysis, ratios, growth, charts, report downloads.
- [x] Price validation, moments, min variance, max Sharpe, frontier, allocation.
- [x] Seven connected Streamlit sections, safe errors, session history/settings.
- [x] Unit, integration, UI tests; generated samples and actual outputs.
- [x] Deployment, health checks, CI, architecture and testing documentation.
- [x] Commit, push, and attempt a pull request; do not merge or deploy.

Final status and limitations are recorded in docs/testing_report.md. An unchecked
external check is not satisfied by a mock or by configuration alone.

## External acceptance still pending

- [ ] Real Gemini semantic embedding and generated-answer test with a securely configured key.
- [ ] Hosted CI outcome and successful PR creation (API permission dependent).
- [ ] Any actual cloud deployment, load/security review, or environment publication (not performed; deployment/publication require approval).

Implementation checkboxes indicate delivered code and local validation where
possible; they do not override these external acceptance limits. See the testing
report for exact passed/skipped counts and the final GitHub delivery outcome.
