import csv
import io
import json
import os
import time
from datetime import datetime, timedelta
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# SETTINGS
# ============================================================

MAP_KEY = os.environ.get("FIRMS_MAP_KEY")

BOUNDARY_FILE = "fars.geojson"
OUTPUT_FILE = "fire_archive_2026.json"

WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5

AREA = f"{WEST},{SOUTH},{EAST},{NORTH}"

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 8, 22)

CHUNK_DAYS = 5

SOURCES = [
    "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_SP",
    "VIIRS_NOAA21_SP",
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
]

MAX_RETRIES = 3
RETRY_DELAY = 5


# ============================================================
# CHECK MAP KEY
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets پیدا نشد."
    )


# ============================================================
# LOAD FARS
# ============================================================

with open(
    BOUNDARY_FILE,
    "r",
    encoding="utf-8"
) as file:

    boundary = json.load(file)


# ============================================================
# GEOJSON GEOMETRIES
# ============================================================

def get_geometries(geojson):

    geojson_type = geojson.get("type")

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

        if geometry:
            return [geometry]

        return []


    if geojson_type in [
        "Polygon",
        "MultiPolygon"
    ]:

        return [geojson]


    return []


FARS_GEOMETRIES = get_geometries(
    boundary
)


if not FARS_GEOMETRIES:

    raise RuntimeError(
        "هندسه معتبر برای fars.geojson پیدا نشد."
    )


print(
    f"تعداد هندسه‌های فارس: "
    f"{len(FARS_GEOMETRIES)}"
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

    for i in range(len(ring)):

        xi, yi = ring[i]
        xj, yj = ring[j]

        intersects = (
            ((yi > lat) != (yj > lat))
            and
            (
                lon <
                (
                    (xj - xi)
                    * (lat - yi)
                    / ((yj - yi) or 1e-15)
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
    coordinates
):

    if not coordinates:
        return False


    # Polygon
    if (
        isinstance(
            coordinates[0],
            list
        )
        and
        len(coordinates[0]) > 0
        and
        isinstance(
            coordinates[0][0],
            list
        )
        and
        len(coordinates[0][0]) > 0
        and
        isinstance(
            coordinates[0][0][0],
            (int, float)
        )
    ):

        # outer ring
        if not point_in_ring(
            lon,
            lat,
            coordinates[0]
        ):
            return False


        # holes
        for hole in coordinates[1:]:

            if point_in_ring(
                lon,
                lat,
                hole
            ):

                return False


        return True


    return False


# ============================================================
# POINT INSIDE GEOMETRY
# ============================================================

def point_inside_geometry(
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

    for geometry in FARS_GEOMETRIES:

        if point_inside_geometry(
            lon,
            lat,
            geometry
        ):

            return True


    return False


# ============================================================
# FIRMS REQUEST
# ============================================================

def get_firms_data(
    source,
    date
):

    date_text = date.strftime(
        "%Y-%m-%d"
    )


    url = (
        "https://firms.modaps.eosdis.nasa.gov/"
        "api/area/csv/"
        f"{MAP_KEY}/"
        f"{source}/"
        f"{AREA}/"
        f"{CHUNK_DAYS}/"
        f"{date_text}"
    )


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"FIRMS | {source} | "
            f"{date_text} | "
            f"تلاش {attempt}/{MAX_RETRIES}"
        )


        try:

            with urlopen(
                url,
                timeout=90
            ) as response:

                return response.read().decode(
                    "utf-8"
                )


        except HTTPError as error:

            print(
                f"HTTP {error.code}"
            )


        except URLError as error:

            print(
                f"Network error: {error.reason}"
            )


        except OSError as error:

            print(
                f"Network error: {error}"
            )


        if attempt < MAX_RETRIES:

            time.sleep(
                RETRY_DELAY
            )


    return None


# ============================================================
# READ CSV
# ============================================================

def read_fires(
    csv_text,
    source
):

    if not csv_text:
        return []


    results = []


    reader = csv.DictReader(
        io.StringIO(csv_text)
    )


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


        if not point_inside_fars(
            lon,
            lat
        ):

            continue


        results.append(
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

                "brightness":
                    row.get(
                        "bright_ti4",
                        ""
                    ),

                "daynight":
                    row.get(
                        "daynight",
                        ""
                    ),

                "version":
                    row.get(
                        "version",
                        ""
                    ),

                "source":
                    source
            }
        )


    return results


# ============================================================
# ARCHIVE COLLECTION
# ============================================================

all_fires = []

current_date = START_DATE


while current_date <= END_DATE:

    for source in SOURCES:

        csv_text = get_firms_data(
            source,
            current_date
        )


        if csv_text is None:

            print(
                f"داده در دسترس نبود: "
                f"{source} "
                f"{current_date.strftime('%Y-%m-%d')}"
            )

            continue


        source_fires = read_fires(
            csv_text,
            source
        )


        print(
            f"حریق داخل فارس: "
            f"{len(source_fires)}"
        )


        all_fires.extend(
            source_fires
        )


    current_date += timedelta(
        days=CHUNK_DAYS
    )


# ============================================================
# SORT
# ============================================================

def sort_key(item):

    date_value = item.get(
        "acq_date",
        ""
    )

    time_value = str(
        item.get(
            "acq_time",
            ""
        )
    ).zfill(4)


    try:

        return datetime.strptime(
            f"{date_value} {time_value}",
            "%Y-%m-%d %H%M"
        )

    except Exception:

        return datetime.min


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
            6
        ),

        round(
            fire["longitude"],
            6
        ),

        fire["acq_date"],

        fire["acq_time"],

        fire["satellite"]
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
            END_DATE.strftime(
                "%Y-%m-%d"
            )

    },

    "count":
        len(unique_fires),

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
    "آرشیو حریق ۲۰۲۶ تکمیل شد"
)

print(
    f"بازه: "
    f"{START_DATE.strftime('%Y-%m-%d')}"
    " تا "
    f"{END_DATE.strftime('%Y-%m-%d')}"
)

print(
    f"تعداد حریق‌های یکتا: "
    f"{len(unique_fires)}"
)

print(
    f"فایل: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
