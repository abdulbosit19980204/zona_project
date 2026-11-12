"""Frontend boshqa domendan ishlaganda CORS. Xost MIDDLEWARE ro'yxatining boshiga qo'shiladi:

    "zona.middleware.ZonaCorsMiddleware",

va settings: ZONA = {"CORS_ORIGINS": ["https://zona.example.uz"]}
Faqat zona API manzillariga (…/api/…) ta'sir qiladi.
"""
from django.http import HttpResponse

from . import conf


class ZonaCorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin and origin in conf.get("CORS_ORIGINS") and "/api/" in request.path
        if allowed and request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRFToken"
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            response["Access-Control-Max-Age"] = "600"
            response["Vary"] = "Origin"
        return response
