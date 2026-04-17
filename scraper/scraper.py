import time
import random
import re
import logging
from bs4 import BeautifulSoup
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# Confirmed from live page inspection
BASE_URL = "https://www.ixigo.com/trains/{}"


# ── Browser factory ──────────────────────────────────────────────────────────

def make_context(playwright):
    """
    Creates a desktop browser context that won't trigger mobile layout.
    Always use this — never call new_context() directly in worker.
    Returns (browser, context).
    """
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ]
    )

    version_major = browser.version.split(".")[0]

    context = browser.new_context(
        user_agent=(
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version_major}.0.0.0 Safari/537.36"
        ),
        no_viewport=True,       # --start-maximized controls actual size
        is_mobile=False,
        has_touch=False,
        locale="en-IN",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return browser, context


# ── Page state detection ─────────────────────────────────────────────────────

def is_mobile_layout(page: Page) -> bool:
    """
    Ixigo serves mobile layout when viewport < ~1024px or mobile UA.
    Desktop schedule has tables; mobile uses card/list components.
    """
    # Hard check: rendered viewport width
    try:
        vw = page.evaluate("() => window.innerWidth")
        if vw < 1024:
            return True
    except Exception:
        pass

    # DOM check: mobile uses list-based schedule, not tables
    has_mobile_cards = page.locator(
        ".schedule-list-item, .m-schedule-row, .train-schedule-mobile"
    ).count() > 0
    has_tables = page.locator("table").count() > 0

    if has_mobile_cards and not has_tables:
        return True

    return False


def is_redirected(page: Page, train_no: str) -> bool:
    """
    Detects hard redirects (URL changed) and soft redirects
    (URL same but page is homepage or error state).
    """
    current_url = page.url

    if str(train_no) not in current_url:
        return True

    # # Soft redirect: rendered the trains search homepage
    # has_search   = page.locator("input[placeholder*='Train']").count() > 0
    # has_no_table = page.locator("table").count() == 0
    # if has_search and has_no_table:
    #     return True

    # # Error page content
    # try:
    #     body = page.locator("body").inner_text().lower()
    #     for phrase in ["train not found", "invalid train", "no schedule", "404"]:
    #         if phrase in body:
    #             return True
    # except Exception:
    #     pass

    return False


# ── Value cleaners ───────────────────────────────────────────────────────────

def clean_time(raw: str) -> str | None:
    """
    Returns "HH:MM" or None.
    Handles: "21:00", "21:00 Hrs", "starts", "ends", "--"
    """
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower() in ("--", "starts", "ends", "source", "destination", ""):
        return None
    match = re.search(r"\b(\d{1,2}:\d{2})\b", raw)
    return match.group(1) if match else None


def clean_halt(raw: str) -> str | None:
    """Pass through halt string — db.py converts to int minutes."""
    if not raw or raw.strip() in ("--", "-", ""):
        return None
    return raw.strip()


def clean_delay(raw: str) -> str | None:
    """Pass through delay string — db.py converts to int minutes."""
    if not raw or raw.strip() in ("--", ""):
        return None
    return raw.strip()


def parse_service_days(raw: str) -> str:
    """
    Ixigo shows: "Fri, Sun" or "SMTWTFS" style or "Daily"
    Store as-is — clean enough for day-of-week filtering logic.
    """
    if not raw:
        return ""
    return raw.strip()


# ── Main scrape entry point ──────────────────────────────────────────────────

def scrape_train(train_no: str, page: Page) -> dict | str | None:
    """
    Returns:
        dict      → success, ready to pass to save_train_data()
        "BLOCKED" → redirected/blocked, worker should restart browser
        "MOBILE"  → mobile layout, worker should reset context and retry
        "WRONG"   → page loaded but data couldn't be parsed
        None      → unexpected exception caught in worker
    """
    url = BASE_URL.format(train_no)

    # Warm up: visit landing page first to establish session/cookies
    try:
        page.goto("https://www.ixigo.com/trains", timeout=30000)
        time.sleep(random.uniform(2, 4))
    except Exception:
        pass  # non-fatal

    # Navigate to train page
    try:
        page.goto(url, timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)
        try:
            page.wait_for_selector("table", timeout=15000)  # wait specifically for a table
        except Exception:
            pass  # if no table appears in 8s, redirect check will catch it

    except Exception as e:
        logger.warning(f"[{train_no}] Navigation failed: {e}")
        return "BLOCKED"

    # Give JS time to render schedule tables
    time.sleep(random.uniform(1, 2))

    # Gate 1: redirect / not found
    if is_redirected(page, train_no):
        logger.warning(f"[{train_no}] Redirected >> {page.url}")
        return "BLOCKED"

    # Gate 2: mobile layout
    if is_mobile_layout(page):
        logger.warning(f"[{train_no}] Mobile layout detected")
        return "MOBILE"

    # Gate 3: need at least some tables on page
    if page.locator("table").count() < 1:
        logger.warning(f"[{train_no}] No tables found — incomplete render")
        return "WRONG"

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    try:
        return _parse(soup, train_no)
    except Exception as e:
        logger.error(f"[{train_no}] Parse exception: {e}", exc_info=True)
        return "WRONG"


# ── HTML parser ──────────────────────────────────────────────────────────────

