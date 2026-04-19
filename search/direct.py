import logging
from datetime import date, time
from typing import Optional

from .db import execute
from .models import DirectResult
from .filters import train_runs_on_day, get_transfer_weekday

logger = logging.getLogger(__name__)


def search_direct(
    source:       str,
    destination:  str,
    journey_date: date,
    depart_after: Optional[time] = None,   # e.g. time(9, 0) for after 9am
) -> list[DirectResult]:
    """
    Find all direct trains from source → destination on journey_date.
    Sorted by journey duration (shortest first).

    Args:
        source:       station code e.g. "JP"
        destination:  station code e.g. "NDLS"
        journey_date: date of travel
        depart_after: optional — only return trains departing after this time

    Returns:
        List of DirectResult sorted by journey_minutes ascending.
    """
    source      = source.upper().strip()
    destination = destination.upper().strip()

    rows = execute("""
        SELECT
            t.train_no,
            t.train_name,
            t.classes,
            t.service_days,

            -- Source stop info
            src.departure_time  AS src_departure,
            src.arrival_time    AS src_arrival,
            src.day_offset      AS src_day,
            src.stop_index      AS src_idx,

            -- Destination stop info
            dst.arrival_time    AS dst_arrival,
            dst.departure_time  AS dst_departure,
            dst.day_offset      AS dst_day,
            dst.stop_index      AS dst_idx,

            -- Journey duration in minutes
            (
                (dst.day_offset - src.day_offset) * 1440
                + EXTRACT(EPOCH FROM (
                    COALESCE(dst.arrival_time, dst.departure_time)
                    - COALESCE(src.departure_time, src.arrival_time)
                ))::int / 60
            ) AS journey_minutes,

            -- Intermediate stops count
            (dst.stop_index - src.stop_index - 1) AS stops_in_between

        FROM train_stops src
        JOIN train_stops dst
            ON  src.train_no    = dst.train_no
            AND dst.station_code = %s
            AND dst.stop_index  > src.stop_index
        JOIN trains t
            ON t.train_no = src.train_no

        WHERE src.station_code = %s
          AND COALESCE(src.departure_time, src.arrival_time) IS NOT NULL
          AND COALESCE(dst.arrival_time,   dst.departure_time) IS NOT NULL

        ORDER BY journey_minutes ASC
    """, (destination, source))

    results = []

    for row in rows:
        # Filter by service day
        weekday = journey_date.weekday()
        if not train_runs_on_day(row["service_days"], weekday):
            continue

        src_dep = row["src_departure"] or row["src_arrival"]
        dst_arr = row["dst_arrival"]   or row["dst_departure"]

        # Filter by depart_after if provided
        if depart_after and src_dep:
            if row["src_day"] == 0 and src_dep < depart_after:
                continue

        # Skip negative/zero duration (data anomaly)
        if row["journey_minutes"] is None or row["journey_minutes"] <= 0:
            continue

        results.append(DirectResult(
            train_no         = row["train_no"].strip(),
            train_name       = row["train_name"],
            source_station   = source,
            dest_station     = destination,
            departure_time   = src_dep,
            departure_day    = row["src_day"],
            arrival_time     = dst_arr,
            arrival_day      = row["dst_day"],
            journey_minutes  = row["journey_minutes"],
            stops_in_between = row["stops_in_between"],
            classes          = row["classes"] or "",
            service_days     = row["service_days"] or "",
        ))

    # Already sorted by SQL but re-sort after day filter
    # in case day filtering changed the order
    results.sort(key=lambda r: r.journey_minutes)
    return results