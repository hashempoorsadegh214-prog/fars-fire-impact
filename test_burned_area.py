import json
import os
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


# ============================================================
# تنظیمات
# ============================================================

FIRES_FILE = "fires.json"

# فقط برای آزمایش
# خروجی واقعی Burnt Area از CDSE در مرحله بعد وارد سامانه می‌شود.


# ============================================================
# خواندن آخرین حریق
# ============================================================

with open(
    FIRES_FILE,
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
        "هیچ حریقی در fires.json پیدا نشد."
    )


latest_fire = fires[0]


lat = float(
    latest_fire["latitude"]
)

lon = float(
    latest_fire["longitude"]
)

acq_date = latest_fire.get(
    "acq_date",
    ""
)

acq_time = latest_fire.get(
    "acq_time",
    ""
)


print("")
print(
    "=========================================="
)

print(
    "آخرین حریق پیدا شد"
)

print(
    f"Latitude : {lat}"
)

print(
    f"Longitude: {lon}"
)

print(
    f"Date     : {acq_date}"
)

print(
    f"Time UTC : {acq_time}"
)

print(
    "=========================================="
)


# ============================================================
# تعیین تاریخ Burnt Area
# ============================================================

try:

    date_object = datetime.strptime(
        acq_date,
        "%Y-%m-%d"
    )

except ValueError:

    raise RuntimeError(
        f"فرمت تاریخ حریق نامعتبر است: {acq_date}"
    )


print("")
print(
    f"تاریخ حریق برای جستجوی Burnt Area: "
    f"{date_object.strftime('%Y-%m-%d')}"
)


# ============================================================
# توضیح
# ============================================================

print("")
print(
    "Burnt Area نسخه 4 روزانه Copernicus:"
)

print(
    "وضوح: 300 متر"
)

print(
    "لایه مورد نیاز: burned_fraction"
)

print(
    "این تست فعلاً فقط آخرین حریق و تاریخ آن را آماده می‌کند."
)

print(
    "اتصال مستقیم به فایل Burnt Area در مرحله بعد انجام می‌شود."
)


# ============================================================
# خلاصه
# ============================================================

result = {

    "latest_fire": {

        "latitude": lat,

        "longitude": lon,

        "date": acq_date,

        "time_utc": acq_time

    },

    "burnt_area_product":
        "Copernicus Burnt Area v4 daily 300m",

    "required_layer":
        "burned_fraction",

    "status":
        "READY_FOR_BURNT_AREA_DOWNLOAD"

}


with open(
    "burned_area_test.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        result,
        file,
        ensure_ascii=False,
        indent=2
    )


print("")
print(
    "فایل burned_area_test.json ساخته شد."
)

print(
    "=========================================="
)
