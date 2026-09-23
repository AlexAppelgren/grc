"""The real retriever of the release gate (SRC-05, AC-SRC1, playbook 16).

`scripts/search_eval.py --retriever apps.search.eval:Retriever` asks it the labelled
questions of `eval/retrieval.jsonl` and scores the stable keys it answers, best first. It
answers through `hybrid.run_search`, the statement `POST /search` runs, over the library
`seed_demo` loads from `apps/library/fixtures/prototype_data.json`, indexed and embedded the
way `reindex_library` and the sweep behind it leave it. The bank asking has narrowed
nothing, so the whole library is in its scope: a footprint with no terms restricts no
dimension (`apps/taxonomy/matching.py`). It asks for the widest page the API serves, so a
hit anywhere in the answer counts, which is what a question expecting no answer needs.

**Where the corpus lives: never in the development database.** A gate that seeded it would
file sample records among whatever a developer was doing there, and score whatever they had
changed. Inside the test runner (SRC-S8) the database already is the runner's throwaway
one, and the corpus is built in the test's own transaction. From the command line the
retriever does what the runner does: Django on `config.test_settings` (unless
DJANGO_SETTINGS_MODULE names another), a database created by Django's own test machinery
and migrated from zero, dropped when the process ends. It is named
`test_<database>_search_eval`, so it never collides with a `manage.py test` running in the
same worktree slot.

**Mock or real.** `is_mock` is true when any adapter in the chain is a mock — the embedder,
the reranker, or both — and `name` names each one, so the harness's report says which chain
ran and `--record` refuses a baseline a mock earned. `none` is not a mock: it is the
contracted state before D-09 names a model, the keyword leg and the fused order alone.
Under the test settings the embedder is always the mock, so no run of this retriever can be
recorded until a real model is configured (docs/TODO_FOR_alex.md, D-09).
"""

from __future__ import annotations

import atexit
import io
import os
import uuid
from datetime import date
from typing import TYPE_CHECKING

import django
from django.apps import apps as django_apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.backends.base.creation import TEST_DATABASE_PREFIX

from apps.shared.adapters import embedder, reranker

if TYPE_CHECKING:
    from apps.search.schemas import SearchHit

SPEC = "apps.search.eval:Retriever"
SCRATCH_SUFFIX = "_search_eval"


class Retriever:
    """`search(query, lang, as_of) -> [stable keys, best first]` over the fixture corpus.

    Models are imported inside the methods: the harness imports this module before Django
    is set up, and setting it up is the constructor's first job."""

    def __init__(self) -> None:
        _throwaway_database()
        self._tenant_id = _corpus()

    @property
    def name(self) -> str:
        return f"{SPEC} (embedder {embedder.get_embedder().name}, reranker {reranker.get_reranker().name})"

    @property
    def is_mock(self) -> bool:
        return isinstance(embedder.get_embedder(), embedder.MockEmbedder) or isinstance(
            reranker.get_reranker(), reranker.MockReranker
        )

    def search(self, query: str, lang: str, as_of: date | None) -> list[str]:
        from apps.search import hybrid
        from apps.search.schemas import SearchRequest
        from apps.shared import tenancy

        body = SearchRequest(q=query, lang=lang, as_of=as_of, limit=settings.API_PAGE_SIZE_MAX)
        with transaction.atomic():
            tenancy.activate(self._tenant_id)
            # A fresh caller per question: the rate limit is per person (NFR-02).
            hits = hybrid.run_search(body, tenant_id=self._tenant_id, user_id=uuid.uuid4()).items
            return _stable_keys(hits)


def _throwaway_database() -> None:
    """Django, and a database nobody else uses (see the module docstring)."""
    if not django_apps.ready:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")
        django.setup()
    named = connection.settings_dict["NAME"]
    if named.startswith(TEST_DATABASE_PREFIX):
        return
    connection.settings_dict["TEST"]["NAME"] = f"{TEST_DATABASE_PREFIX}{named}{SCRATCH_SUFFIX}"
    connection.creation.create_test_db(verbosity=0, autoclobber=True)
    atexit.register(connection.creation.destroy_test_db, named, verbosity=0)


def _corpus() -> uuid.UUID:
    """The fixture library, indexed and embedded, and the bank that searches it. Every step
    is idempotent, so a second retriever on the same database finds the corpus in place."""
    from apps.search import indexing
    from apps.shared import factories

    quiet = io.StringIO()
    call_command("seed_demo", stdout=quiet)
    call_command("reindex_library", stdout=quiet)
    indexing.embed_backlog()
    with transaction.atomic():
        return factories.tenant(name="Search evaluation").id


def _stable_keys(hits: list[SearchHit]) -> list[str]:
    """What the evaluation set names: a hit's record by its stable key, in the hit order."""
    from apps.library.models import Obligation, Provision
    from apps.watch.models import RegulatoryChange

    ids = [hit.id for hit in hits]
    keys = {
        row_id: key
        for model in (Obligation, Provision, RegulatoryChange)
        for row_id, key in model.objects.filter(id__in=ids).values_list("id", "stable_key")
    }
    return [keys[hit.id] for hit in hits]
