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

# پایان انحصاری
# یعنی تا پایان 22 اوت 2026
END_DATE = datetime(2026, 8, 23)

DAY_RANGE = 5

# برای آرشیو تاریخی فقط SP
SOURCES = [
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
]

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

TIMEOUT = 120


# ============================================================
# CHECK SECRET
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets تنظیم نشده است."
    )


# ============================================================
# DOWNLOAD ONE 5-DAY PERIOD
# ============================================================

def download_period(source, start_date):

    date_text = start_date.strftime(
        "%Y-%m-%d"
    )

    url = (
        f"{URL}/"
        f"{MAP_KEY}/"
        f"{source}/"
        f"{AREA}/"
        f"{DAY_RANGE}/"
        f"{date_text}"
    )

    print("")
    print(
        f"درخواست FIRMS:"
    )
    print(
        f"منبع: {source}"
    )
    print(
        f"شروع: {date_text}"
    )

    response = requests.get(
        url,
        timeout=TIMEOUT
    )

    if response.status_code != 200:

        print(
            f"HTTP {response.status_code}"
        )

        print(
            response.text[:500]
        )

        return []


    text = response.text.strip()


    if not text:
        return []


    # اگر FIRMS به‌جای CSV خطا برگرداند
    if text.startswith("{"):

        print(
            "پاسخ JSON/خطا دریافت شد:"
        )

        print(
            text[:500]
        )

        return []


    reader = csv.DictReader(
        io.StringIO(text)
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

            "latitude":
                lat,

            "longitude":
                lon,

            "acq_date":
                row.get(
                    "acq_date",
                    ""
                ),

            "acq_time":
                row.get(
                    "acq_time",
                    ""
                ),

            "satellite":
                row.get(
                    "satellite",
                    ""
                ),

            "instrument":
                row.get(
                    "instrument",
                    ""
                ),

            "confidence":
                row.get(
                    "confidence",
                    ""
                ),

            "frp":
                row.get(
                    "frp",
                    ""
                ),

            "daynight":
                row.get(
                    "daynight",
                    ""
                ),

            "source":
                source
        })


    return fires


# ============================================================
# COLLECT
# ============================================================

all_fires = []

current_date = START_DATE


while current_date < END_DATE:

    period_end = min(
        current_date
        + timedelta(
            days=DAY_RANGE - 1
        ),
        END_DATE
        - timedelta(
            days=1
        )
    )


    print("")
    print(
        "=========================================="
    )

    print(
        f"بازه: "
        f"{current_date.strftime('%Y-%m-%d')}"
        " تا "
        f"{period_end.strftime('%Y-%m-%d')}"
    )

    print(
        "=========================================="
    )


    for source in SOURCES:

        fires = download_period(
            source,
            current_date
        )


        print(
            f"{source}: "
            f"{len(fires)} رکورد"
        )


        all_fires.extend(
            fires
        )


    current_date += timedelta(
        days=DAY_RANGE
    )


# ============================================================
# SORT
# ============================================================

def sort_key(fire):

    try:

        return datetime.strptime(
            f"{fire.get('acq_date', '')} "
            f"{str(fire.get('acq_time', '')).zfill(4)}",
            "%Y-%m-%d %H%M"
        )

    except Exception:

        return datetime.min


all_fires.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# REMOVE DUPLICATES
# ============================================================

unique_fires = []

seen = set()


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

        fire.get(
            "acq_date",
            ""
        ),

        fire.get(
            "acq_time",
            ""
        ),

        fire.get(
            "satellite",
            ""
        )
    )


    if key in seen:
        continue


    seen.add(
        key
    )


    unique_fires.append(
        fire
    )


# ============================================================
# GROUP BY DATE
# ============================================================

date_summary = {}


for fire in unique_fires:

    date = fire.get(
        "acq_date",
        ""
    )


    if not date:
        continue


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

    "status":
        "SUCCESS",

    "period": {

        "start":
            START_DATE.strftime(
                "%Y-%m-%d"
            ),

        "end":
            (
                END_DATE
                - timedelta(
                    days=1
                )
            ).strftime(
                "%Y-%m-%d"
            )

    },

    "area": {

        "west":
            WEST,

        "south":
            SOUTH,

        "east":
            EAST,

        "north":
            NORTH

    },

    "sources":
        SOURCES,

    "raw_count":
        len(all_fires),

    "count":
        len(unique_fires),

    "date_count":
        len(date_summary),

    "date_summary":
        date_summary,

    "fires":
        unique_fires
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


# ============================================================
# FINAL
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "آرشیو تاریخی حریق 2026 آماده شد"
)

print(
    f"رکورد خام: {len(all_fires)}"
)

print(
    f"رکورد یکتا: {len(unique_fires)}"
)

print(
    f"روزهای دارای حریق: {len(date_summary)}"
)

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
