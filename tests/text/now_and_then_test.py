import unittest
from datetime import datetime, timedelta

from pyppin.text.now_and_then import Formats, now_and_then, relative_time_string


class NowAndThenTest(unittest.TestCase):
    def test_relative_time_string(self) -> None:
        self.assertEqual(
            "110.0msec from now", relative_time_string(timedelta(seconds=0.11))
        )
        self.assertEqual(
            "12.1 seconds ago", relative_time_string(timedelta(seconds=-12.1))
        )
        self.assertEqual(
            "0:43:14 from now", relative_time_string(timedelta(minutes=43, seconds=14))
        )
        self.assertEqual(
            "3 days, 4:25:00 ago",
            relative_time_string(-timedelta(days=3, hours=4, minutes=25)),
        )
        # Remember that a Gregorian year isn't an integer number of days! It's 365.2425 days.
        self.assertEqual(
            "12 years, 17 days, 7:29:36 from now",
            relative_time_string(timedelta(days=4400, hours=5, minutes=20)),
        )
        # But Julian years are precisely 365.25 days.
        self.assertEqual(
            "12 years, 17 days, 5:20:00 ago",
            relative_time_string(
                -timedelta(days=4400, hours=5, minutes=20), julian=True
            ),
        )

    def test_now_and_then(self) -> None:
        time1 = datetime(2022, 7, 1)
        time2 = datetime(2022, 7, 18, 15, 22, 23)

        # Let 'now' be 7/1, and 'then' be 7/18, a day in the future.
        self.assertEqual(
            "Monday, July 18, 2022 15:22:23 (17 days, 15:22:23 from now)",
            now_and_then(time1, time2, format=Formats.LONG_FORMAT),
        )

        # Other way round, and let's use ISO format.
        self.assertEqual(
            "2022-07-01T00:00:00 (17 days, 15:22:23 ago)", now_and_then(time2, time1)
        )
