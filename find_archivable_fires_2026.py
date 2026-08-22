import json
from datetime import datetime, timedelta


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"
ARCHIVE_FILE = "sentinel2_archive_2026.json"

OUTPUT_FILE = "archivable_fires_2026.json"

# حداکثر فاصله برای تصویر قبل
BEFORE_DAYS = 5

# حداکثر فاصله برای تصویر بعد
AFTER_DAYS = 5


# ============================================================
# LOAD FILES
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
        "هیچ حریقی در fires.json پیدا نشد."
    )


if not acquisitions:
    raise RuntimeError(
        "هیچ برداشت Sentinel-2 در آرشیو پیدا نشد."
    )


# ============================================================
# PREPARE SENTINEL-2 ACQUISITIONS
# ============================================================

sentinel_dates = []


for item in acquisitions:

    acquisition_text = item.get(
        "acquisition"
    )

    if not acquisition_text:
        continue

    try:

        acquisition_date = datetime.fromisoformat(
            acquisition_text.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:

        continue

    sentinel_dates.append(
        {
            "datetime":
                acquisition_date,

            "acquisition":
                acquisition_text,

            "tile_count":
                item.get(
                    "tile_count",
                    0
                ),

            "tiles":
                item.get(
                    "tiles",
                    []
                )
        }
    )


sentinel_dates.sort(
    key=lambda x: x["datetime"]
)


# ============================================================
# FIND BEFORE / AFTER
# ============================================================

def find_before_after(
    fire_date
):

    before_candidates = []
    after_candidates = []


    for item in sentinel_dates:

        image_date = item["datetime"]

        difference = (
            image_date.date()
            -
            fire_date.date()
        ).days


        # ----------------------------
        # قبل حریق
        # ----------------------------

        if (
            -BEFORE_DAYS
            <= difference
            <= -1
        ):

            before_candidates.append(
                item
            )


        # ----------------------------
        # بعد حریق
        # ----------------------------

        if (
            1
            <= difference
            <= AFTER_DAYS
        ):

            after_candidates.append(
                item
            )


    # نزدیک‌ترین تصویر قبل
    before = None

    if before_candidates:

        before = min(
            before_candidates,
            key=lambda x:
                abs(
                    (
                        x["datetime"].date()
                        -
                        fire_date.date()
                    ).days
                )
        )


    # نزدیک‌ترین تصویر بعد
    after = None

    if after_candidates:

        after = min(
            after_candidates,
            key=lambda x:
                abs(
                    (
                        x["datetime"].date()
                        -
                        fire_date.date()
                    ).days
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

    date_text = fire.get(
        "acq_date"
    )

    if not date_text:
        continue


    try:

        fire_date = datetime.strptime(
            date_text,
            "%Y-%m-%d"
        )

    except Exception:

        continue


    before, after = find_before_after(
        fire_date
    )


    if before and after:

        status = "READY"

    elif before:

        status = "WAITING_FOR_AFTER_IMAGE"

    else:

        status = "NO_BEFORE_IMAGE"


    results.append(

        {

            "fire": fire,

            "status": status,

            "before": before,

            "after": after

        }

    )


# ============================================================
# SUMMARY
# ============================================================

ready_count = sum(
    1
    for item in results
    if item["status"] == "READY"
)


waiting_count = sum(
    1
    for item in results
    if item["status"]
    == "WAITING_FOR_AFTER_IMAGE"
)


no_before_count = sum(
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

    "rules": {

        "before_days":
            BEFORE_DAYS,

        "after_days":
            AFTER_DAYS

    },

    "summary": {

        "total_fires":
            len(results),

        "ready":
            ready_count,

        "waiting_for_after":
            waiting_count,

        "no_before":
            no_before_count

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
# REPORT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "تطبیق حریق با آرشیو Sentinel-2"
)

print(
    f"کل حریق‌ها: {len(results)}"
)

print(
    f"آماده پردازش: {ready_count}"
)

print(
    f"منتظر تصویر بعد: {waiting_count}"
)

print(
    f"بدون تصویر قبل: {no_before_count}"
)

print(
    f"خروجی: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
