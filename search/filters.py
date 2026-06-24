from datetime import date, time, timedelta
from typing import Optional


def to_absolute_minutes(t: time, day_offset: int) -> int:
    """Converts time + day_offset to minutes from journey start."""
    return (day_offset * 1440) + (t.hour * 60) + t.minute


def get_transfer_weekday(journey_date: date, leg1_arrival_offset: int) -> int:
    """
    Returns weekday index (0=Mon, 6=Sun) of the day
    leg2 is actually needed — accounts for overnight leg1.
    """
    transfer_date = journey_date + timedelta(days=leg1_arrival_offset)
    return transfer_date.weekday()


def train_runs_on_day(service_days: str, weekday: int) -> bool:
    """
    Checks if a train runs on a given weekday.
    weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    """
    if not service_days:
        return True   # assume runs if data missing

    service_days = service_days.strip().lower()

    day_map = {
        0: ["mon", "monday"],
        1: ["tue", "tuesday"],
        2: ["wed", "wednesday"],
        3: ["thu", "thursday"],
        4: ["fri", "friday"],
        5: ["sat", "saturday"],
        6: ["sun", "sunday"],
    }

    aliases = day_map.get(weekday, [])
    return any(alias in service_days for alias in aliases)


def is_valid_transfer(
    leg1_arrival_time:     time,
    leg1_arrival_offset:   int,
    leg2_departure_time:   time,
    leg2_departure_offset: int,
    leg2_service_days:     str,
    journey_date:          date,
    min_buffer_minutes:    int = 30,
    max_wait_minutes:      int = 360,
) -> tuple[bool, Optional[str], int]:
    """
    Returns (is_valid, rejection_reason, gap_minutes).
    gap_minutes is returned even on rejection for debugging.
    """

    # Gate 1: does leg2 run on the day it's needed?
    transfer_weekday = get_transfer_weekday(journey_date, leg1_arrival_offset)
    if not train_runs_on_day(leg2_service_days, transfer_weekday):
        return False, "leg2_not_running_on_transfer_day", 0

    # Gate 2: compute gap in minutes
    arrive_abs  = to_absolute_minutes(leg1_arrival_time,   leg1_arrival_offset)
    depart_abs  = to_absolute_minutes(leg2_departure_time, leg2_departure_offset)
    gap         = depart_abs - arrive_abs

    # Gate 3: leg2 must depart after leg1 arrives
    if gap < 0:
        return False, "leg2_departs_before_leg1_arrives", gap

    # Gate 4: minimum buffer
    if gap < min_buffer_minutes:
        return False, f"gap_too_short_{gap}min", gap

    # Gate 5: maximum wait
    if gap > max_wait_minutes:
        return False, f"gap_too_long_{gap}min", gap

    return True, None, gap