from django.contrib import admin

from .models import AIUsage, Area, CalendarEvent, CalendarSync, ChatMessage, DayPlan, PlanEntry, Task, WeeklyCheckIn


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "color", "position")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "area", "due_date", "priority", "done")
    list_filter = ("done", "priority", "energy")
    search_fields = ("title",)


class PlanEntryInline(admin.TabularInline):
    model = PlanEntry
    extra = 0


@admin.register(DayPlan)
class DayPlanAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "checked_in_at")
    inlines = [PlanEntryInline]


admin.site.register(WeeklyCheckIn)
admin.site.register(CalendarSync)


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "calendar_name", "start", "all_day_date")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "role", "status")


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ("day", "user", "count")
