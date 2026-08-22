import json
from datetime import datetime, timedelta


# ============================================================
# SETTINGS
# ============================================================

FIRE_ARCHIVE = "fire_archive_2026.json"
S2_ARCHIVE = "sentinel2_archive_2026.json"

OUTPUT_FILE = "archivable_fires_2026.json"

BEFORE_DAYS = 5
AFTER_DAYS = 5


# ============================================================
# LOAD FILES
# ============================================================

with open(
    FIRE_ARCHIVE,
    "r",
    encoding="utf-8"
) as file:

    fire_data = json.load(file)


with open(
    S2_ARCHIVE,
    "r",
    encoding="utf-8"
) as file:

    s2_data = json.load(file)


fires = fire_data.get(
    "fires",
    []
)

products = s2_data.get(
    "products",
    []
)


if not fires:

    raise RuntimeError(
        "fire_archive_2026.json خالی است."
    )


if not products:

    raise RuntimeError(
        "sentinel2_archive_2026.json خالی است."
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

        xi, yi = ring[i]
        xj, yj = ring[j]

        if (
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
        ):

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


    # بررسی حفره‌ها
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

    if not geometry:

        return False


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
# PREPARE SENTINEL-2 PRODUCTS
# ============================================================

s2_products = []


for product in products:

    acquisition = (
        product
        .get(
            "ContentDate",
            {}
        )
        .get(
            "Start",
            ""
        )
    )


    footprint = product.get(
        "GeoFootprint"
    )


    if not acquisition:

        continue


    if not footprint:

        continue


    try:

        acquisition_dt = datetime.fromisoformat(
            acquisition.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:

        continue


    s2_products.append(
        {

            "id":
                product.get(
                    "Id",
                    ""
                ),

            "name":
                product.get(
                    "Name",
                    ""
                ),

            "s3_path":
                product.get(
                    "S3Path",
                    ""
                ),

            "datetime":
                acquisition_dt,

            # متن برای ذخیره در JSON
            "acquisition":
                acquisition,

            "footprint":
                footprint
        }
    )


# ============================================================
# GROUP BY DATE
# ============================================================

products_by_date = {}


for product in s2_products:

    date_key = (
        product["datetime"].date()
    )


    products_by_date.setdefault(
        date_key,
        []
    ).append(
        product
    )


# ============================================================
# GET TILES COVERING FIRE
# ============================================================

def get_covering_tiles(
    lon,
    lat,
    date_value
):

    result = []


    for product in products_by_date.get(
        date_value,
        []
    ):

        if point_in_geometry(
            lon,
            lat,
            product["footprint"]
        ):

            result.append(
                {

                    "id":
                        product["id"],

                    "name":
                        product["name"],

                    "s3_path":
                        product["s3_path"],

                    "acquisition":
                        product["acquisition"]
                }
            )


    return result


# ============================================================
# FIND BEFORE / AFTER
# ============================================================

def find_before_after(
    fire_date,
    lon,
    lat
):

    before = None
    after = None


    # --------------------------------------------------------
    # BEFORE
    # نزدیک‌ترین تصویر در بازه 5 روز قبل
    # --------------------------------------------------------

    for offset in range(
        1,
        BEFORE_DAYS + 1
    ):

        candidate_date = (
            fire_date
            - timedelta(
                days=offset
            )
        )


        tiles = get_covering_tiles(
            lon,
            lat,
            candidate_date
        )


        if tiles:

            before = {

                "date":
                    candidate_date.strftime(
                        "%Y-%m-%d"
                    ),

                "days_from_fire":
                    offset,

                "tile_count":
                    len(tiles),

                "tiles":
                    tiles
            }

            break


    # --------------------------------------------------------
    # AFTER
    # نزدیک‌ترین تصویر در بازه 5 روز بعد
    # --------------------------------------------------------

    for offset in range(
        1,
        AFTER_DAYS + 1
    ):

        candidate_date = (
            fire_date
            + timedelta(
                days=offset
            )
        )


        tiles = get_covering_tiles(
            lon,
            lat,
            candidate_date
        )


        if tiles:

            after = {

                "date":
                    candidate_date.strftime(
                        "%Y-%m-%d"
                    ),

                "days_from_fire":
                    offset,

                "tile_count":
                    len(tiles),

                "tiles":
                    tiles
            }

            break


    return (
        before,
        after
    )


# ============================================================
# PROCESS FIRES
# ============================================================

results = []

ready = 0
waiting = 0
no_before = 0


total_fires = len(
    fires
)


for index, fire in enumerate(
    fires,
    start=1
):

    if index % 500 == 0:

        print(
            f"بررسی {index}/{total_fires}"
        )


    date_text = fire.get(
        "acq_date"
    )


    if not date_text:

        continue


    try:

        fire_date = datetime.strptime(
            date_text,
            "%Y-%m-%d"
        ).date()

    except Exception:

        continue


    try:

        lon = float(
            fire["longitude"]
        )

        lat = float(
            fire["latitude"]
        )

    except Exception:

        continue


    before, after = find_before_after(
        fire_date,
        lon,
        lat
    )


    if before and after:

        status = "READY"

        ready += 1


    elif before:

        status = (
            "WAITING_FOR_AFTER_IMAGE"
        )

        waiting += 1


    else:

        status = "NO_BEFORE_IMAGE"

        no_before += 1


    results.append(
        {

            "fire":
                fire,

            "status":
                status,

            "before":
                before,

            "after":
                after

        }
    )


# ============================================================
# SAVE SUMMARY
# ============================================================

result = {

    "status":
        "SUCCESS",

    "rules":
        {

            "before_days":
                BEFORE_DAYS,

            "after_days":
                AFTER_DAYS
        },

    "summary":
        {

            "total_fires":
                len(results),

            "ready":
                ready,

            "waiting_for_after":
                waiting,

            "no_before":
                no_before
        },

    "fires":
        results
}


# ============================================================
# SAVE JSON
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
    "تطبیق FIRMS و Sentinel-2 تمام شد"
)

print(
    f"کل رکوردها: {len(results)}"
)

print(
    f"آماده محاسبه: {ready}"
)

print(
    f"منتظر تصویر بعد: {waiting}"
)

print(
    f"بدون تصویر قبل: {no_before}"
)

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
