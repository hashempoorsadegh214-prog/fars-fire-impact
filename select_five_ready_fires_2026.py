import json
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2


# ============================================================
# SETTINGS
# ============================================================

INPUT_FILE = "archivable_fires_2026.json"
OUTPUT_FILE = "selected_five_ready_fires_2026.json"

TARGET_COUNT = 5

# حداقل فاصله بین دو حریق انتخاب‌شده
MIN_DISTANCE_KM = 5.0


# ============================================================
# LOAD
# ============================================================

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as file:

    data = json.load(file)


fires = data.get(
    "fires",
    []
)


if not fires:

    raise RuntimeError(
        "archivable_fires_2026.json خالی است."
    )


# ============================================================
# READY FIRES
# ============================================================

ready = []

for item in fires:

    if item.get("status") != "READY":
        continue

    fire = item.get(
        "fire",
        {}
    )

    try:

        date_text = fire["acq_date"]

        time_text = str(
            fire.get(
                "acq_time",
                ""
            )
        ).zfill(4)

        fire_datetime = datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H%M"
        )

        lat = float(
            fire["latitude"]
        )

        lon = float(
            fire["longitude"]
        )

    except Exception:

        continue


    ready.append(
        {
            "datetime":
                fire_datetime,

            "fire":
                fire,

            "before":
                item.get("before"),

            "after":
                item.get("after")

        }
    )


if not ready:

    raise RuntimeError(
        "هیچ حریق READY پیدا نشد."
    )


# ============================================================
# SORT
# قدیمی‌ترین‌ها اول
# ============================================================

ready.sort(
    key=lambda item:
        item["datetime"]
)


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def distance_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    earth_radius_km = 6371.0

    lat1 = radians(
        lat1
    )

    lat2 = radians(
        lat2
    )

    dlat = radians(
        lat2 - lat1
    )

    dlon = radians(
        lon2 - lon1
    )

    a = (
        sin(dlat / 2) ** 2
        +
        cos(lat1)
        *
        cos(lat2)
        *
        sin(dlon / 2) ** 2
    )

    c = (
        2
        *
        atan2(
            sqrt(a),
            sqrt(1 - a)
        )
    )

    return (
        earth_radius_km
        *
        c
    )


# ============================================================
# SELECT DIVERSE FIRES
# ============================================================

selected = []


for candidate in ready:

    fire = candidate["fire"]

    lat = float(
        fire["latitude"]
    )

    lon = float(
        fire["longitude"]
    )

    too_close = False


    for existing in selected:

        existing_fire = existing["fire"]

        existing_lat = float(
            existing_fire["latitude"]
        )

        existing_lon = float(
            existing_fire["longitude"]
        )

        distance = distance_km(
            lat,
            lon,
            existing_lat,
            existing_lon
        )


        # هم حریق‌های خیلی نزدیک
        # و هم نقاط یک منطقه را کاهش می‌دهیم.
        if distance < MIN_DISTANCE_KM:

            too_close = True

            break


    if too_close:
        continue


    selected.append(
        candidate
    )


    if len(selected) >= TARGET_COUNT:
        break


# ============================================================
# FALLBACK
# اگر به 5 مورد با فاصله 5 کیلومتر نرسیدیم،
# از READYها به‌صورت ترتیبی تکمیل می‌کنیم.
# ============================================================

if len(selected) < TARGET_COUNT:

    selected_keys = {
        (
            item["fire"].get("acq_date"),
            item["fire"].get("acq_time"),
            item["fire"].get("latitude"),
            item["fire"].get("longitude")
        )
        for item in selected
    }


    for candidate in ready:

        key = (
            candidate["fire"].get(
                "acq_date"
            ),

            candidate["fire"].get(
                "acq_time"
            ),

            candidate["fire"].get(
                "latitude"
            ),

            candidate["fire"].get(
                "longitude"
            )
        )


        if key in selected_keys:
            continue


        selected.append(
            candidate
        )

        selected_keys.add(
            key
        )


        if len(selected) >= TARGET_COUNT:
            break


# ============================================================
# BUILD OUTPUT
# ============================================================

output_fires = []


for index, item in enumerate(
    selected[:TARGET_COUNT],
    start=1
):

    fire = item["fire"]


    output_fires.append(
        {

            "id":
                index,

            "fire":
                fire,

            "before":
                item["before"],

            "after":
                item["after"]

        }
    )


result = {

    "status":
        "SUCCESS",

    "selection_rule":
        {

            "requested":
                TARGET_COUNT,

            "minimum_distance_km":
                MIN_DISTANCE_KM

        },

    "count":
        len(output_fires),

    "fires":
        output_fires

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
# REPORT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "5 حریق READY انتخاب شدند"
)

print(
    f"تعداد نهایی: "
    f"{len(output_fires)}"
)

print(
    "=========================================="
)


for item in output_fires:

    fire = item["fire"]

    print("")

    print(
        f"#{item['id']} | "
        f"{fire.get('acq_date', '-')}"
        f" | "
        f"{fire.get('acq_time', '-')}"
    )

    print(
        f"مختصات: "
        f"{fire.get('latitude', '-')}, "
        f"{fire.get('longitude', '-')}"
    )

    print(
        f"قبل: "
        f"{item['before'].get('date', '-') if item['before'] else '-'}"
    )

    print(
        f"بعد: "
        f"{item['after'].get('date', '-') if item['after'] else '-'}"
    )


print("")

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
