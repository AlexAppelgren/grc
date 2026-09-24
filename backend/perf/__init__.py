"""The API performance harness (NFR-02, playbook 10): `harness.py` measures one route,
`routes.py` lists the routes measured, and `scripts/perf_report.py` runs the list against
its budgets and its recorded baseline. Local and CI tooling only: it refuses to run on a
deployed environment."""
