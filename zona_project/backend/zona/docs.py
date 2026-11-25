"""Qo'llanma (/api/docs/): tizimning to'liq yo'riqnomasi — repo'dagi docs/manual/*.md fayllaridan.

Fayllar kod bilan birga yangilanadi (har o'zgarishda tegishli bob ham yangilanadi). Fayl nomi: "02-support-bot.md" —
raqam tartibni, qolgani manzilni (slug) beradi; birinchi "# Sarlavha" qatori — bob nomi, undan keyingi "> ..." —
qisqa tavsif."""
import re
from pathlib import Path

from django.conf import settings
from django.urls import path
from rest_framework import status
from rest_framework.response import Response

from .api import zona_api
from .permissions import CanView

NAME = re.compile(r"^(\d+)-([a-z0-9-]+)\.md$")


def manual_dir():
    return Path(getattr(settings, "MANUAL_DIR", "") or Path(settings.BASE_DIR).parent / "docs" / "manual")


def _chapters():
    out = []
    d = manual_dir()
    if not d.is_dir():
        return out
    for f in sorted(d.iterdir()):
        m = NAME.match(f.name)
        if not m:
            continue
        text = f.read_text(encoding="utf-8")
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), m.group(2))
        desc = next((ln[1:].strip() for ln in text.splitlines() if ln.startswith(">")), "")
        out.append({"slug": m.group(2), "order": int(m.group(1)), "title": title, "description": desc,
                    "file": f.name, "updated": f.stat().st_mtime, "text": text})
    return out


@zona_api(["GET"], [CanView])
def chapters(request):
    """Boblar ro'yxati; ?q=so'z — matn bo'yicha qidiruv (qaysi bobda va nechta)."""
    q = (request.query_params.get("q") or "").strip().lower()
    rows = []
    for c in _chapters():
        hits = c["text"].lower().count(q) if q else 0
        if q and not hits:
            continue
        rows.append({k: c[k] for k in ("slug", "order", "title", "description", "updated")} | ({"hits": hits} if q else {}))
    return Response(rows)


@zona_api(["GET"], [CanView])
def chapter(request, slug):
    for c in _chapters():
        if c["slug"] == slug:
            return Response({k: c[k] for k in ("slug", "order", "title", "description", "updated", "text")})
    return Response({"detail": "Bob topilmadi"}, status=status.HTTP_404_NOT_FOUND)


urlpatterns = [
    path("", chapters, name="docs"),
    path("<slug:slug>/", chapter, name="docs-chapter"),
]
