#!/usr/bin/env python
"""Django's command-line utility. The settings module defaults to config.settings; the
canonical gate commands pass --settings=config.test_settings explicitly (playbook App. D)."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
