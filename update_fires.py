import csv
import io
import json
import os
import time
from datetime import datetime
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# SETTINGS
# ============================================================

MAP_KEY = os.environ.get("FIRMS_MAP_KEY")

WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5

AREA = f"{WEST},{SOUTH},{EAST},{NORTH}"

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
]

OUTPUT_FILE = "fires.json"
BOUNDARY_FILE = "fars.geojson"

MAX_RETRIES = 3
RETRY_DELAY = 10


# ============================================================
# CHECK MAP KEY
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets پیدا نشد."
    )


# ============================================================
# LOAD FARS GEOJSON
# ============================================================

with open(
    BOUNDARY_FILE,
    "r",
    encoding="utf-8"
) as file:

    boundary = json.load(file)


# ============================================================
# GET GEOMETRIES
# ============================================================

def get_geometries(geojson):

    geojson_type = geojson.get("type")

    # FeatureCollection
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

    # Feature
    if geojson_type == "Feature":

        geometry = geojson.get(
            "geometry"
        )

        if geometry:
            return [geometry]

        return []

    # Direct Geometry
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
    f"تعداد هندسه‌های مرز فارس: "
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
        isinstance(coordinates, list)
        and len(coordinates) > 0
        and isinstance(coordinates[0], list)
        and len(coordinates[0]) > 0
        and isinstance(coordinates[0][0], list)
        and len(coordinates[0][0]) > 0
        and isinstance(
            coordinates[0][0][0],
            (int, float)
        )
    ):

        # پوسته بیرونی
        if not point_in_ring(
            lon,
            lat,
            coordinates[0]
        ):
            return False

        # سوراخ‌های داخلی
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
# GET FIRMS DATA WITH RETRY
# ============================================================

def get_firms_data(source):

    url = (
        "https://firms.modaps.eosdis.nasa.gov/"
        f"api/area/csv/"
        f"{MAP_KEY}/"
        f"{source}/"
        f"{AREA}/"
        "1"
    )

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"درخواست FIRMS برای {source} "
            f"(تلاش {attempt}/{MAX_RETRIES})"
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
                f"خطای HTTP برای {source}: "
                f"{error.code}"
            )

        except URLError as error:

            print(
                f"خطای شبکه برای {source}: "
                f"{error.reason}"
            )

        except OSError as error:

            print(
                f"خطای شبکه سیستم برای {source}: "
                f"{error}"
            )

        if attempt < MAX_RETRIES:

            print(
                f"{RETRY_DELAY} ثانیه صبر می‌کنیم..."
            )

            time.sleep(
                RETRY_DELAY
            )

    print(
        f"داده {source} در این اجرا در دسترس نبود."
    )

    return None


# ============================================================
# READ FIRE DATA
# ============================================================

fires = []

successful_sources = []

failed_sources = []


for source in SOURCES:

    csv_text = get_firms_data(
        source
    )

    if csv_text is None:

        failed_sources.append(
            source
        )

        continue


    successful_sources.append(
        source
    )


    try:

        reader = csv.DictReader(
            io.StringIO(csv_text)
        )

    except Exception as error:

        print(
            f"خطا در خواندن CSV "
            f"{source}: {error}"
        )

        failed_sources.append(
            source
        )

        continue


    source_count = 0


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
            KeyError,
            TypeError
        ):

            continue


        # فقط حریق‌های داخل فارس
        if not point_inside_fars(
            lon,
            lat
        ):
            continue


        source_count += 1


        acq_date = row.get(
            "acq_date",
            ""
        )

        acq_time = row.get(
            "acq_time",
            ""
        )


        # ====================================================
        # UTC TIME
        # ====================================================

        try:

            time_value = int(
                str(acq_time).zfill(4)
            )

            hour = time_value // 100
            minute = time_value % 100

            acquisition_utc = (
                f"{acq_date} "
                f"{hour:02d}:"
                f"{minute:02d}:00"
            )

        except Exception:

            acquisition_utc = (
                f"{acq_date} "
                f"{acq_time}"
            )


        # ====================================================
        # FIRE RECORD
        # ====================================================

        fires.append(
            {
                "latitude": lat,

                "longitude": lon,

                "acq_date": acq_date,

                "acq_time": acq_time,

                "acquisition_utc":
                    acquisition_utc,

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

                "source":
                    source
            }
        )


    print(
        f"{source}: "
        f"{source_count} حریق داخل فارس"
    )


# ============================================================
# IF NO SOURCE WAS AVAILABLE
# ============================================================

if not successful_sources:

    print("")
    print(
        "هیچ‌یک از سرویس‌های FIRMS "
        "در این اجرا در دسترس نبودند."
    )

    if os.path.exists(
        OUTPUT_FILE
    ):

        print(
            "فایل fires.json قبلی حفظ می‌شود."
        )

        print(
            "Workflow بدون خطای اطلاعاتی "
            "پایان می‌یابد."
        )

        raise SystemExit(0)

    else:

        print(
            "فایل قبلی fires.json وجود ندارد."
        )

        output = {

            "updated_at_utc":
                datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

            "count": 0,

            "fires": [],

            "status":
                "FIRMS temporarily unavailable"
        }

        with open(
            OUTPUT_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                output,
                file,
                ensure_ascii=False,
                indent=2
            )

        raise SystemExit(0)


# ============================================================
# SORT
# ============================================================

def sort_key(item):

    value = item.get(
        "acquisition_utc",
        ""
    )

    try:

        return datetime.strptime(
            value,
            "%Y-%m-%d %H:%M:%S"
        )

    except Exception:

        return datetime.min


fires.sort(
    key=sort_key,
    reverse=True
)


# ============================================================
# REMOVE DUPLICATES
# ============================================================

unique_fires = []

seen = set()


for fire in fires:

    key = (
        fire["latitude"],
        fire["longitude"],
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
# CREATE OUTPUT
# ============================================================

output = {

    "updated_at_utc":
        datetime.utcnow().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

    "count":
        len(unique_fires),

    "successful_sources":
        successful_sources,

    "failed_sources":
        failed_sources,

    "fires":
        unique_fires
}


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        output,
        file,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# RESULT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    f"تعداد کل حریق‌های فارس: "
    f"{len(unique_fires)}"
)

print(
    f"منابع موفق: "
    f"{', '.join(successful_sources) if successful_sources else 'هیچ‌کدام'}"
)

print(
    f"منابع ناموفق: "
    f"{', '.join(failed_sources) if failed_sources else 'هیچ‌کدام'}"
)

print(
    f"فایل خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
