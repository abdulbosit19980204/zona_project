from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/support/", include("support.urls")),
    path("api/inventory/", include("inventory.urls")),
    path("api/prbc/", include("prbc.urls")),
    path("api/docs/", include("zona.docs")),  # qo'llanma (docs/manual/*.md)
    path("", include("zona.urls")),  # boshqa loyihada odatda: path("zona/", include("zona.urls"))
]
