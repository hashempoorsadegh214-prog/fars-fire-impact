import json
from datetime import datetime


# ============================================================
# SETTINGS
# ============================================================

INPUT_FILE = "archivable_fires_2026.json"
OUTPUT_FILE = "selected_fire_2026.json"


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
# SELECT READY FIRES
# ============================================================

ready_fires = []

for item in fires:

    if item.get(
        "status"
    ) != "READY":

        continue


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

        fire_datetime = datetime.strptime(
            f"{date_text} {time_text}",
            "%Y-%m-%d %H%M"
        )

    except Exception:

        fire_datetime = datetime.min


    ready_fires.append(
        {
            "fire_datetime":
                fire_datetime,

            "item":
                item
        }
    )


if not ready_fires:

    raise RuntimeError(
        "هیچ حریق READY پیدا نشد."
    )


# ============================================================
# OLDEST READY FIRE
# ============================================================

ready_fires.sort(
    key=lambda x:
        x["fire_datetime"]
)


selected = ready_fires[0]["item"]


# ============================================================
# CREATE SMALL OUTPUT
# ============================================================

fire = selected["fire"]

before = selected.get(
    "before"
)

after = selected.get(
    "after"
)


result = {

    "status":
        "SELECTED",

    "reason":
        "اولین حریق READY در آرشیو 2026",

    "fire":
        fire,

    "before":
        before,

    "after":
        after
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
    "اولین حریق READY انتخاب شد"
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
    f"تصویر قبل: "
    f"{before.get('date', '-') if before else '-'}"
)

print(
    f"Tile قبل: "
    f"{before.get('tile_count', '-') if before else '-'}"
)

print(
    f"تصویر بعد: "
    f"{after.get('date', '-') if after else '-'}"
)

print(
    f"Tile بعد: "
    f"{after.get('tile_count', '-') if after else '-'}"
)

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
