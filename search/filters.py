from datetime import date, time, timedelta
from typing import Optional


def to_absolute_minutes(t: time, day_offset: int) -> int:
    """Converts time + day_offset to minutes from journey start."""
    return (day_offset * 1440) + (t.hour * 60) + t.minute


def get_transfer_weekday(journey_date: date, leg1_arrival_offset: int, leg1_arrival_time: time) -> list[int]:
    """
    Returns weekday index (0=Mon, 6=Sun) of the day
    leg2 is actually needed — accounts for overnight leg1.
    """
    transfer_datetime = timedelta(days=leg1_arrival_offset + journey_date.weekday() + 1, hours=leg1_arrival_time.hour, minutes=leg1_arrival_time.minute)
    tdt_min = transfer_datetime + timedelta(minutes=30)
    if tdt_min.days > 7:
        tdt_min_wd = tdt_min.days - 7 - 1
    else:
        tdt_min_wd = tdt_min.days - 1
    tdt_max = transfer_datetime + timedelta(minutes=300)
    if tdt_max.days > 7:
        tdt_max_wd = tdt_min.days - 7 - 1
    else:
        tdt_max_wd = tdt_min.days - 1

    if tdt_max_wd == tdt_max_wd:
        return [tdt_max_wd]
    return [tdt_min_wd, tdt_max_wd]


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


def train_runs_on_day_indirect(service_days: str, weekday: list, leg1_arrival_time: time, leg2_departure_time: time) -> tuple[bool, int, str]:
    """
    Checks if a train runs on a given weekday, 
    and falls between the waiting buffer
    weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    """
    if not service_days:
        return True   # assume runs if data missing

    service_days = service_days.strip()

    nday = {0: "Mon",1: "Tue",2: "Wed",3: "Thu",4: "Fri",5: "Sat",6: "Sun",}

    gap_td = timedelta(hours=leg2_departure_time.hour, minutes=leg2_departure_time.minute) - timedelta(hours=leg1_arrival_time.hour, minutes=leg1_arrival_time.minute)
    gap = int(gap_td.total_seconds() / 60)

    if len(weekday) == 1:
        if nday.get(weekday[0]) in service_days:
            if gap_td >= timedelta(minutes=30) and gap_td <= timedelta(minutes=300):
                return True, gap, nday.get(weekday[0])

    if len(weekday) == 2:
        l2dt = timedelta(hours=leg2_departure_time.hour,minutes=leg2_departure_time.minute)
        l1dt30 = timedelta(hours=leg1_arrival_time.hour,minutes=leg1_arrival_time.minute + 30)

        if nday.get(weekday[0]) in service_days:
            if gap_td >=  timedelta(minutes=30) and l1dt30 <= l2dt and l2dt <= timedelta(days=1):
                return True, gap, nday.get(weekday[0])

        l1dt300 = timedelta(hours=leg1_arrival_time.hour,minutes=leg1_arrival_time.minute + 300)    

        if nday.get(weekday[1]) in service_days:
            if gap_td <= timedelta(minutes=300) and timedelta(minutes=0) <= l2dt and l2dt <= l1dt300:
                return True, gap, nday.get(weekday[1])
    
    return False, gap, ''


def xfr_service_days(service_days: str, leg2_departure_offset: int) -> str:
    """
    Return the updated service_days for particular station
    based on day_offset of the station and service_days of the train
    """
    if leg2_departure_offset == 0:
        return service_days
    temp = []

    dayn = {"Mon": 1,"Tue": 2,"Wed": 3,"Thu": 4,"Fri": 5,"Sat": 6,"Sun": 7,}

    nday = {1: "Mon",2: "Tue",3: "Wed",4: "Thu",5: "Fri",6: "Sat",7: "Sun",}
    
    for day in service_days.strip().split(', '):
        var = dayn.get(day) + leg2_departure_offset
        if var > 7:
            temp.append(nday.get(var - 7))
        else:
            temp.append(nday.get(var))

    return ", ".join(temp)
    

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
    updated_service_days = xfr_service_days(service_days=leg2_service_days, leg2_departure_offset=leg2_departure_offset)

    transfer_weekday = get_transfer_weekday(journey_date=journey_date, leg1_arrival_offset=leg1_arrival_offset, leg1_arrival_time=leg1_arrival_time)

    trodi, gap, day = train_runs_on_day_indirect(service_days=updated_service_days, leg1_arrival_time=leg1_arrival_time, leg2_departure_time=leg2_departure_time, weekday=transfer_weekday)
    
    if not trodi:
        return False, "leg2_not_running_on_transfer_day", 0

    return True, None, gap