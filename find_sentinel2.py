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

MAX_CLOUD = 30.0
AFTER_DAYS = 5


# ============================================================
# LOAD LATEST FIRE
# ============================================================

with open(
    FIRES_FILE,
    "r",
    encoding="utf-8"
) as file:
    data = json.load(file)


fires = data.get("fires", [])

if not fires:
    raise RuntimeError(
        "هیچ حریقی در fires.json پیدا نشد."
    )


latest_fire = fires[0]

fire_date_text = latest_fire.get("acq_date")
fire_lat = float(latest_fire["latitude"])
fire_lon = float(latest_fire["longitude"])


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
print("==========================================")
print("آخرین حریق")
print(f"تاریخ: {fire_date_text}")
print(f"عرض: {fire_lat}")
print(f"طول: {fire_lon}")
print("==========================================")


# ============================================================
# SEARCH SENTINEL-2
# ============================================================

def search_sentinel2(start_date, end_date):

    start_iso = start_date.strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )

    end_iso = end_date.strftime(
        "%Y-%m-%dT00:00:00.000Z"
    )

    point_wkt = (
        f"POINT({fire_lon} {fire_lat})"
    )

    spatial_filter = (
        "OData.CSC.Intersects("
        "area=geography'SRID=4326;"
        f"{point_wkt}"
        "')"
    )

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

    collection_filter = (
        "Collection/Name eq 'SENTINEL-2'"
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
        + spatial_filter
        + " and "
        + product_type_filter
        + " and "
        + cloud_filter
        + " and "
        + date_filter
    )

    params = {
        "$filter": query_filter,
        "$orderby": "ContentDate/Start desc",
        "$top": "50",
        "$select":
            "Id,Name,S3Path,ContentDate,GeoFootprint"
    }

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

    return response.json().get(
        "value",
        []
    )


# ============================================================
# SEARCH WINDOWS
# ============================================================

before_3_start = (
    fire_date - timedelta(days=3)
)

before_3_end = (
    fire_date + timedelta(days=1)
)

before_5_start = (
    fire_date - timedelta(days=5)
)

before_5_end = (
    fire_date + timedelta(days=1)
)

after_start = (
    fire_date + timedelta(days=1)
)

after_end = (
    fire_date + timedelta(days=AFTER_DAYS + 1)
)


before_3_products = search_sentinel2(
    before_3_start,
    before_3_end
)

before_5_products = search_sentinel2(
    before_5_start,
    before_5_end
)

after_products = search_sentinel2(
    after_start,
    after_end
)


# ============================================================
# UNIQUE PRODUCTS
# ============================================================

def unique_products(products):

    result = []
    seen = set()

    for product in products:

        product_id = product.get("Id")

        if not product_id:
            continue

        if product_id in seen:
            continue

        seen.add(product_id)
        result.append(product)

    return result


before_products = unique_products(
    before_3_products + before_5_products
)

after_products = unique_products(
    after_products
)


# ============================================================
# GET DATE
# ============================================================

def get_start_date(product):

    return product.get(
        "ContentDate",
        {}
    ).get(
        "Start",
        ""
    )


# ============================================================
# GROUP BEFORE PRODUCTS BY ACQUISITION TIME
# ============================================================

before_groups = {}

for product in before_products:

    start = get_start_date(product)

    if not start:
        continue

    date_key = start[:19]

    before_groups.setdefault(
        date_key,
        []
    ).append(product)


# ============================================================
# CHOOSE BEST BEFORE ACQUISITION
# ============================================================

sorted_before_times = sorted(
    before_groups.keys(),
    reverse=True
)


selected_before_time = None

selected_before_tiles = []


if sorted_before_times:

    selected_before_time = (
        sorted_before_times[0]
    )

    selected_before_tiles = (
        before_groups[
            selected_before_time
        ]
    )


# ============================================================
# CHOOSE BEST AFTER PRODUCT
# ============================================================

after_products.sort(
    key=get_start_date
)

selected_after = (
    after_products[0]
    if after_products
    else None
)


# ============================================================
# PRINT RESULTS
# ============================================================

print("")
print("==========================================")
print("تصویر قبل از حریق")
print("==========================================")

if selected_before_tiles:

    print(
        f"زمان برداشت: "
        f"{selected_before_time}"
    )

    print(
        f"تعداد Tile: "
        f"{len(selected_before_tiles)}"
    )

    for tile in selected_before_tiles:

        print(
            f"- {tile.get('Name', '-')}"
        )

else:

    print(
        "تصویر قبل پیدا نشد."
    )


print("")
print("==========================================")
print("تصویر بعد از حریق")
print("==========================================")

if selected_after:

    print(
        selected_after.get(
            "Name",
            "-"
        )
    )

else:

    print(
        "هنوز تصویر بعد از حریق موجود نیست."
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

        "before_3_day": {

            "start":
                before_3_start.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                fire_date.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                len(before_3_products)
        },

        "before_5_day": {

            "start":
                before_5_start.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                fire_date.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                len(before_5_products)
        },

        "after_5_day": {

            "start":
                after_start.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                after_end.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                len(after_products)
        }
    },

    "before": {

        "selected_acquisition":
            selected_before_time,

        "tile_count":
            len(selected_before_tiles),

        "tiles":
            selected_before_tiles
    },

    "after": {

        "selected":
            selected_after
    }
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
    "نتیجه در sentinel2_search.json ذخیره شد."
)
