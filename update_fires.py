import csv
import io
import json
import os
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
# GET GEOMETRIES FROM GEOJSON
# ============================================================

def get_geometries(geojson):

    geojson_type = geojson.get("type")

    # حالت FeatureCollection
    if geojson_type == "FeatureCollection":

        geometries = []

        for feature in geojson.get("features", []):

            geometry = feature.get("geometry")

            if geometry:
                geometries.append(geometry)

        return geometries

    # حالت Feature
    if geojson_type == "Feature":

        geometry = geojson.get("geometry")

        if geometry:
            return [geometry]

        return []

    # حالت مستقیم Geometry
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

def point_in_ring(lon, lat, ring):

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

    # Polygon:
    # [
    #   outer_ring,
    #   hole_1,
    #   hole_2
    # ]

    if (
        isinstance(coordinates, list)
        and len(coordinates) > 0
        and isinstance(coordinates[0], list)
        and len(coordinates[0]) > 0
        and isinstance(coordinates[0][0], list)
        and len(coordinates[0][0]) > 0
        and isinstance(coordinates[0][0][0], (int, float))
    ):

        # بیرون از پوسته اصلی
        if not point_in_ring(
            lon,
            lat,
            coordinates[0]
        ):
            return False

        # بررسی سوراخ‌های داخلی
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
# GET FIRMS DATA
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

    print(
        f"دریافت داده {source} ..."
    )

    try:

        with urlopen(
            url,
            timeout=60
        ) as response:

            return response.read().decode(
                "utf-8"
            )

    except HTTPError as error:

        raise RuntimeError(
            f"FIRMS HTTP Error "
            f"{error.code}: {source}"
        )

    except URLError as error:

        raise RuntimeError(
            f"خطا در اتصال به FIRMS: "
            f"{error.reason}"
        )


# ============================================================
# READ FIRE DATA
# ============================================================

fires = []


for source in SOURCES:

    csv_text = get_firms_data(
        source
    )

    reader = csv.DictReader(
        io.StringIO(csv_text)
    )

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
            KeyError
        ):

            continue


        # فقط نقاط داخل فارس
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


        # ----------------------------------------------------
        # UTC TIME
        # ----------------------------------------------------

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

    seen.add(key)

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
    f"فایل خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
