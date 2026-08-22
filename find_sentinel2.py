import json
import requests
from datetime import datetime, timedelta, timezone


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"

CATALOGUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)

# حداکثر درصد ابر
MAX_CLOUD = 30.0


# ============================================================
# LOAD LATEST FIRE
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


fire_date_text = latest_fire.get(
    "acq_date"
)

fire_lat = float(
    latest_fire["latitude"]
)

fire_lon = float(
    latest_fire["longitude"]
)


if not fire_date_text:

    raise RuntimeError(
        "تاریخ آخرین حریق مشخص نیست."
    )


fire_date = datetime.strptime(
    fire_date_text,
    "%Y-%m-%d"
).replace(
    tzinfo=timezone.utc
)


print("")
print(
    "=========================================="
)

print(
    "آخرین حریق"
)

print(
    f"تاریخ: {fire_date_text}"
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
# SEARCH FUNCTION
# ============================================================

def search_sentinel2(
    start_date,
    end_date
):

    start_iso = (
        start_date.strftime(
            "%Y-%m-%dT00:00:00.000Z"
        )
    )

    end_iso = (
        end_date.strftime(
            "%Y-%m-%dT00:00:00.000Z"
        )
    )


    # --------------------------------------------------------
    # نقطه حریق
    # --------------------------------------------------------

    point_wkt = (
        f"POINT({fire_lon} {fire_lat})"
    )


    # --------------------------------------------------------
    # فیلتر مکانی رسمی CDSE
    # --------------------------------------------------------

    spatial_filter = (
        "OData.CSC.Intersects("
        "area=geography'SRID=4326;"
        f"{point_wkt}"
        "')"
    )


    # --------------------------------------------------------
    # Sentinel-2 L2A
    # --------------------------------------------------------

    product_type_filter = (
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


    # --------------------------------------------------------
    # Cloud cover
    # --------------------------------------------------------

    cloud_filter = (
        "Attributes/"
        "OData.CSC.DoubleAttribute/"
        "any("
        "att:"
        "att/Name eq 'cloudCover'"
        " and "
        "att/"
        "OData.CSC.DoubleAttribute/"
        f"Value le {MAX_CLOUD}"
        ")"
    )


    # --------------------------------------------------------
    # Collection
    # --------------------------------------------------------

    collection_filter = (
        "Collection/Name eq 'SENTINEL-2'"
    )


    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    date_filter = (
        "ContentDate/Start gt "
        f"{start_iso}"
        " and "
        "ContentDate/Start lt "
        f"{end_iso}"
    )


    # --------------------------------------------------------
    # Final filter
    # --------------------------------------------------------

    query_filter = (
        collection_filter
        + " and "
        + spatial_filter
        + " and "
        + product_type_filter
        + " and "
        + cloud_filter
        + " and "
        + date_filter
    )


    params = {

        "$filter":
            query_filter,

        "$orderby":
            "ContentDate/Start desc",

        "$top":
            "50",

        "$select":
            "Id,Name,S3Path,ContentDate,GeoFootprint"

    }


    print("")
    print(
        "در حال جستجوی Sentinel-2 ..."
    )

    print(
        f"بازه: "
        f"{start_date.strftime('%Y-%m-%d')}"
        " تا "
        f"{end_date.strftime('%Y-%m-%d')}"
    )


    response = requests.get(

        CATALOGUE_URL,

        params=params,

        timeout=90
    )


    if response.status_code != 200:

        raise RuntimeError(
            "خطا در جستجوی Sentinel-2:\n"
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )


    result = response.json()

    return result.get(
        "value",
        []
    )


# ============================================================
# 3-DAY WINDOW
# ============================================================

three_day_start = (
    fire_date
    - timedelta(days=3)
)


three_day_end = (
    fire_date
    + timedelta(days=1)
)


print("")
print(
    "=========================================="
)

print(
    "بازه ۳ روزه"
)

print(
    f"{three_day_start.strftime('%Y-%m-%d')}"
    " تا "
    f"{fire_date.strftime('%Y-%m-%d')}"
)


three_day_products = search_sentinel2(
    three_day_start,
    three_day_end
)


print(
    f"تعداد تصاویر: "
    f"{len(three_day_products)}"
)


# ============================================================
# 5-DAY WINDOW
# ============================================================

five_day_start = (
    fire_date
    - timedelta(days=5)
)


five_day_end = (
    fire_date
    + timedelta(days=1)
)


print("")
print(
    "=========================================="
)

print(
    "بازه ۵ روزه"
)

print(
    f"{five_day_start.strftime('%Y-%m-%d')}"
    " تا "
    f"{fire_date.strftime('%Y-%m-%d')}"
)


five_day_products = search_sentinel2(
    five_day_start,
    five_day_end
)


print(
    f"تعداد تصاویر: "
    f"{len(five_day_products)}"
)


# ============================================================
# REMOVE DUPLICATES
# ============================================================

all_products = []

seen = set()


for product in (
    three_day_products
    + five_day_products
):

    product_id = product.get(
        "Id"
    )

    if not product_id:
        continue

    if product_id in seen:
        continue

    seen.add(
        product_id
    )

    all_products.append(
        product
    )


# ============================================================
# SORT BY DATE
# ============================================================

def get_start_date(product):

    content_date = product.get(
        "ContentDate",
        {}
    )

    return content_date.get(
        "Start",
        ""
    )


all_products.sort(
    key=get_start_date,
    reverse=True
)


# ============================================================
# PRINT RESULTS
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "تصاویر واقعی مرتبط با نقطه حریق"
)

print(
    "=========================================="
)


for index, product in enumerate(
    all_products,
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
        f"Start: "
        f"{get_start_date(product)}"
    )

    print(
        f"ID: "
        f"{product.get('Id', '-')}"
    )

    print(
        f"S3Path: "
        f"{product.get('S3Path', '-')}"
    )


# ============================================================
# SAVE RESULT
# ============================================================

result = {

    "fire": {

        "date":
            fire_date_text,

        "latitude":
            fire_lat,

        "longitude":
            fire_lon

    },

    "search_point": {

        "latitude":
            fire_lat,

        "longitude":
            fire_lon

    },

    "criteria": {

        "max_cloud_percent":
            MAX_CLOUD,

        "product_type":
            "S2MSI2A",

        "spatial_filter":
            "POINT",

        "spatial_crs":
            "EPSG:4326"

    },

    "windows": {

        "three_day": {

            "start":
                three_day_start.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                fire_date.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                len(three_day_products)

        },

        "five_day": {

            "start":
                five_day_start.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                fire_date.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                len(five_day_products)

        }

    },

    "products":
        all_products
}


with open(
    "sentinel2_search.json",
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
    "نتیجه ذخیره شد:"
)

print(
    "sentinel2_search.json"
)

print(
    "=========================================="
)
