from django.urls import path

from .views import common

urlpatterns = [
    path("", common.home, name="home"),
    path("healthz", common.healthz, name="healthz"),
]
