from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("zona.urls")),  # boshqa loyihada odatda: path("zona/", include("zona.urls"))
]
