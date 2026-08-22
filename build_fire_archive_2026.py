import csv
import io
import json
import os
from datetime import datetime, timedelta

import requests


# ============================================================
# SETTINGS
# ============================================================

MAP_KEY = os.environ.get("FIRMS_MAP_KEY")

OUTPUT_FILE = "fire_archive_2026.json"

WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5

AREA = f"{WEST},{SOUTH},{EAST},{NORTH}"

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 8, 23)   # پایان انحصاری

DAY_RANGE = 5

# فقط منابع تاریخی استاندارد
SOURCES = [
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
]

BASE_URL = "https://firms.modaps.eosdis.nasa.gov"

TIMEOUT = 120


# ============================================================
# CHECK KEY
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets وجود ندارد."
    )


# ============================================================
# DATA AVAILABILITY
# ============================================================

def get_availability():

    url = (
        f"{BASE_URL}/api/data_availability/csv/"
        f"{MAP_KEY}/ALL"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT
    )

    if response.status_code != 200:
        raise RuntimeError(
            "خطا در data_availability:\n"
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )

    availability = {}

    reader = csv.DictReader(
        io.StringIO(response.text)
    )

    for row in reader:

        source = row.get("data_id")
        min_date = row.get("min_date")
        max_date = row.get("max_date")

        if not source or not min_date or not max_date:
            continue

        try:
            min_dt = datetime.strptime(
                min_date[:10],
                "%Y-%m-%d"
            )

            max_dt = datetime.strptime(
                max_date[:10],
                "%Y-%m-%d"
            )

        except ValueError:
            continue

        availability[source] = {
            "min": min_dt,
            "max": max_dt
        }

    return availability


# ============================================================
# FIRMS AREA REQUEST
# ============================================================

def get_fires(
    source,
    start_date
):

    date_text = start_date.strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{BASE_URL}/api/area/csv/"
        f"{MAP_KEY}/"
        f"{source}/"
        f"{AREA}/"
        f"{DAY_RANGE}/"
        f"{date_text}"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT
    )

    if response.status_code != 200:
        print(
            f"{source} | HTTP {response.status_code}"
        )
        return []

    reader = csv.DictReader(
        io.StringIO(response.text)
    )

    fires = []

    for row in reader:

        try:
            lat = float(
                row["latitude"]
            )

            lon = float(
                row["longitude"]
            )

        except (
            ValueError,
            TypeError,
            KeyError
        ):
            continue

        if not (
            SOUTH <= lat <= NORTH
            and
            WEST <= lon <= EAST
        ):
            continue

        fires.append({
            "latitude": lat,
            "longitude": lon,
            "acq_date": row.get(
                "acq_date",
                ""
            ),
            "acq_time": row.get(
                "acq_time",
                ""
            ),
            "satellite": row.get(
                "satellite",
                ""
            ),
            "instrument": row.get(
                "instrument",
                ""
            ),
            "confidence": row.get(
                "confidence",
                ""
            ),
            "frp": row.get(
                "frp",
                ""
            ),
            "daynight": row.get(
                "daynight",
                ""
            ),
            "source": source
        })

    return fires


# ============================================================
# MAIN
# ============================================================

print("")
print("==========================================")
print("آرشیو تاریخی FIRMS - سال 2026")
print("==========================================")

availability = get_availability()


for source in SOURCES:

    if source not in availability:

        print(
            f"{source}: در دسترس نیست"
        )

        continue

    info = availability[source]

    print(
        f"{source}: "
        f"{info['min'].strftime('%Y-%m-%d')}"
        " تا "
        f"{info['max'].strftime('%Y-%m-%d')}"
    )


all_fires = []

current = START_DATE


while current < END_DATE:

    period_end = min(
        current + timedelta(
            days=DAY_RANGE - 1
        ),
        END_DATE - timedelta(
            days=1
        )
    )

    print("")
    print(
        f"بازه: "
        f"{current.strftime('%Y-%m-%d')}"
        " تا "
        f"{period_end.strftime('%Y-%m-%d')}"
    )

    for source in SOURCES:

        info = availability.get(
            source
        )

        if not info:
            continue

        if (
            period_end < info["min"]
            or
            current > info["max"]
        ):
            print(
                f"{source}: خارج از بازه داده"
            )
            continue

        fires = get_fires(
            source,
            current
        )

        print(
            f"{source}: {len(fires)} رکورد"
        )

        all_fires.extend(
            fires
        )

    current += timedelta(
        days=DAY_RANGE
    )


# ============================================================
# DEDUPLICATE
# ============================================================

unique = {}
source_priority = {
    "VIIRS_SNPP_SP": 1,
    "VIIRS_NOAA20_SP": 1,
    "VIIRS_NOAA21_SP": 1,
}


for fire in all_fires:

    key = (
        round(
            fire["latitude"],
            5
        ),
        round(
            fire["longitude"],
            5
        ),
        fire["acq_date"],
        fire["acq_time"],
        fire["satellite"]
    )

    if key not in unique:
        unique[key] = fire


fires = list(
    unique.values()
)


# ============================================================
# SORT NEWEST FIRST
# ============================================================

def sort_key(fire):

    try:
        return datetime.strptime(
            f"{fire['acq_date']} "
            f"{str(fire['acq_time']).zfill(4)}",
            "%Y-%m-%d %H%M"
        )

    except Exception:
        return datetime.min


fires.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# DATE SUMMARY
# ============================================================

date_summary = {}

for fire in fires:

    date = fire["acq_date"]

    date_summary[date] = (
        date_summary.get(
            date,
            0
        )
        + 1
    )


# ============================================================
# SAVE
# ============================================================

result = {
    "status": "SUCCESS",

    "period": {
        "start":
            START_DATE.strftime(
                "%Y-%m-%d"
            ),
        "end":
            (
                END_DATE - timedelta(
                    days=1
                )
            ).strftime(
                "%Y-%m-%d"
            )
    },

    "area": {
        "west": WEST,
        "south": SOUTH,
        "east": EAST,
        "north": NORTH
    },

    "count":
        len(fires),

    "date_count":
        len(date_summary),

    "date_summary":
        date_summary,

    "fires":
        fires
}


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        result,
        file,
        ensure_ascii=False,
        indent=2
    )


print("")
print("==========================================")
print(
    f"رکوردهای خام: {len(all_fires)}"
)
print(
    f"رکوردهای یکتا: {len(fires)}"
)
print(
    f"روزهای دارای حریق: {len(date_summary)}"
)
print(
    f"خروجی: {OUTPUT_FILE}"
)
print("==========================================")
