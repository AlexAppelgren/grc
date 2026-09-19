"""Routes of the library app (playbook 4.1: routes only). Chunk 1 adds the language
reference read for pickers (locale, tenant languages); instruments, provisions and
obligations follow in chunk 3."""

from django.http import HttpRequest
from ninja import Router

from apps.identity.schemas import RoleRef
from apps.library.models import Language
from apps.shared.authentication import SessionAuth

router = Router(tags=["Library"])


@router.get("/reference/languages", response=list[RoleRef], auth=SessionAuth(), operation_id="listLanguages", by_alias=True)
def list_languages(request: HttpRequest) -> list[RoleRef]:
    # Ungated by design: capability (any session; a reference read for pickers, I18N-01).
    return [
        RoleRef(key=language.key, kind=None, label=language.name)
        for language in Language.objects.filter(active=True).order_by("key")
    ]
