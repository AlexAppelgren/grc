# The law's own words

One file per tranche, named as the tranche is (`se-forordningar.json` beside
`../se-forordningar.json`): the verbatim text of the sections, articles and guidelines the
tranche's obligations cite, in the language the authority published them in, with the
translations that stand beside it.

The format, its rules and what each source asks of someone who republishes its text are in
`../README.md`, "The law's own words". The files are produced by script from the official
sources and never retyped. `python backend/apps/library/baseline/check_baseline.py`, run
without arguments, checks every file here; a tranche with no file yet is not checked.
