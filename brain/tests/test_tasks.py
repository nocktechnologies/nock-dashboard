from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from brain.models import MorningNoteSent
from brain.tasks import check_missed_morning_note


def _make_localtime(hour: int) -> datetime:
    """Return a timezone-aware datetime for today at the given hour."""
    now = timezone.now()
    return now.replace(hour=hour, minute=30, second=0, microsecond=0)


class CheckMissedMorningNoteTest(TestCase):
    """Tests for the worker_ready missed-morning-note recovery handler."""

    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_does_not_fire_before_6am(self, mock_localtime, mock_task):
        mock_localtime.return_value = _make_localtime(5)
        check_missed_morning_note(sender=None)
        mock_task.delay.assert_not_called()

    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_does_not_fire_after_noon(self, mock_localtime, mock_task):
        mock_localtime.return_value = _make_localtime(12)
        check_missed_morning_note(sender=None)
        mock_task.delay.assert_not_called()

    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_fires_when_missed(self, mock_localtime, mock_task):
        """Between 6-12 with no MorningNoteSent today -> should fire."""
        fake_now = _make_localtime(8)
        mock_localtime.return_value = fake_now
        check_missed_morning_note(sender=None)
        mock_task.delay.assert_called_once()

    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_does_not_fire_when_already_ran(self, mock_localtime, mock_task):
        """Between 6-12 but MorningNoteSent exists today -> should NOT fire."""
        fake_now = _make_localtime(8)
        mock_localtime.return_value = fake_now
        MorningNoteSent.objects.create(date=fake_now.date())
        check_missed_morning_note(sender=None)
        mock_task.delay.assert_not_called()

    @override_settings(MORNING_NOTE_ENABLED=False)
    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_disabled_setting_skips(self, mock_localtime, mock_task):
        """When MORNING_NOTE_ENABLED=False, recovery should not fire."""
        mock_localtime.return_value = _make_localtime(8)
        check_missed_morning_note(sender=None)
        mock_task.delay.assert_not_called()

    def test_daily_maintenance_importable_and_callable(self):
        """daily_maintenance task should be importable and delay-able."""
        from brain.tasks import daily_maintenance

        assert callable(daily_maintenance)
        assert callable(daily_maintenance.delay)

    @patch("brain.tasks.daily_maintenance")
    @patch("brain.tasks.tz.localtime")
    def test_does_not_create_record_directly(self, mock_localtime, mock_task):
        """Recovery handler should not create MorningNoteSent — daily_maintenance does."""
        fake_now = _make_localtime(8)
        mock_localtime.return_value = fake_now
        check_missed_morning_note(sender=None)
        assert not MorningNoteSent.objects.filter(date=fake_now.date()).exists()
