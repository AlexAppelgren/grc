"""Adapters (playbook 16): one interface each for the LLM, the embedder, the agent runner
and the mailer; a mock for tests and E2E; the real provider chosen by a setting. The
production-safety block refuses a mock on a deployed environment other than `test`.

Before implementing a real provider, fetch its current documentation and record what
was relied on in docs/plans/Verification_Log.md. Provider APIs move and are not recalled.
"""
