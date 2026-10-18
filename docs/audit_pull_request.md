Ambiguous table headers could silently change financial inputs, spreadsheet exports
missed dangerous headers/control characters, and temporary Chroma files could be
removed while clients still held locks. This audit validates raw headers, protects
CSV text, scopes conversation history, and closes owned clients before cleanup.
It also adds correctly labeled calendar YoY calculations and stronger portfolio
input/solver validation while preserving the existing service architecture.

Runtime dependencies are separated from test/sample tools. Gemini model names
remain configurable, including gemini-3.8-flash as an environment override;
availability is not claimed. Live verification requires explicit opt-in and checks
model metadata before generation, with sanitized error messages.

Validation: 101 passed, 2 live-provider skips, zero failures/errors/warnings on both
Python 3.11 and 3.12. Actual browser upload/chat/financial/optimizer/export/cleanup
flows passed. The non-root runtime-only Docker image built and passed health and
representative functional checks. Exact evidence, real screenshots and Windows /
Community Cloud instructions are linked from docs/repository_audit.md.

Limits: live Gemini/account/model access and Windows behavior remain unverified;
public hostile-upload deployment needs authentication, parser isolation and
retention controls. No security certification or investment-performance claim is
made. This description is prepared locally; no push, new PR, deployment or
publication has been authorized or performed during this audit.
