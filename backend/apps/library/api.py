"""Routes of the library app (playbook 4.1: routes only). Chunk 1 adds the language
reference read for pickers (locale, tenant languages); chunk 3 adds the library reads,
beginning with the obligations list.

A library record read serves a person with `library.read` and an agent's key with
`library:read`, so it is a logic gate (apps/taxonomy/http.py `require_library_read`) and
listed in `UNGATED_BY_DESIGN`; `answers_problems` is always innermost."""

from django.http import HttpRequest
from ninja import Query, Router

from apps.identity.schemas import RoleRef
from apps.library import reading
from apps.library.models import Language
from apps.library.schemas import ObligationPage, ObligationQuery
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import answers_problems, caller_tenant, require_library_read
from apps.taxonomy.reading import language_order

router = Router(tags=["Library"])

SESSION_OR_KEY = [SessionAuth(), ApiKeyAuth()]


@router.get("/reference/languages", response=list[RoleRef], auth=SessionAuth(), operation_id="listLanguages", by_alias=True)
def list_languages(request: HttpRequest) -> list[RoleRef]:
    # Ungated by design: capability (any session; a reference read for pickers, I18N-01).
    return [
        RoleRef(key=language.key, kind=None, label=language.name)
        for language in Language.objects.filter(active=True).order_by("key")
    ]


@router.get("/obligations", response=ObligationPage, auth=SESSION_OR_KEY, operation_id="listObligations", by_alias=True)
@answers_problems
def list_obligations(request: HttpRequest, query: Query[ObligationQuery], page: Query[PageQuery]) -> ObligationPage:
    # Ungated by design: logic-gate (library.read in a tenant, or a key with library:read; INV-03, AGT-02).
    require_library_read(request)
    tenant = caller_tenant(request)
    order = language_order(request, tenant=tenant)
    items, total = reading.obligation_page(tenant, order, query, limit=page.limit, offset=page.offset)
    return ObligationPage(items=items, total=total)
