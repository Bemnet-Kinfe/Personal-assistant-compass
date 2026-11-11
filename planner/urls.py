from django.urls import path

from .views import common
from .views import tasks
from .views import plan
from .views import checkins
from .views import calendar

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
    path("check-in/daily/", checkins.checkin_daily, name="checkin_daily"),
    path("check-in/daily/carry/", checkins.carry_over, name="carry_over"),
    path("check-in/daily/finish/", checkins.finish_day, name="finish_day"),
    path("check-in/weekly/", checkins.checkin_weekly, name="checkin_weekly"),
    path("tasks/<int:pk>/reschedule/", checkins.task_reschedule, name="task_reschedule"),
    path("settings/calendar/sync/", calendar.calendar_sync_now, name="calendar_sync"),
]
