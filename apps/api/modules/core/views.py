from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


@never_cache
@api_view(["GET"])
@permission_classes([AllowAny])
def live(request):
    return JsonResponse({"status": "ok", "service": "oral-sp-api"})


@never_cache
@api_view(["GET"])
@permission_classes([AllowAny])
def ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "error"}, status=503)
    return JsonResponse({"status": "ok", "database": "ready"})

