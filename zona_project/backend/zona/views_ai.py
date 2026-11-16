"""AI endpointlari. AI ishlamasa ham foydalanuvchi bo'sh qolmaydi: mahalliy qidiruv natijasi qaytadi."""
from rest_framework import status
from rest_framework.response import Response

from .ai import service
from .ai.providers import AIError
from .api import zona_api
from .models import Member, Task
from .permissions import CanView, ReadOrEdit
from .search import search as run_search


def _hints(found):
    names = dict(Member.objects.values_list("id", "name"))
    titles = dict(Task.objects.filter(id__in=[t["id"] for t in found["tasks"][:6]]).values_list("id", "title"))
    lines = [f"- xodim {p['member']} ({names.get(p['member'], '?')}), ishonch {p['confidence']}%" for p in found["people"][:3]]
    lines += [f"- vazifa {t['id']}: {titles.get(t['id'], '')}" for t in found["tasks"][:6]]
    return "\n".join(lines)


@zona_api(["POST"], [CanView])
def route(request):
    question = str(request.data.get("question", "")).strip()[:2000]
    if len(question) < 3:
        return Response({"question": "Savolni yozing."}, status=status.HTTP_400_BAD_REQUEST)
    found = run_search(question)
    try:
        result, meta = service.route(question, request.user, hints=_hints(found))
    except AIError as e:
        return Response({"source": "search", "search": found, "ai_error": str(e),
                         "ai_unavailable": isinstance(e, service.AIUnavailable)})
    return Response({"source": "ai", "search": found, **result, "meta": meta})


@zona_api(["POST"], [CanView])
def person(request):
    try:
        member = int(request.data.get("member"))
    except (TypeError, ValueError):
        return Response({"member": "Xodim id kerak."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        result, meta = service.person(member, request.user, str(request.data.get("lang") or "uz"))
    except AIError as e:
        return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({**result, "meta": meta})


@zona_api(["POST"], [ReadOrEdit])
def audit(request):
    try:
        result, meta = service.audit(request.user, str(request.data.get("lang") or "uz"))
    except AIError as e:
        return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({**result, "meta": meta})


@zona_api(["POST"], [CanView])
def workload(request):
    """Yuklama tahlili (vaqt asosida): ortiqcha yuklama, tavsiyalar, zonalar bo'yicha eng mos xodim."""
    try:
        result, meta = service.workload(request.user, str(request.data.get("lang") or "uz"))
    except AIError as e:
        return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({**result, "meta": meta})


@zona_api(["POST"], [ReadOrEdit])
def estimate(request):
    """Savollarga vaqtni AI bilan taxminlash (qo'lda kiritilganlarga tegilmaydi)."""
    try:
        result, meta = service.estimate_times(request.user)
    except AIError as e:
        return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({**result, "meta": meta})


@zona_api(["POST"], [ReadOrEdit])
def estimate_rules(request):
    """Qoida bo'yicha (AI'siz) boshlang'ich taxmin: faqat vaqti avtomatik bo'lgan savollar uchun."""
    from . import timeload
    return Response({"updated": timeload.apply_estimates()})
