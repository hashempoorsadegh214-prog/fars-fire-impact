import json
import time
from datetime import datetime

import requests


# ============================================================
# SETTINGS
# ============================================================

OUTPUT_FILE = "sentinel2_archive_2026.json"

CATALOGUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)

# نقطه‌ای که قبلاً برای آن Sentinel-2 پیدا کردیم
LATITUDE = 28.68269
LONGITUDE = 52.09232

START_DATE = datetime(
    2026,
    1,
    1
)

END_DATE = datetime(
    2026,
    8,
    23
)

REQUEST_TIMEOUT = 120


# ============================================================
# SEARCH
# ============================================================

start_iso = (
    START_DATE.strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )
)

end_iso = (
    END_DATE.strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )
)


# فقط نقطه
point_wkt = (
    f"POINT({LONGITUDE} {LATITUDE})"
)


spatial_filter = (
    "OData.CSC.Intersects("
    "area=geography'SRID=4326;"
    f"{point_wkt}"
    "')"
)


collection_filter = (
    "Collection/Name eq 'SENTINEL-2'"
)


product_filter = (
    "Attributes/"
    "OData.CSC.StringAttribute/"
    "any("
    "att:"
    "att/Name eq 'productType'"
    " and "
    "att/"
    "OData.CSC.StringAttribute/"
    "Value eq 'S2MSI2A'"
    ")"
)


date_filter = (
    "ContentDate/Start gt "
    f"{start_iso}"
    " and "
    "ContentDate/Start lt "
    f"{end_iso}"
)


query_filter = (
    collection_filter
    + " and "
    + product_filter
    + " and "
    + spatial_filter
    + " and "
    + date_filter
)


params = {

    "$filter":
        query_filter,

    "$orderby":
        "ContentDate/Start desc",

    "$top":
        "100",

    "$select":
        "Id,Name,S3Path,ContentDate"

}


# ============================================================
# REQUEST
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "تست آرشیو Sentinel-2"
)

print(
    f"مختصات: "
    f"{LATITUDE}, {LONGITUDE}"
)

print(
    f"بازه: "
    f"{START_DATE.strftime('%Y-%m-%d')}"
    " تا "
    f"{END_DATE.strftime('%Y-%m-%d')}"
)

print(
    "=========================================="
)


for attempt in range(
    1,
    4
):

    try:

        response = requests.get(
            CATALOGUE_URL,
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"HTTP: {response.status_code}"
        )

        if response.status_code != 200:

            print(
                response.text
            )

            if attempt < 3:

                time.sleep(5)

                continue

            raise RuntimeError(
                "درخواست OData ناموفق بود."
            )


        data = response.json()

        products = data.get(
            "value",
            []
        )

        break


    except Exception as error:

        print(
            f"خطا: {error}"
        )

        if attempt < 3:

            time.sleep(5)

        else:

            raise


# ============================================================
# RESULT
# ============================================================

print("")
print(
    "تعداد تصاویر پیدا شده:"
)

print(
    len(products)
)


for index, product in enumerate(
    products,
    start=1
):

    print("")
    print(
        f"#{index}"
    )

    print(
        f"Name: "
        f"{product.get('Name', '-')}"
    )

    print(
        f"Date: "
        f"{product.get('ContentDate', {}).get('Start', '-')}"
    )


# ============================================================
# SAVE
# ============================================================

result = {

    "status":
        "SUCCESS",

    "test_point": {

        "latitude":
            LATITUDE,

        "longitude":
            LONGITUDE

    },

    "period": {

        "start":
            START_DATE.strftime(
                "%Y-%m-%d"
            ),

        "end":
            (
                END_DATE
            ).strftime(
                "%Y-%m-%d"
            )

    },

    "product_type":
        "S2MSI2A",

    "product_count":
        len(products),

    "products":
        products

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


print("")
print(
    "=========================================="
)

print(
    "نتیجه در sentinel2_archive_2026.json ذخیره شد."
)

print(
    "=========================================="
)
