from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from pyppin.text.si_prefix import si_prefix


def now_and_then(
    now: Optional[datetime], then: datetime, julian: bool = False, format: Optional[str] = None
) -> str:
    """Output a string '{then}, {duration} ago' or '{then}, {duration} from now', or the like,
    expressing "then" in terms of "now." This tends to be useful in debugging and status pages.

    For hopefully obvious reasons, don't use this in outside-facing UI's; this code is 100%
    English-based, and would be virtually impossible to localize, as different cultures express
    temporal relationships differently.

    Args:
        now: The current time, which we use as a baseline. If not given, we use right now.
        then: The time we want to express
        julian: If True, use Julian (astronomical) years for intervals longer than a year;
            otherwise, use Gregorian years.
        format: If given, the format in which to print out 'now'. The default is to use ISO
            format.

    The argument order may seem a bit counterintuitive at first (why is the time we want to express
    the *second* argument??) but experiment shows it works well, because it matches the name of the
    function, which is also a common English idiom, and you usually have a variable named 'now'
    anyway!
    """
    if now is None:
        now = datetime.now(tz=then.tzinfo)
    then_str = then.isoformat() if format is None else then.strftime(format)
    return f'{then_str} ({time_delta_string(then - now, julian=julian)})'


# A couple of handy values to pass for the format in now_and_then.
LONG_FORMAT = '%A, %B %d, %Y %X'  # Monday, July 18, 2022 15:20:23
LOCAL_DATETIME = '%c'  # Wed Jul 18 15:20:23 1988
LOCAL_DATE_ONLY = '%x'
LOCAL_TIME_ONLY = '%X'


def time_delta_string(delta: timedelta, julian: bool = False) -> str:
    """Express a time delta in words, e.g. "15 seconds ago" or "3 years from now."

    Args:
        delta: The time to be expressed.
        julian: If True, use Julian (astronomical) years; otherwise, use Gregorian years.
    """
    if delta < _ZERO:
        return _time_delta_string(-delta, julian=julian) + " ago"
    elif delta > _ZERO:
        return _time_delta_string(delta, julian=julian) + " from now"
    else:
        return "Now"


def _time_delta_string(delta: timedelta, julian: bool = False) -> str:
    """Like time_delta_string, but only for positive values."""
    if delta <= _ZERO:
        raise ValueError('time_delta_string only accepts strictly positive values')

    interval = delta.total_seconds()

    if interval <= 1:
        return f'{si_prefix(interval)}sec'
    elif interval < 60:
        return f'{interval:0.1f} seconds'

    # Divide the interval into these units. For a handy mnemonic, remember that to within less than
    # a percent, pi seconds is a nanocentury!
    years, days, hours, minutes, seconds = _subdivide(
        interval, _JULIAN_SECONDS if julian else _GREGORIAN_SECONDS, 86400, 3600, 60
    )

    if years:
        return f'{years} years, {days} days, {hours}:{minutes:02d}:{seconds:02d}'
    elif days:
        return f'{days} days, {hours}:{minutes:02d}:{seconds:02d}'
    else:
        return f'{hours}:{minutes:02d}:{seconds:02d}'


def _subdivide(value: float, *chunks: int) -> Tuple[int, ...]:
    """Chop up a value into units. For example,

    _subdivide(100000, 86400, 3600, 60) = (1, 3, 46, 40)

    i.e., 100000 = 1 * 86400 + 3 * 3600 + 46 * 60 + 40

    If you pass N chunks, you will get back N+1 ints; the float remainder is dropped.
    """
    assert chunks
    result: List[int] = []
    for chunk in chunks:
        chunk_value = int(value // chunk)
        result.append(chunk_value)
        value -= chunk_value * chunk
    result.append(int(value))
    return tuple(result)


_ZERO = timedelta()
_JULIAN_SECONDS = 31557600
_GREGORIAN_SECONDS = 31556952
