"""Xost loyihaning REST_FRAMEWORK sozlamalaridan mustaqil API asoslari."""
from rest_framework import viewsets
from rest_framework.decorators import (api_view, authentication_classes, parser_classes, permission_classes,
                                       renderer_classes)
from rest_framework.parsers import JSONParser
from rest_framework.renderers import JSONRenderer

from .auth import AUTHENTICATION
from .permissions import ReadOrEdit


def zona_api(methods, permissions):
    def wrap(fn):
        fn = authentication_classes(AUTHENTICATION)(fn)
        fn = permission_classes(permissions)(fn)
        fn = renderer_classes([JSONRenderer])(fn)
        fn = parser_classes([JSONParser])(fn)
        return api_view(methods)(fn)
    return wrap


class ZonaViewSet(viewsets.ModelViewSet):
    pagination_class = None
    authentication_classes = AUTHENTICATION
    permission_classes = [ReadOrEdit]
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser]
    filter_backends = []

    def next_order(self):
        model = self.get_queryset().model
        last = model.objects.order_by("-order").values_list("order", flat=True).first()
        return (last or 0) + 1
