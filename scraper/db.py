import psycopg2
import psycopg2.extras
import logging
import re
from datetime import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "train_db",
    "user":     "postgres",
    "password": "20357",   # ← change this
}

'''
            blocked          : 2
            parse_error      : 2
            
            Blocked trains:
            ['22325', '22326']
            
            Parse error trains:
            ['12891', '20896']
'''

@contextmanager
def get_conn():
    """
    Always creates a fresh connection.
    Never share psycopg2 connections across processes — it crashes.
    """
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_time(value) -> time | None:
    if not value:
        return None
    s = str(value).strip()
    if s.lower() in ("--", "", "starts", "ends", "source", "destination"):
        return None
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", s)
    if match:
        return time(int(match.group(1)), int(match.group(2)))
    return None


def parse_minutes(value) -> int | None:
    """
    Converts any duration/delay string to integer minutes.
    Handles: "3min", "2 Hrs 30 Min", "On Time", "9min", "--", None
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("--", "", "on time"):
        return 0 if "on time" in s else None
    hours = re.search(r"(\d+)\s*hr", s)
    mins  = re.search(r"(\d+)\s*min", s)
    if not hours and not mins:
        digits = re.sub(r"[^0-9]", "", s)
        return int(digits) if digits else None
    total = (int(hours.group(1)) * 60 if hours else 0) + \
            (int(mins.group(1))        if mins  else 0)
    return total if total >= 0 else None


def save_train_data(data: dict):
    """
    Writes one fully-scraped train to PostgreSQL.

    Expected data shape (exactly what scraper.py returns):
    {
        "train_no":            "12974",
        "train_name":          "JP INDB SF EXP",
        "source_station":      "JP",
        "destination_station": "INDB",
        "classes":             "1A, 2A, 3A, 3E, SL",
        "service_days":        "Fri, Sun",
        "train_type":          "Mail Express",
        "duration":            "9hr 25min",
        "start_time":          "21:00",
        "end_time":            "06:25",
        "stops": [
            {
                "station_code":  "JP",
                "station_name":  "Jaipur",
                "stop_index":    0,
                "arrival_time":  None,        ← None for first stop
                "departure_time": "21:00",
                "halt_time":     None,
                "distance_km":   0,
                "platform":      "5",
                "day_offset":    0,
                "avg_delay":     0
            },
            ...
        ]
    }
    """
    with get_conn() as conn:
        cur = conn.cursor()

        # 1. Upsert all stations from this train's stops
        station_rows = [
            (s["station_code"].upper(), s["station_name"])
            for s in data["stops"]
        ]
        psycopg2.extras.execute_values(cur, """
            INSERT INTO stations (station_code, station_name)
            VALUES %s
            ON CONFLICT (station_code) DO NOTHING
        """, station_rows)

        # 2. Upsert train record
        cur.execute("""
            INSERT INTO trains
                (train_no, train_name, source_station, destination_station,
                 classes, service_days, start_time, end_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (train_no) DO UPDATE SET
                train_name           = EXCLUDED.train_name,
                classes              = EXCLUDED.classes,
                service_days         = EXCLUDED.service_days,
                start_time           = EXCLUDED.start_time,
                end_time             = EXCLUDED.end_time
        """, (
            data["train_no"],
            data["train_name"],
            data["source_station"].upper(),
            data["destination_station"].upper(),
            data["classes"],
            data["service_days"],
            parse_time(data.get("start_time")),
            parse_time(data.get("end_time")),
        ))

        # 3. Delete existing stops then bulk insert fresh
        cur.execute(
            "DELETE FROM train_stops WHERE train_no = %s",
            (data["train_no"],)
        )

        stop_rows = [(
            data["train_no"],
            s["station_code"].upper(),
            s["stop_index"],
            parse_time(s.get("arrival_time")),
            parse_time(s.get("departure_time")),
            parse_minutes(s.get("halt_time")),
            s.get("day_offset", 0),
            parse_minutes(s.get("avg_delay")),
        ) for s in data["stops"]]

        psycopg2.extras.execute_values(cur, """
            INSERT INTO train_stops
                (train_no, station_code, stop_index,
                 arrival_time, departure_time,
                 halt_time, day_offset, avg_delay)
            VALUES %s
        """, stop_rows)

        logger.info(
            f"  [OK] Saved {data['train_no']} | {data['train_name']} "
            f"| {len(stop_rows)} stops"
        )


def bulk_update_major_junctions():
    """
    Run once after all scraping is complete.
    Derives major junction status from actual traffic data.
    A station is major if: 25+ distinct trains stop there AND
    trains from 2+ railway zones pass through.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            WITH stop_counts AS (
                SELECT
                    station_code,
                    COUNT(DISTINCT train_no)                         AS train_count,
                    COUNT(DISTINCT SUBSTRING(train_no::text, 1, 2)) AS zone_count
                FROM train_stops
                GROUP BY station_code
            )
            UPDATE stations s
            SET is_major_junction = TRUE
            FROM stop_counts sc
            WHERE s.station_code = sc.station_code
              AND sc.train_count  > 25
              AND sc.zone_count  >= 2
        """)
        logger.info(f"Marked {cur.rowcount} stations as major junctions")