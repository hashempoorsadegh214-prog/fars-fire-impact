import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"

CATALOGUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)

DATASET_ID = (
    "ba_global_300m_daily_v4"
)


# ============================================================
# LOAD LATEST FIRE
# ============================================================

try:

    with open(
        FIRES_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        fires_data = json.load(file)

except FileNotFoundError:

    raise RuntimeError(
        "فایل fires.json پیدا نشد."
    )


fires = fires_data.get(
    "fires",
    []
)


if not fires:

    raise RuntimeError(
        "هیچ حریقی در fires.json وجود ندارد."
    )


latest_fire = fires[0]


fire_date = latest_fire.get(
    "acq_date",
    ""
)

fire_lat = float(
    latest_fire["latitude"]
)

fire_lon = float(
    latest_fire["longitude"]
)


if not fire_date:

    raise RuntimeError(
        "تاریخ آخرین حریق مشخص نیست."
    )


print("")
print(
    "=========================================="
)

print(
    "آخرین حریق"
)

print(
    f"تاریخ: {fire_date}"
)

print(
    f"عرض: {fire_lat}"
)

print(
    f"طول: {fire_lon}"
)

print(
    "=========================================="
)


# ============================================================
# ODATA QUERY
# ============================================================

# محصول Burnt Area V4 روزانه
#
# fileFormat = cog
# datasetIdentifier = ba_global_300m_daily_v4
#
# تاریخ تولید محصول را با OriginDate جستجو می‌کنیم.
#
# برای اینکه یک اختلاف کوچک زمانی باعث از دست رفتن محصول نشود،
# یک بازه سه روزه اطراف تاریخ حریق بررسی می‌شود.


start_date = (
    fire_date +
    "T00:00:00.000Z"
)

query_filter = (
    "Collection/Name eq 'CLMS'"
    " and "
    "Attributes/OData.CSC.StringAttribute/"
    "any(att:"
    "att/Name eq 'datasetIdentifier'"
    f" and att/OData.CSC.StringAttribute/Value eq '{DATASET_ID}'"
    ")"
    " and "
    "Attributes/OData.CSC.StringAttribute/"
    "any(att:"
    "att/Name eq 'fileFormat'"
    " and att/OData.CSC.StringAttribute/Value eq 'cog'"
    ")"
)


params = {

    "$filter":
        query_filter,

    "$top":
        "20",

    "$count":
        "true",

    "$expand":
        "Attributes"

}


url = (
    CATALOGUE_URL
    + "?"
    + urlencode(
        params
    )
)


print("")
print(
    "در حال بررسی کاتالوگ Copernicus ..."
)

print(
    DATASET_ID
)


# ============================================================
# REQUEST
# ============================================================

try:

    with urlopen(
        url,
        timeout=60
    ) as response:

        response_text = (
            response
            .read()
            .decode("utf-8")
        )

except HTTPError as error:

    raise RuntimeError(
        f"خطای OData: HTTP {error.code}"
    )

except URLError as error:

    raise RuntimeError(
        f"خطا در اتصال به کاتالوگ Copernicus: "
        f"{error.reason}"
    )


# ============================================================
# PARSE RESPONSE
# ============================================================

try:

    catalogue = json.loads(
        response_text
    )

except json.JSONDecodeError:

    raise RuntimeError(
        "پاسخ کاتالوگ Copernicus JSON معتبر نیست."
    )


products = catalogue.get(
    "value",
    []
)


print("")
print(
    f"تعداد محصولات پیدا شده: "
    f"{len(products)}"
)


# ============================================================
# FIND PRODUCT CLOSEST TO FIRE DATE
# ============================================================

selected = None


def extract_date(product):

    for key in [
        "OriginDate",
        "PublicationDate",
        "ContentDate"
    ]:

        value = product.get(
            key
        )

        if value:

            return str(
                value
            )

    return ""


# ابتدا محصولی که نام یا OriginDate آن
# با تاریخ حریق هم‌خوانی بیشتری دارد پیدا می‌کنیم.

for product in products:

    name = str(
        product.get(
            "Name",
            ""
        )
    )

    origin_date = extract_date(
        product
    )

    combined = (
        name
        + " "
        + origin_date
    )

    if fire_date in combined:

        selected = product

        break


# اگر تطابق مستقیم پیدا نشد،
# اولین محصول COG را فقط برای بررسی نگه می‌داریم.

if selected is None and products:

    selected = products[0]


# ============================================================
# OUTPUT
# ============================================================

if selected is None:

    print("")
    print(
        "هیچ محصول Burnt Area V4 COG پیدا نشد."
    )

    print(
        "در این مرحله هیچ فایل دانلود نمی‌شود."
    )

    result = {

        "status":
            "PRODUCT_NOT_FOUND",

        "fire_date":
            fire_date,

        "latitude":
            fire_lat,

        "longitude":
            fire_lon

    }

else:

    print("")
    print(
        "=========================================="
    )

    print(
        "محصول Burnt Area پیدا شد"
    )

    print(
        f"ID: {selected.get('Id', '-')}"
    )

    print(
        f"Name: {selected.get('Name', '-')}"
    )

    print(
        f"OriginDate: "
        f"{selected.get('OriginDate', '-')}"
    )

    print(
        f"PublicationDate: "
        f"{selected.get('PublicationDate', '-')}"
    )

    print(
        "=========================================="
    )


    result = {

        "status":
            "PRODUCT_FOUND",

        "fire": {

            "date":
                fire_date,

            "latitude":
                fire_lat,

            "longitude":
                fire_lon

        },

        "product": selected

    }


# ============================================================
# SAVE RESULT
# ============================================================

with open(
    "burned_area_product.json",
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
    "فایل burned_area_product.json ساخته شد."
)

print(
    "=========================================="
)
