import json
from datetime import datetime


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"
ARCHIVE_FILE = "sentinel2_archive_2026.json"

OUTPUT_FILE = "archivable_fires_2026.json"

BEFORE_DAYS = 5
AFTER_DAYS = 5


# ============================================================
# LOAD DATA
# ============================================================

with open(
    FIRES_FILE,
    "r",
    encoding="utf-8"
) as file:
    fires_data = json.load(file)


with open(
    ARCHIVE_FILE,
    "r",
    encoding="utf-8"
) as file:
    archive_data = json.load(file)


fires = fires_data.get(
    "fires",
    []
)

acquisitions = archive_data.get(
    "acquisitions",
    []
)


if not fires:
    raise RuntimeError(
        "fires.json حاوی حریق نیست."
    )


if not acquisitions:
    raise RuntimeError(
        "sentinel2_archive_2026.json "
        "حاوی برداشت Sentinel-2 نیست."
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

        if (
            ((yi > lat) != (yj > lat))
            and
            (
                lon <
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
    coordinates
):

    if not coordinates:
        return False


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
# PREPARE SENTINEL-2 ACQUISITIONS
# ============================================================

sentinel_acquisitions = []


for acquisition in acquisitions:

    acquisition_time = acquisition.get(
        "acquisition"
    )

    if not acquisition_time:
        continue


    try:

        acquisition_dt = datetime.fromisoformat(
            acquisition_time.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:

        continue


    sentinel_acquisitions.append(
        {
            "datetime":
                acquisition_dt,

            "acquisition":
                acquisition_time,

            "tile_count":
                acquisition.get(
                    "tile_count",
                    0
                ),

            "tiles":
                acquisition.get(
                    "tiles",
                    []
                )
        }
    )


# ============================================================
# FIND PRODUCTS COVERING FIRE POINT
# ============================================================

def tiles_covering_fire(
    fire_lon,
    fire_lat,
    acquisition
):

    matching_tiles = []


    for tile in acquisition.get(
        "tiles",
        []
    ):

        geofootprint = tile.get(
            "geofootprint"
        )


        if geofootprint is None:

            # اگر footprint در آرشیو ذخیره نشده،
            # فعلاً Tile را نگه می‌داریم.
            matching_tiles.append(
                tile
            )

            continue


        if point_in_geometry(
            fire_lon,
            fire_lat,
            geofootprint
        ):

            matching_tiles.append(
                tile
            )


    return matching_tiles


# ============================================================
# FIND BEFORE / AFTER
# ============================================================

def find_images_for_fire(
    fire
):

    fire_date_text = fire.get(
        "acq_date"
    )

    if not fire_date_text:

        return None, None


    fire_date = datetime.strptime(
        fire_date_text,
        "%Y-%m-%d"
    ).date()


    fire_lon = float(
        fire["longitude"]
    )

    fire_lat = float(
        fire["latitude"]
    )


    before_candidates = []
    after_candidates = []


    for acquisition in sentinel_acquisitions:

        acquisition_date = (
            acquisition["datetime"].date()
        )


        difference = (
            acquisition_date
            -
            fire_date
        ).days


        # ----------------------------
        # BEFORE
        # ----------------------------

        if (
            -BEFORE_DAYS
            <= difference
            <= -1
        ):

            tiles = tiles_covering_fire(
                fire_lon,
                fire_lat,
                acquisition
            )


            if tiles:

                before_candidates.append(
                    {
                        "difference":
                            difference,

                        "acquisition":
                            acquisition[
                                "acquisition"
                            ],

                        "tile_count":
                            len(tiles),

                        "tiles":
                            tiles
                    }
                )


        # ----------------------------
        # AFTER
        # ----------------------------

        if (
            1
            <= difference
            <= AFTER_DAYS
        ):

            tiles = tiles_covering_fire(
                fire_lon,
                fire_lat,
                acquisition
            )


            if tiles:

                after_candidates.append(
                    {
                        "difference":
                            difference,

                        "acquisition":
                            acquisition[
                                "acquisition"
                            ],

                        "tile_count":
                            len(tiles),

                        "tiles":
                            tiles
                    }
                )


    # نزدیک‌ترین قبل
    before = None

    if before_candidates:

        before = min(
            before_candidates,
            key=lambda item:
                abs(
                    item["difference"]
                )
        )


    # نزدیک‌ترین بعد
    after = None

    if after_candidates:

        after = min(
            after_candidates,
            key=lambda item:
                abs(
                    item["difference"]
                )
        )


    return before, after


# ============================================================
# PROCESS FIRES
# ============================================================

results = []


for index, fire in enumerate(
    fires,
    start=1
):

    print("")
    print(
        f"بررسی حریق {index}/{len(fires)}"
    )


    before, after = find_images_for_fire(
        fire
    )


    if before and after:

        status = "READY"

    elif before:

        status = "WAITING_FOR_AFTER_IMAGE"

    else:

        status = "NO_BEFORE_IMAGE"


    print(
        f"تاریخ حریق: "
        f"{fire.get('acq_date', '-')}"
    )

    print(
        f"وضعیت: {status}"
    )


    if before:

        print(
            f"قبل: "
            f"{before['acquisition']}"
        )

        print(
            f"Tileهای قبل: "
            f"{before['tile_count']}"
        )


    if after:

        print(
            f"بعد: "
            f"{after['acquisition']}"
        )

        print(
            f"Tileهای بعد: "
            f"{after['tile_count']}"
        )


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
# SUMMARY
# ============================================================

ready = sum(
    1
    for item in results
    if item["status"] == "READY"
)


waiting = sum(
    1
    for item in results
    if item["status"]
    == "WAITING_FOR_AFTER_IMAGE"
)


no_before = sum(
    1
    for item in results
    if item["status"]
    == "NO_BEFORE_IMAGE"
)


# ============================================================
# SAVE
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
    "تطبیق حریق و Sentinel-2 تمام شد"
)

print(
    f"کل حریق‌ها: {len(results)}"
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