def _parse(soup: BeautifulSoup, train_no: str) -> dict | str:
    """
    Parses the live Ixigo train page structure for ixigo.com/trains/{no}

    Page structure (confirmed from live page):
    ┌─────────────────────────────────────────┐
    │  <h1>  Jp Indb Sf Exp 12974 Train       │
    │  Train info table (2-col key/value)     │
    │    Classes | 1A, 2A, 3A, 3E, SL        │
    │    Service Days | Fri, Sun              │
    │    Type | Mail Express                  │
    │  Schedule section:                      │
    │    Header row  → one <table>            │
    │    Each stop   → its own <table>        │  ← critical: one table per row
    └─────────────────────────────────────────┘
    """

    # ── Train name ────────────────────────────────────────────────────────────
    # Page title is "Jp Indb Sf Exp 12974 Train" — strip number + " Train"
    train_name = ""
    h1 = soup.find("h1")
    if h1:
        raw = h1.get_text(strip=True)
        # Remove "12974 Train" or "12974" from end
        raw = re.sub(rf"\s*{re.escape(str(train_no))}\s*Train\s*$", "", raw, flags=re.IGNORECASE)
        raw = re.sub(rf"\s*{re.escape(str(train_no))}\s*$", "", raw)
        train_name = raw.strip()

    if not train_name:
        # Fallback: page <title> tag
        title = soup.find("title")
        if title:
            raw = title.get_text(strip=True)
            # "12974 Jp Indb Sf Exp Train Route..." → extract name portion
            match = re.search(rf"{re.escape(str(train_no))}\s+(.+?)\s+Train", raw, re.IGNORECASE)
            if match:
                train_name = match.group(1).strip()

    if not train_name:
        logger.warning(f"[{train_no}] Could not extract train name")
        return "WRONG"

    # ── Info table ────────────────────────────────────────────────────────────
    # Structure: <table><tr><td>Classes</td><td>1A, 2A, 3A, 3E, SL</td></tr>...
    info_data = {}
    all_tables = soup.find_all("table")

    for table in all_tables:
        rows = table.find_all("tr")
        for row in rows:
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cols) == 2 and cols[0]:
                info_data[cols[0].strip().lower()] = cols[1].strip()

    def get_info(*keys) -> str:
        for k in keys:
            for stored_key, val in info_data.items():
                if k.lower() in stored_key:
                    return val
        return ""

    # Exact keys from live page: "Classes", "Service Days", "Type"
    classes      = get_info("classes", "class")
    service_days = parse_service_days(get_info("service days", "runs on"))
    train_type   = get_info("type")

    # ── Schedule rows ─────────────────────────────────────────────────────────
    # CRITICAL STRUCTURE: On the live page, the schedule is NOT one big table.
    # The header is one <table>, and EACH STOP ROW is its own separate <table>.
    # We identify stop rows by their column count (10 columns per stop row).
    #
    # Confirmed columns (from live page):
    # [0] Stn Code | [1] Stn Name | [2] Arrives | [3] Departs | [4] Stop time
    # [5] Distance | [6] Platform | [7] Route    | [8] Day     | [9] Avg delay

    stops = []
    stop_index = 0

    for table in all_tables:
        for row in table.find_all("tr"):
            cols = [c.get_text(strip=True) for c in row.find_all("td")]

            # Stop rows have exactly 10 columns
            # Skip header rows (th) and info table rows (2 cols)
            if len(cols) != 10:
                continue

            # Column 0 must look like a station code (2-7 uppercase letters/digits)
            station_code = cols[0].strip().upper()
            if not re.match(r"^[A-Z0-9]{2,7}$", station_code):
                continue

            station_name = cols[1].strip()

            # cols[2] = Arrives: "starts" for origin, "HH:MM" for others
            # cols[3] = Departs: "ends" for destination, "HH:MM" for others
            arrival_raw   = cols[2].strip()
            departure_raw = cols[3].strip()
            halt_raw      = cols[4].strip()   # e.g. "3min", "-", "--"
            # cols[5] = Distance (km) — not stored but useful for validation
            # cols[6] = Platform number
            # cols[7] = Route number (always "1" for main route)
            day_raw   = cols[8].strip()       # "1" or "2"
            delay_raw = cols[9].strip()       # "On Time", "9min", "--"

            arrival_time   = clean_time(arrival_raw)
            departure_time = clean_time(departure_raw)

            # day_offset: Ixigo Day 1 = 0, Day 2 = 1, Day 3 = 2
            try:
                day_offset = int(re.search(r"\d+", day_raw).group()) - 1
            except Exception:
                day_offset = 0

            stops.append({
                "station_code":  station_code,
                "station_name":  station_name,
                "stop_index":    stop_index,
                "arrival_time":  arrival_time,    # None for first stop
                "departure_time": departure_time, # None for last stop
                "halt_time":     clean_halt(halt_raw),
                "day_offset":    day_offset,
                "avg_delay":     clean_delay(delay_raw),
            })
            stop_index += 1

    if not stops:
        logger.warning(f"[{train_no}] Zero stops parsed — page may not have rendered")
        return "WRONG"

    source_station = stops[0]["station_code"]
    dest_station   = stops[-1]["station_code"]

    return {
        "train_no":            train_no,
        "train_name":          train_name,
        "source_station":      source_station,
        "destination_station": dest_station,
        "classes":             classes,
        "service_days":        service_days,
        "train_type":          train_type,
        "start_time":          stops[0]["departure_time"],
        "end_time":            stops[-1]["arrival_time"],
        "stops":               stops,
    }