"""The assistant. The model is always mocked; tests never call OpenRouter."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import AIUsage, ChatMessage, DayPlan, PlanEntry, Task
from ..services import ai, assistant, gcal
from .helpers import SignedInTestCase, fake_response, make_user


class ParseTests(TestCase):
    def test_reads_json_in_many_shapes(self):
        self.assertEqual(ai.parse_json('{"a": 1}'), {"a": 1})
        self.assertEqual(ai.parse_json('Sure!\n```json\n{"a": 2}\n```'), {"a": 2})
        self.assertEqual(ai.parse_json('Here: {"a": 3} hope that helps'), {"a": 3})
        for bad in ("no json", "[1, 2]", ""):
            with self.assertRaises(ai.AIError):
                ai.parse_json(bad)

    @override_settings(OPENROUTER_API_KEY="k", AI_MODEL="m1", AI_FALLBACK_MODELS=["m2"])
    @mock.patch("planner.services.ai.requests.post")
    def test_request_shape_and_fallbacks(self, post):
        post.return_value = fake_response(body={"choices": [{"message": {"content": '{"reply": "hi", "changes": []}'}}]})
        self.assertEqual(ai.complete_json([{"role": "user", "content": "x"}]), {"reply": "hi", "changes": []})
        payload = post.call_args.kwargs["json"]
        self.assertEqual((payload["model"], payload["models"]), ("m1", ["m1", "m2"]))
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer k")

    @override_settings(OPENROUTER_API_KEY="k")
    @mock.patch("planner.services.ai.requests.post", return_value=fake_response(502))
    def test_upstream_failure(self, post):
        with self.assertRaises(ai.AIError) as e:
            ai.complete_json([])
        self.assertEqual(e.exception.code, "upstream_error")

    @override_settings(OPENROUTER_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(ai.AIError) as e:
            ai.complete_json([])
        self.assertEqual(e.exception.code, "not_configured")


class ValidationTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.t = Task.objects.create(user=self.user, area=self.area(), title="Read")
        self.day = timezone.localdate().isoformat()

    def test_keeps_only_valid_changes(self):
        other = make_user("other@example.com")
        theirs = Task.objects.create(user=other, area=other.areas.first(), title="Theirs")
        raw = [
            {"type": "plan", "task": self.t.pk, "date": self.day, "slot": "morning", "label": "ok"},
            {"type": "plan", "task": theirs.pk, "date": self.day, "slot": "morning"},  # someone else's task
            {"type": "plan", "task": self.t.pk, "date": "tomorrow", "slot": "morning"},  # bad date
            {"type": "plan", "task": self.t.pk, "date": self.day, "slot": "dawn"},  # bad slot
            {"type": "delete_everything"},  # unknown
            {"type": "add_task", "title": "  "},  # empty
            {"type": "add_task", "title": "Gym", "area": "personal", "minutes": 9999, "priority": "urgent"},
            {"type": "block_time", "task": "new:0", "date": self.day, "start": "18:30", "minutes": 60},
            {"type": "block_time", "task": self.t.pk, "date": self.day, "start": "25:00", "minutes": 60},
            {"type": "set_top3", "date": self.day, "tasks": [self.t.pk, theirs.pk, "new:0", "new:5"]},
            "not a dict",
        ]
        out = assistant.validate_changes(self.user, raw)
        self.assertEqual([c["type"] for c in out], ["plan", "add_task", "block_time", "set_top3"])
        gym = out[1]
        self.assertEqual((gym["area"], gym["minutes"]), ("Personal", 720))
        self.assertNotIn("priority", gym)
        self.assertEqual(out[3]["tasks"], [self.t.pk, "new:0"])

    def test_not_a_list(self):
        self.assertEqual(assistant.validate_changes(self.user, {"type": "plan"}), [])


class ApplyTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.t = Task.objects.create(user=self.user, area=self.area(), title="Read")

    def msg(self, changes):
        changes = assistant.validate_changes(self.user, changes)
        return ChatMessage.objects.create(user=self.user, role="assistant", content="Plan:", changes=changes, status="pending")

    def test_applies_only_chosen_changes(self):
        m = self.msg([
            {"type": "add_task", "title": "Gym", "area": "Personal", "minutes": 60, "energy": "easy"},
            {"type": "plan", "task": "new:0", "date": self.today.isoformat(), "slot": "evening"},
            {"type": "complete", "task": self.t.pk},
        ])
        self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0", "1"]})
        gym = Task.objects.get(title="Gym")
        self.assertEqual((gym.area.name, gym.energy), ("Personal", "easy"))
        self.assertEqual(PlanEntry.objects.get().task, gym)
        self.t.refresh_from_db()
        self.assertFalse(self.t.done)
        m.refresh_from_db()
        self.assertEqual((m.status, m.applied), ("applied", [0, 1]))

    def test_plan_for_unchosen_new_task_is_dropped(self):
        m = self.msg([
            {"type": "add_task", "title": "Gym"},
            {"type": "plan", "task": "new:0", "date": self.today.isoformat(), "slot": "evening"},
        ])
        self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["1"]})
        self.assertFalse(Task.objects.filter(title="Gym").exists())
        self.assertFalse(PlanEntry.objects.exists())

    def test_cannot_apply_twice(self):
        m = self.msg([{"type": "complete", "task": self.t.pk}])
        self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0"]})
        self.t.set_done(False)
        self.t.save()
        r = self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0"]})
        self.assertIn("already handled", r["HX-Trigger"])
        self.t.refresh_from_db()
        self.assertFalse(self.t.done)

    def test_set_top3_and_update(self):
        m = self.msg([
            {"type": "update_task", "task": self.t.pk, "due": self.today.isoformat(), "priority": "high"},
            {"type": "set_top3", "date": self.today.isoformat(), "tasks": [self.t.pk]},
        ])
        self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0", "1"]})
        self.t.refresh_from_db()
        self.assertEqual((self.t.due_date, self.t.priority), (self.today, "high"))
        self.assertEqual(list(DayPlan.objects.get(date=self.today).top_tasks.all()), [self.t])

    @mock.patch.object(gcal, "create_block")
    def test_block_time_plans_and_adds_to_calendar(self, create_block):
        m = self.msg([{"type": "block_time", "task": self.t.pk, "date": self.today.isoformat(), "start": "14:30", "minutes": 90}])
        self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0"]})
        self.assertEqual(PlanEntry.objects.get().slot, "afternoon")
        create_block.assert_called_once_with(self.user, self.t, self.today, 14 * 60 + 30, 90)

    @mock.patch.object(gcal, "create_block", side_effect=gcal.CalendarError("reconnect", "Reconnect Google."))
    def test_calendar_failure_is_reported_but_plan_kept(self, create_block):
        m = self.msg([{"type": "block_time", "task": self.t.pk, "date": self.today.isoformat(), "start": "09:00", "minutes": 30}])
        r = self.hx_post(f"/assistant/{m.pk}/apply/", {"change": ["0"]})
        self.assertIn("Couldn", r["HX-Trigger"])
        self.assertTrue(PlanEntry.objects.exists())

    def test_skip(self):
        m = self.msg([{"type": "complete", "task": self.t.pk}])
        self.hx_post(f"/assistant/{m.pk}/skip/")
        m.refresh_from_db()
        self.assertEqual(m.status, "skipped")

    def test_other_users_message(self):
        other = make_user("other@example.com")
        m = ChatMessage.objects.create(user=other, role="assistant", content="x", changes=[], status="pending")
        self.assertEqual(self.client.post(f"/assistant/{m.pk}/apply/").status_code, 404)


@override_settings(OPENROUTER_API_KEY="test-key", AI_DAILY_LIMIT=2)
class AskTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.t = Task.objects.create(user=self.user, area=self.area(), title="Grade psets", due_date=timezone.localdate())

    @mock.patch.object(ai, "complete_json")
    def test_ask_saves_reply_and_proposal(self, complete):
        today = timezone.localdate().isoformat()
        complete.return_value = {"reply": "Morning works.", "changes": [
            {"type": "plan", "task": self.t.pk, "date": today, "slot": "morning", "label": "Plan grading this morning"}]}
        r = self.client.post("/assistant/ask/", {"text": "Plan my day"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Morning works.")
        self.assertContains(r, "Plan grading this morning")
        self.assertContains(r, "Do it")
        prompt = complete.call_args[0][0]
        self.assertEqual(prompt[0]["role"], "system")
        self.assertIn('"title": "Grade psets"', prompt[0]["content"])
        self.assertIn("Google Calendar: not connected", prompt[0]["content"])
        self.assertEqual(prompt[-1], {"role": "user", "content": "Plan my day"})

    @mock.patch.object(ai, "complete_json", return_value={"reply": "ok", "changes": []})
    def test_daily_limit(self, complete):
        for _ in range(3):
            self.client.post("/assistant/ask/", {"text": "hi"})
        self.assertEqual(complete.call_count, 2)
        self.assertEqual(AIUsage.objects.get(user=self.user).count, 2)
        self.assertTrue(ChatMessage.objects.filter(is_error=True, content__contains="today’s assistant limit").exists())

    @mock.patch.object(ai, "complete_json", side_effect=ai.AIError("invalid_json"))
    def test_model_failure_is_explained(self, complete):
        self.client.post("/assistant/ask/", {"text": "hi"})
        self.assertTrue(ChatMessage.objects.filter(is_error=True, content__contains="garbled").exists())

    @mock.patch.object(ai, "complete_json", return_value={"reply": "ok", "changes": []})
    def test_errors_are_left_out_of_history(self, complete):
        ChatMessage.objects.create(user=self.user, role="assistant", content="boom", is_error=True)
        self.client.post("/assistant/ask/", {"text": "hi"})
        contents = [m["content"] for m in complete.call_args[0][0]]
        self.assertNotIn("boom", contents)

    def test_home_shows_assistant(self):
        r = self.client.get("/")
        self.assertContains(r, "Your assistant")
        self.assertContains(r, "2 left today")

    def test_clear_chat(self):
        ChatMessage.objects.create(user=self.user, role="user", content="x")
        self.hx_post("/assistant/clear/")
        self.assertFalse(ChatMessage.objects.exists())


class ContextTests(SignedInTestCase):
    def test_context_lists_free_time_and_tasks(self):
        Task.objects.create(user=self.user, area=self.area(), title="Essay", due_date=timezone.localdate() + timedelta(days=1))
        text = assistant.context_for(self.user)
        self.assertIn('"title": "Essay"', text)
        self.assertIn("morning (8am–12pm, 240 free min)", text)
        self.assertIn("Personal (personal time)", text)
