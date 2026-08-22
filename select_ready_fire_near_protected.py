import json
from datetime import datetime


# ============================================================
# SETTINGS
# ============================================================

INPUT_FILE = "archivable_fires_2026.json"

PROTECTED_FILE = "protected_areas.geojson"
HUNTING_FILE = "hunting_banned.geojson"

OUTPUT_FILE = "selected_protected_fire_2026.json"


# ============================================================
# LOAD FILES
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as file:

    archive = json.load(file)


with open(
    PROTECTED_FILE,
    "r",
    encoding="utf-8"
) as file:

    protected_data = json.load(file)


with open(
    HUNTING_FILE,
    "r",
    encoding="utf-8"
) as file:

    hunting_data = json.load(file)


fires = archive.get(
    "fires",
    []
)


if not fires:

    raise RuntimeError(
        "archivable_fires_2026.json خالی است."
    )


# ============================================================
# EXTRACT GEOMETRIES
# ============================================================

def extract_geometries(
    geojson
):

    geometry_type = geojson.get(
        "type"
    )


    if geometry_type == "FeatureCollection":

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


    if geometry_type == "Feature":

        geometry = geojson.get(
            "geometry"
        )

        return (
            [geometry]
            if geometry
            else []
        )


    if geometry_type in (
        "Polygon",
        "MultiPolygon"
    ):

        return [geojson]


    return []


protected_geometries = extract_geometries(
    protected_data
)

hunting_geometries = extract_geometries(
    hunting_data
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
                    *
                    (lat - yi)
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


# ============================================================
# POINT IN ANY GEOMETRY
# ============================================================

def point_in_any(
    lon,
    lat,
    geometries
):

    for geometry in geometries:

        if point_in_geometry(
            lon,
            lat,
            geometry
        ):

            return True


    return False


# ============================================================
# FIND READY FIRES
# ============================================================

ready_fires = [

    item

    for item in fires

    if item.get(
        "status"
    ) == "READY"

]


if not ready_fires:

    raise RuntimeError(
        "هیچ حریق READY پیدا نشد."
    )


# ============================================================
# SORT OLDEST FIRST
# ============================================================

def fire_datetime(
    item
):

    fire = item.get(
        "fire",
        {}
    )

    date_text = fire.get(
        "acq_date",
        ""
    )

    time_text = str(
        fire.get(
            "acq_time",
            ""
        )
    ).zfill(4)


    try:

        return datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H%M"
        )

    except Exception:

        return datetime.max


ready_fires.sort(
    key=fire_datetime
)


# ============================================================
# SEARCH PROTECTED / HUNTING
# ============================================================

selected = None


for item in ready_fires:

    fire = item.get(
        "fire",
        {}
    )


    try:

        lon = float(
            fire["longitude"]
        )

        lat = float(
            fire["latitude"]
        )

    except Exception:

        continue


    inside_protected = point_in_any(
        lon,
        lat,
        protected_geometries
    )


    inside_hunting = point_in_any(
        lon,
        lat,
        hunting_geometries
    )


    if (
        inside_protected
        or
        inside_hunting
    ):

        selected = {

            "original":
                item,

            "inside_protected_areas":
                inside_protected,

            "inside_hunting_banned":
                inside_hunting

        }

        break


# ============================================================
# RESULT
# ============================================================

if selected is None:

    raise RuntimeError(
        "هیچ حریق READY داخل مناطق چهارگانه "
        "یا مناطق شکار ممنوع پیدا نشد."
    )


# ============================================================
# SAVE SMALL OUTPUT
# ============================================================

original = selected[
    "original"
]

fire = original[
    "fire"
]


result = {

    "status":
        "SELECTED",

    "reason":
        "حریق READY داخل محدوده حفاظتی",

    "fire":
        fire,

    "inside_protected_areas":
        selected[
            "inside_protected_areas"
        ],

    "inside_hunting_banned":
        selected[
            "inside_hunting_banned"
        ],

    "before":
        original.get(
            "before"
        ),

    "after":
        original.get(
            "after"
        )

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
# REPORT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "حریق آزمایشی حفاظتی انتخاب شد"
)

print(
    f"تاریخ: "
    f"{fire.get('acq_date', '-')}"
)

print(
    f"زمان: "
    f"{fire.get('acq_time', '-')}"
)

print(
    f"Latitude: "
    f"{fire.get('latitude', '-')}"
)

print(
    f"Longitude: "
    f"{fire.get('longitude', '-')}"
)

print(
    f"داخل مناطق چهارگانه: "
    f"{selected['inside_protected_areas']}"
)

print(
    f"داخل شکار ممنوع: "
    f"{selected['inside_hunting_banned']}"
)

print(
    f"تصویر قبل: "
    f"{original.get('before', {}).get('date', '-')}"
)

print(
    f"تصویر بعد: "
    f"{original.get('after', {}).get('date', '-')}"
)

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
