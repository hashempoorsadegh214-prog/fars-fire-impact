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

BOUNDARY_FILE = "fars.geojson"

OUTPUT_FILE = "fire_archive_2026.json"

# محدوده کلی برای کم کردن حجم درخواست FIRMS
WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5

AREA = f"{WEST},{SOUTH},{EAST},{NORTH}"

# بازه آرشیو
START_DATE = datetime(2026, 1, 1)

# پایان انحصاری
# یعنی تا پایان 22 اوت 2026
END_DATE = datetime(2026, 8, 23)

# FIRMS حداکثر 5 روز در هر درخواست
DAY_RANGE = 5

# فقط داده استاندارد تاریخی
SOURCES = [
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
]

BASE_URL = (
    "https://firms.modaps.eosdis.nasa.gov"
)

TIMEOUT = 120


# ============================================================
# CHECK SECRET
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets تنظیم نشده است."
    )


# ============================================================
# LOAD FARS GEOJSON
# ============================================================

with open(
    BOUNDARY_FILE,
    "r",
    encoding="utf-8"
) as file:

    fars_data = json.load(file)


# ============================================================
# EXTRACT GEOMETRIES
# ============================================================

def extract_geometries(
    geojson
):

    geojson_type = geojson.get(
        "type"
    )

    if geojson_type == "FeatureCollection":

        geometries = []

        for feature in geojson.get(
            "features",
            []
        ):

            geometry = feature.get(
                "geometry"
            )

            if geometry:
                geometries.append(
                    geometry
                )

        return geometries


    if geojson_type == "Feature":

        geometry = geojson.get(
            "geometry"
        )

        return (
            [geometry]
            if geometry
            else []
        )


    if geojson_type in (
        "Polygon",
        "MultiPolygon"
    ):

        return [geojson]


    return []


FARS_GEOMETRIES = extract_geometries(
    fars_data
)


if not FARS_GEOMETRIES:

    raise RuntimeError(
        "هندسه معتبر در fars.geojson پیدا نشد."
    )


print("")
print(
    "=========================================="
)

print(
    "مرز واقعی فارس بارگذاری شد."
)

print(
    f"تعداد هندسه‌ها: "
    f"{len(FARS_GEOMETRIES)}"
)

print(
    "=========================================="
)


# ============================================================
# POINT IN RING
# ============================================================

def point_in_ring(
    lon,
    lat,
    ring
):

    inside = False

    j = len(ring) - 1

    for i in range(
        len(ring)
    ):

        xi = ring[i][0]
        yi = ring[i][1]

        xj = ring[j][0]
        yj = ring[j][1]

        intersects = (

            ((yi > lat) != (yj > lat))

            and

            (
                lon
                <
                (
                    (xj - xi)
                    * (lat - yi)
                    /
                    ((yj - yi) or 1e-15)
                    + xi
                )
            )
        )

        if intersects:

            inside = not inside

        j = i

    return inside


# ============================================================
# POINT IN POLYGON
# ============================================================

def point_in_polygon(
    lon,
    lat,
    polygon
):

    if not polygon:
        return False


    # حلقه بیرونی
    if not point_in_ring(
        lon,
        lat,
        polygon[0]
    ):

        return False


    # حفره‌ها
    for hole in polygon[1:]:

        if point_in_ring(
            lon,
            lat,
            hole
        ):

            return False


    return True


# ============================================================
# POINT IN GEOMETRY
# ============================================================

def point_in_geometry(
    lon,
    lat,
    geometry
):

    geometry_type = geometry.get(
        "type"
    )

    coordinates = geometry.get(
        "coordinates"
    )


    if geometry_type == "Polygon":

        return point_in_polygon(
            lon,
            lat,
            coordinates
        )


    if geometry_type == "MultiPolygon":

        for polygon in coordinates:

            if point_in_polygon(
                lon,
                lat,
                polygon
            ):

                return True

        return False


    return False


# ============================================================
# POINT INSIDE FARS
# ============================================================

def point_inside_fars(
    lon,
    lat
):

    # ابتدا Bounding Box
    # برای سرعت بیشتر
    if not (
        WEST <= lon <= EAST
        and
        SOUTH <= lat <= NORTH
    ):

        return False


    # سپس مرز واقعی
    for geometry in FARS_GEOMETRIES:

        if point_in_geometry(
            lon,
            lat,
            geometry
        ):

            return True


    return False


# ============================================================
# REQUEST FIRMS
# ============================================================

def download_period(
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
            f"{source} | "
            f"HTTP {response.status_code}"
        )

        print(
            response.text[:500]
        )

        return []


    text = response.text.strip()


    if not text:

        return []


    if text.startswith("{"):

        print(
            f"{source} | پاسخ غیر CSV"
        )

        print(
            text[:500]
        )

        return []


    return text


# ============================================================
# READ CSV AND FILTER WITH FARS BOUNDARY
# ============================================================

def read_fires(
    csv_text,
    source
):

    if not csv_text:

        return []


    reader = csv.DictReader(
        io.StringIO(csv_text)
    )


    fires = []

    box_count = 0
    fars_count = 0


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


        # ----------------------------------------------------
        # Bounding Box
        # ----------------------------------------------------

        if not (
            SOUTH <= lat <= NORTH
            and
            WEST <= lon <= EAST
        ):

            continue


        box_count += 1


        # ----------------------------------------------------
        # مرز واقعی فارس
        # ----------------------------------------------------

        if not point_inside_fars(
            lon,
            lat
        ):

            continue


        fars_count += 1


        fires.append(

            {

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
            }
        )


    print(
        f"{source} | داخل Bounding Box: "
        f"{box_count} | داخل مرز فارس: "
        f"{fars_count}"
    )


    return fires


# ============================================================
# SORT
# ============================================================

def sort_key(
    fire
):

    try:

        return datetime.strptime(
            f"{fire.get('acq_date', '')} "
            f"{str(fire.get('acq_time', '')).zfill(4)}",
            "%Y-%m-%d %H%M"
        )

    except Exception:

        return datetime.min


# ============================================================
# COLLECT HISTORICAL FIRES
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

        text = download_period(
            source,
            current_date
        )


        fires = read_fires(
            text,
            source
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

all_fires.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# REMOVE EXACT DUPLICATES
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
# SORT FINAL
# ============================================================

unique_fires.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# GROUP BY DATE
# ============================================================

date_summary = {}


for fire in unique_fires:

    date_value = fire.get(
        "acq_date",
        ""
    )


    if not date_value:

        continue


    date_summary[
        date_value
    ] = (
        date_summary.get(
            date_value,
            0
        )
        + 1
    )


# ============================================================
# RESULT
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

        "type":
            "Fars Province",

        "bounding_box": [

            WEST,
            SOUTH,
            EAST,
            NORTH
        ],

        "boundary_file":
            BOUNDARY_FILE

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


# ============================================================
# SAVE
# ============================================================

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
# FINAL REPORT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "آرشیو واقعی حریق‌های داخل فارس آماده شد"
)

print(
    f"رکورد خام داخل فارس: "
    f"{len(all_fires)}"
)

print(
    f"رکورد یکتا: "
    f"{len(unique_fires)}"
)

print(
    f"روزهای دارای حریق: "
    f"{len(date_summary)}"
)

print(
    f"خروجی: "
    f"{OUTPUT_FILE}"
)

print(
    "=========================================="
)
