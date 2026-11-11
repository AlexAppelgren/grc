"""`manage.py file_library_baseline`: file the library baseline's due entries as proposals of
the platform agent `library-baseline`, after registering the sources it names (ADR 0065,
D-118; apps/proposals/baseline.py). The beat runs the same every
`LIBRARY_BASELINE_FILING_MINUTES`; this is for a first run by hand or `--dry-run`.

Run it after `seed_reference`, approve the instruments, run it again for their duties. Every
run is idempotent and never refiles an unchanged entry that was decided."""

from __future__ import annotations

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from apps.proposals import baseline


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
            counts = {
                state: sum(tally[(tranche, kind)] for kind in (baseline.INSTRUMENT, baseline.OBLIGATION))
                for state, tally in (("held", report.held), ("open", report.open), ("decided", report.decided))
            }
            self.stdout.write(
                f"{tranche}: {verb} {report.filed[(tranche, baseline.INSTRUMENT)]} instruments and "
                f"{report.filed[(tranche, baseline.OBLIGATION)]} duties; {report.waiting[tranche]} duties wait for their "
                f"instrument's approval; {counts['held']} already in the library, {counts['open']} open in the queue, "
                f"{counts['decided']} decided before"
            )
        for key, code, detail in report.refused:
            self.stderr.write(f"refused {key}: {code}: {detail}")
        self.stdout.write(f"runs: {report.runs}, refused: {len(report.refused)}")
