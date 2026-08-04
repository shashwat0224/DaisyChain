import logging
from datetime import date, time
from typing import Optional

from .db import execute
from .models import DirectResult, IndirectResult, TransferInfo
from .filters import is_valid_transfer, train_runs_on_day

logger = logging.getLogger(__name__)

# Transfer buffer: major junctions need more time (busy, far platforms)
BUFFER_MAJOR  = 45   # minutes
BUFFER_NORMAL = 30   # minutes
MAX_WAIT      = 360  # 6 hours max layover


def _get_legs_through_station(
    source:      str,
    destination: str,
    transfer:    str,
) -> tuple[list[dict], list[dict]]:
    """
    Fetch leg1 (source→transfer) and leg2 (transfer→destination)
    raw rows from DB for a specific transfer station.
    """
    leg1_rows = execute("""
        SELECT
            t.train_no,
            t.train_name,
            t.classes,
            t.service_days,
            src.departure_time  AS src_departure,
            src.arrival_time    AS src_arrival,
            src.day_offset      AS src_day,
            src.stop_index      AS src_idx,
            xfr.arrival_time    AS xfr_arrival,
            xfr.departure_time  AS xfr_departure,
            xfr.day_offset      AS xfr_day,
            xfr.stop_index      AS xfr_idx,
            (
                (xfr.day_offset - src.day_offset) * 1440
                + EXTRACT(EPOCH FROM (
                    COALESCE(xfr.arrival_time, xfr.departure_time)
                    - COALESCE(src.departure_time, src.arrival_time)
                ))::int / 60
            ) AS journey_minutes
        FROM train_stops src
        JOIN train_stops xfr
            ON  src.train_no     = xfr.train_no
            AND xfr.station_code = %s
            AND xfr.stop_index   > src.stop_index
        JOIN trains t ON t.train_no = src.train_no
        WHERE src.station_code = %s
          AND COALESCE(src.departure_time, src.arrival_time) IS NOT NULL
          AND COALESCE(xfr.arrival_time,   xfr.departure_time) IS NOT NULL
    """, (transfer, source))

    leg2_rows = execute("""
        SELECT
            t.train_no,
            t.train_name,
            t.classes,
            t.service_days,
            xfr.departure_time  AS xfr_departure,
            xfr.arrival_time    AS xfr_arrival,
            xfr.day_offset      AS xfr_day,
            xfr.stop_index      AS xfr_idx,
            dst.arrival_time    AS dst_arrival,
            dst.departure_time  AS dst_departure,
            dst.day_offset      AS dst_day,
            dst.stop_index      AS dst_idx,
            (
                (dst.day_offset - xfr.day_offset) * 1440
                + EXTRACT(EPOCH FROM (
                    COALESCE(dst.arrival_time, dst.departure_time)
                    - COALESCE(xfr.departure_time, xfr.arrival_time)
                ))::int / 60
            ) AS journey_minutes,
            -- get origin day_offset for service_day check
            (SELECT day_offset FROM train_stops 
             WHERE train_no = xfr.train_no 
             AND stop_index = 0) AS origin_day_offset
        FROM train_stops xfr
        JOIN train_stops dst
            ON  xfr.train_no     = dst.train_no
            AND dst.station_code = %s
            AND dst.stop_index   > xfr.stop_index
        JOIN trains t ON t.train_no = xfr.train_no
        WHERE xfr.station_code = %s
          AND COALESCE(xfr.departure_time, xfr.arrival_time) IS NOT NULL
          AND COALESCE(dst.arrival_time,   dst.departure_time) IS NOT NULL
    """, (destination, transfer))

    return leg1_rows, leg2_rows


def _get_transfer_stations(
    source:      str,
    destination: str,
    major_only:  bool,
) -> list[dict]:
    """
    Find all stations that are reachable from source
    AND can reach destination — these are candidate transfer points.
    """
    query = """
        SELECT DISTINCT
            s.station_code,
            s.station_name,
            s.is_major_junction
        FROM train_stops t1
        JOIN train_stops t2
            ON  t1.train_no      != t2.train_no
            AND t1.station_code   = t2.station_code
        JOIN stations s
            ON  s.station_code   = t1.station_code
        WHERE t1.train_no IN (
            SELECT train_no FROM train_stops WHERE station_code = %s
        )
        AND t2.train_no IN (
            SELECT train_no FROM train_stops WHERE station_code = %s
        )
        AND t1.station_code NOT IN (%s, %s)
    """
    params = (source, destination, source, destination)

    if major_only:
        query += """
        AND s.is_major_junction = TRUE
        ORDER BY s.is_major_junction DESC, s.station_code ASC
        """

    query += " LIMIT 100"

    return execute(query, params)


