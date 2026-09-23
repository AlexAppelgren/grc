"""The real retriever of the release gate (SRC-05, AC-SRC1, playbook 16).

`scripts/search_eval.py --retriever apps.search.eval:Retriever` asks it the labelled
questions of `eval/retrieval.jsonl` and scores the stable keys it answers, best first. It
answers through `hybrid.run_search`, the statement `POST /search` runs, over the library
`seed_demo` loads from `apps/library/fixtures/prototype_data.json`, indexed and embedded the
way `reindex_library` and the sweep behind it leave it. The bank asking has narrowed
nothing, so the whole library is in its scope: a footprint with no terms restricts no
dimension (`apps/taxonomy/matching.py`). It asks for the widest page the API serves, so a
hit anywhere in the answer counts, which is what a question expecting no answer needs.

**The day it asks on is the corpus's, not the calendar's.** The fixture is dated around its
own anchor day (`_meta.anchor_date`), and a question without an `as_of` is asked on that
day. Asked on today's date instead, a version that comes into force next month would change
the text searched, and the score, with no change to the code or the corpus.

**Where the corpus lives: never in the development database.** A gate that seeded it would
file sample records among whatever a developer was doing there, and score whatever they had
changed. Inside the test runner (SRC-S8) the database already is the runner's throwaway
one, and the corpus is built in the test's own transaction. From the command line the
retriever does what the runner does, with the runner's own `setup_databases`: Django on
`config.test_settings` (unless DJANGO_SETTINGS_MODULE names another), a database migrated
from zero, every alias that mirrors `default` (`app`, the production role) pointed at it,
and all of it dropped when the process ends. It is named
`test_<database>_search_eval_<process id>`, so it collides neither with a `manage.py test`
in the same worktree slot nor with a second evaluation running beside it.

The tenant that asks is made with the test factory, deliberately: this code runs only in a
throwaway database (`seed_demo` also refuses a deployed one), and a bank made there needs
no audit trail. It is found by its slug before it is made, so every step of building the
corpus is idempotent and four retrievers in one test share one bank.

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
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.db.backends.base.creation import TEST_DATABASE_PREFIX
from django.test.utils import setup_databases, teardown_databases

from apps.shared.adapters import embedder, reranker

if TYPE_CHECKING:
    from django.db.backends.base.base import BaseDatabaseWrapper

SPEC = "apps.search.eval:Retriever"
SCRATCH_SUFFIX = "_search_eval"
TENANT_SLUG = "search-evaluation"


class Retriever:
    """`search(query, lang, as_of) -> [stable keys, best first]` over the fixture corpus.

    Models are imported inside the methods: the harness imports this module before Django
    is set up, and setting it up is the constructor's first job."""

    def __init__(self) -> None:
        _throwaway_database()
        from apps.taxonomy.seeds import fixture  # a models import: only once Django is set up

        self._tenant_id = _corpus()
        self._anchor = date.fromisoformat(fixture.load()["_meta"]["anchor_date"])

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

        body = SearchRequest(q=query, lang=lang, as_of=as_of or self._anchor, limit=settings.API_PAGE_SIZE_MAX)
        with transaction.atomic():
            tenancy.activate(self._tenant_id)
            # A fresh caller per question: the rate limit is per person (NFR-02).
            hits = hybrid.run_search(body, tenant_id=self._tenant_id, user_id=uuid.uuid4()).items
            return _stable_keys([hit.id for hit in hits])

    def ask(self, query: str, lang: str, as_of: date | None) -> list[str]:
        """What Ask would give a model for the question: `hybrid.passages`, the read
        `POST /ask` makes, at the depth it makes it. A question about a standard's control
        expects nothing here although Search finds the conformance duty (SRC-S12, D-81)."""
        from apps.search import hybrid
        from apps.shared import tenancy
        from apps.shared.models import Tenant

        with transaction.atomic():
            tenancy.activate(self._tenant_id)
            rows = hybrid.passages(
                query,
                tenant=Tenant.objects.get(pk=self._tenant_id),
                lang=lang,
                as_of=as_of or self._anchor,
                depth=settings.ASK_RETRIEVAL_DEPTH,
            )
            return _stable_keys([row["record_id"] for row in rows])


def _throwaway_database() -> None:
    """Django, and a database nobody else uses (see the module docstring)."""
    if not django_apps.ready:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.test_settings")
        django.setup()
    named = connection.settings_dict["NAME"]
    if named.startswith(TEST_DATABASE_PREFIX):
        return
    connection.settings_dict["TEST"]["NAME"] = f"{TEST_DATABASE_PREFIX}{named}{SCRATCH_SUFFIX}_{os.getpid()}"
    # `aliases` maps an alias to whether its contents are serialized, the shape the runner passes.
    created = setup_databases(verbosity=0, interactive=False, aliases={DEFAULT_DB_ALIAS: False}, serialized_aliases=set())
    atexit.register(_drop, created)


def _drop(created: list[tuple[BaseDatabaseWrapper, str, bool]]) -> None:
    # A session still open on the scratch database, a mirror's included, would refuse the drop.
    connections.close_all()
    teardown_databases(created, verbosity=0)


def _corpus() -> uuid.UUID:
    """The fixture library, indexed and embedded, and the bank that searches it. Every step
    is idempotent, so a second retriever on the same database finds the corpus in place."""
    from apps.search import indexing
    from apps.shared import factories
    from apps.shared.models import Tenant

    quiet = io.StringIO()
    call_command("seed_demo", stdout=quiet)
    call_command("reindex_library", stdout=quiet)
    indexing.embed_backlog()
    with transaction.atomic():
        found = Tenant.objects.filter(slug=TENANT_SLUG).first()  # ordering: the slug is unique
        return found.id if found else factories.tenant(name="Search evaluation", slug=TENANT_SLUG).id


def _stable_keys(ids: list[uuid.UUID]) -> list[str]:
    """What the evaluation set names: each record by its stable key, in the order given."""
    from apps.library.models import Obligation, Provision
    from apps.watch.models import RegulatoryChange

    keys = {
        row_id: key
        for model in (Obligation, Provision, RegulatoryChange)
        for row_id, key in model.objects.filter(id__in=ids).values_list("id", "stable_key")
    }
    return [keys[row_id] for row_id in ids]
