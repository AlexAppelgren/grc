"""`manage.py file_library_baseline`: file the library baseline's due entries as proposals of
the platform agent `library-baseline`, after registering the sources it names (ADR 0065,
D-118; apps/proposals/baseline.py). The beat runs the same every
`LIBRARY_BASELINE_FILING_MINUTES`; this is for a first run by hand or `--dry-run`.

Run it after `seed_reference`, approve the instruments, run it again for their duties and
summaries, approve the duties, and run it once more for the provisions that cite them and the
corrections of those duties. Every run is idempotent and never refiles an unchanged entry that
was decided."""

from __future__ import annotations

from argparse import ArgumentParser
from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from apps.proposals import baseline

# Each kind the filing files, as the summary names it.
NOUNS = (
    (baseline.INSTRUMENT, "instruments"),
    (baseline.OBLIGATION, "duties"),
    (baseline.SUMMARY, "summaries"),
    (baseline.PROVISION, "provisions"),
    (baseline.CORRECTION, "corrections"),
)


def _counted(tally: Counter[tuple[str, str]], tranche: str) -> str:
    return ", ".join(f"{tally[(tranche, kind)]} {noun}" for kind, noun in NOUNS)


class Command(BaseCommand):
    help = "File the library baseline's entries the library does not hold as proposals for review."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--tranche", action="append", default=[], help="Only this tranche (repeatable). Default: every tranche.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would be filed and file nothing.")

    def handle(self, *args: Any, **options: Any) -> None:  # compliance: allow-kwargs Django command signature
        try:
            if not options["dry_run"]:
                self.stdout.write(f"sources registered: {baseline.register_sources()}")
            report = baseline.file(only=options["tranche"], dry_run=options["dry_run"])
        except ValidationError as error:
            raise CommandError(" ".join(error.messages)) from error
        verb = "would file" if options["dry_run"] else "filed"
        for tranche in baseline.tranches():
            if options["tranche"] and tranche not in options["tranche"]:
                continue
            # A duty and a summary wait for their instrument's approval, a provision for its duties',
            # a correction for its duty's and those of the provisions it names.
            self.stdout.write(
                f"{tranche}: {verb} {_counted(report.filed, tranche)}; waiting for an approval: {_counted(report.waiting, tranche)}; "
                f"already in the library: {_counted(report.held, tranche)}; open in the queue: {_counted(report.open, tranche)}; "
                f"decided before: {_counted(report.decided, tranche)}"
            )
        for key, code, detail in report.refused:
            self.stderr.write(f"refused {key}: {code}: {detail}")
        self.stdout.write(f"runs: {report.runs}, refused: {len(report.refused)}")