def search_indirect(
    source:            str,
    destination:       str,
    journey_date:      date,
    depart_after:      Optional[time] = None,
    max_results:       int = 20,
    major_only:        bool = True,   # set False for fallback
) -> list[IndirectResult]:
    """
    Find indirect routes source → transfer → destination.
    Sorted by total journey duration (shortest first).
    """
    source      = source.upper().strip()
    destination = destination.upper().strip()

    transfer_stations = _get_transfer_stations(source, destination, major_only)

    if not transfer_stations and major_only:
        # Fallback: try all stations
        logger.info(f"No major junction transfers for {source}→{destination}, trying all stations")
        transfer_stations = _get_transfer_stations(source, destination, major_only=False)

    if not transfer_stations:
        logger.info(f"No transfer stations found for {source}→{destination}")
        return []

    logger.info(
        f"Evaluating {len(transfer_stations)} transfer stations "
        f"for {source}→{destination}"
    )

    direct_train_nos = set(
    row["train_no"].strip()
    for row in execute("""
        SELECT DISTINCT src.train_no
        FROM train_stops src
        JOIN train_stops dst
            ON  src.train_no    = dst.train_no
            AND dst.station_code = %s
            AND dst.stop_index  > src.stop_index
        WHERE src.station_code = %s
    """, (destination, source))
)

    results = []

    for station in transfer_stations:
        transfer_code = station["station_code"]
        is_major      = station["is_major_junction"]
        min_buffer    = BUFFER_MAJOR if is_major else BUFFER_NORMAL

        leg1_rows, leg2_rows = _get_legs_through_station(
            source, destination, transfer_code
        )

        for l1 in leg1_rows:
            # Day filter for leg1
            if l1["train_no"].strip() in direct_train_nos:
                continue

            if not train_runs_on_day(l1["service_days"], journey_date.weekday()):
                continue

            l1_src_dep = l1["src_departure"] or l1["src_arrival"]

            # depart_after filter
            if depart_after and l1_src_dep and l1_src_dep < depart_after:
                continue

            if (l1["journey_minutes"] or 0) < 20:
                continue

            l1_xfr_arr = l1["xfr_arrival"] or l1["xfr_departure"]
            if not l1_xfr_arr:
                continue

            for l2 in leg2_rows:
                if l1["train_no"].strip() == l2["train_no"].strip():
                    continue
                
                l2_xfr_dep = l2["xfr_departure"] or l2["xfr_arrival"]
                if not l2_xfr_dep:
                    continue

                valid, reason, gap = is_valid_transfer(
                    leg1_arrival_time     = l1_xfr_arr,
                    leg1_arrival_offset   = l1["xfr_day"],
                    leg2_departure_time   = l2_xfr_dep,
                    leg2_departure_offset = l2["xfr_day"],
                    leg2_service_days     = l2["service_days"],
                    journey_date          = journey_date,
                    min_buffer_minutes    = min_buffer,
                    max_wait_minutes      = MAX_WAIT,
                )

                if not valid:
                    continue

                l2_dst_arr = l2["dst_arrival"] or l2["dst_departure"]

                # Build leg1 result
                leg1_result = DirectResult(
                    train_no         = l1["train_no"].strip(),
                    train_name       = l1["train_name"],
                    source_station   = source,
                    dest_station     = transfer_code,
                    departure_time   = l1_src_dep,
                    departure_day    = l1["src_day"],
                    arrival_time     = l1_xfr_arr,
                    arrival_day      = l1["xfr_day"],
                    journey_minutes  = l1["journey_minutes"] or 0,
                    stops_in_between = l1["xfr_idx"] - l1["src_idx"] - 1,
                    classes          = l1["classes"] or "",
                    service_days     = l1["service_days"] or "",
                )

                # Build leg2 result
                leg2_result = DirectResult(
                    train_no         = l2["train_no"].strip(),
                    train_name       = l2["train_name"],
                    source_station   = transfer_code,
                    dest_station     = destination,
                    departure_time   = l2_xfr_dep,
                    departure_day    = l2["xfr_day"],
                    arrival_time     = l2_dst_arr,
                    arrival_day      = l2["dst_day"],
                    journey_minutes  = l2["journey_minutes"] or 0,
                    stops_in_between = l2["dst_idx"] - l2["xfr_idx"] - 1,
                    classes          = l2["classes"] or "",
                    service_days     = l2["service_days"] or "",
                )

                total_minutes = (
                    (leg1_result.journey_minutes or 0) +
                    gap +
                    (leg2_result.journey_minutes or 0)
                )

                results.append(IndirectResult(
                    leg1              = leg1_result,
                    leg2              = leg2_result,
                    transfer          = TransferInfo(
                        station_code = transfer_code,
                        station_name = station["station_name"],
                        is_major     = is_major,
                        wait_minutes = gap,
                        arrive_time  = l1_xfr_arr,
                        arrive_day   = l1["xfr_day"],
                        depart_time  = l2_xfr_dep,
                        depart_day   = l2["xfr_day"],
                    ),
                    total_minutes     = total_minutes,
                    is_major_junction = is_major,
                ))

                if len(results) >= max_results * 3:
                    # Collected enough candidates — stop early
                    # We'll trim to max_results after sorting
                    break

    # Sort by total journey duration
    results.sort(key=lambda r: r.total_minutes)

    # Deduplicate — same train pair at same transfer = keep shortest wait
    seen = {}
    deduped = []
    for r in results:
        key = (r.leg1.train_no, r.leg2.train_no)   # train pair only
        if key not in seen:
            seen[key] = True
            deduped.append(r)

    return deduped[:max_results]