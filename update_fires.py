import csv
import io
import json
import os
from datetime import datetime
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# تنظیمات
# ============================================================

MAP_KEY = os.environ.get("FIRMS_MAP_KEY")

# محدوده تقریبی استان فارس برای درخواست FIRMS
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
# بررسی MAP KEY
# ============================================================

if not MAP_KEY:
    raise RuntimeError(
        "FIRMS_MAP_KEY در GitHub Secrets پیدا نشد."
    )


# ============================================================
# خواندن مرز فارس
# ============================================================

with open(
    BOUNDARY_FILE,
    "r",
    encoding="utf-8"
) as file:

    boundary = json.load(file)


# ============================================================
# Point in Polygon
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
                lon
                <
                (xj - xi)
                * (lat - yi)
                / ((yj - yi) or 1e-15)
                + xi
            )
        )

        if intersects:
            inside = not inside

        j = i

    return inside


def point_in_polygon(lon, lat, coordinates):

    if not coordinates:
        return False

    # Polygon
    if isinstance(coordinates[0][0][0], (int, float)):

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

    # MultiPolygon
    for polygon in coordinates:

        if point_in_polygon(
            lon,
            lat,
            polygon
        ):
            return True

    return False


def point_inside_fars(lon, lat):

    geometry = boundary["geometry"]

    geometry_type = geometry["type"]

    coordinates = geometry["coordinates"]

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


# ============================================================
# دریافت داده از FIRMS
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
            f"FIRMS HTTP Error {error.code}: "
            f"{source}"
        )

    except URLError as error:

        raise RuntimeError(
            f"خطا در اتصال به FIRMS: "
            f"{error.reason}"
        )


# ============================================================
# پردازش حریق‌ها
# ============================================================

fires = []


for source in SOURCES:

    print(
        f"دریافت داده {source} ..."
    )

    csv_text = get_firms_data(
        source
    )

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
            KeyError
        ):

            continue


        # فقط حریق‌هایی که واقعاً داخل فارس هستند
        if not point_inside_fars(
            lon,
            lat
        ):
            continue


        acq_date = row.get(
            "acq_date",
            ""
        )

        acq_time = row.get(
            "acq_time",
            ""
        )

        # ساعت FIRMS به صورت UTC
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


# ============================================================
# مرتب‌سازی
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
# حذف داده‌های کاملاً تکراری
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
# ساخت خروجی
# ============================================================

output = {

    "updated_at_utc":
        datetime.utcnow()
        .strftime(
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


print(
    "=========================================="
)

print(
    f"تعداد حریق‌های فارس: "
    f"{len(unique_fires)}"
)

print(
    f"فایل خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
