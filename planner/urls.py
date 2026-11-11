from django.urls import path

from .views import common
from .views import tasks
from .views import plan

urlpatterns = [
    path("", common.home, name="home"),
    path("healthz", common.healthz, name="healthz"),
    path("tasks/", tasks.tasks, name="tasks"),
    path("tasks/new/", tasks.task_new, name="task_new"),
    path("tasks/<int:pk>/", tasks.task_edit, name="task_edit"),
    path("tasks/<int:pk>/toggle/", tasks.task_toggle, name="task_toggle"),
    path("tasks/<int:pk>/delete/", tasks.task_delete, name="task_delete"),
    path("settings/", tasks.settings_page, name="settings"),
    path("settings/areas/", tasks.area_save, name="area_add"),
    path("settings/areas/<int:pk>/", tasks.area_save, name="area_save"),
    path("settings/areas/<int:pk>/delete/", tasks.area_delete, name="area_delete"),
    path("plan/", plan.plan, name="plan"),
    path("plan/pick/<str:date>/<str:slot>/", plan.plan_pick, name="plan_pick"),
    path("plan/add/", plan.plan_add, name="plan_add"),
    path("plan/entry/<int:pk>/remove/", plan.plan_remove, name="plan_remove"),
    path("plan/star/", plan.plan_star, name="plan_star"),
]
