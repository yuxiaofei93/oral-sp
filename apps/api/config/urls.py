from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("modules.accounts.urls")),
    path("api/health/", include("modules.core.urls")),
    path("api/teacher/cases/", include("modules.cases.urls")),
    path("api/teacher/teaching/", include("modules.teaching.urls")),
    path("api/", include("modules.simulation.urls")),
]
