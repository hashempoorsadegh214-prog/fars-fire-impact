import json
import time
from datetime import datetime, timedelta

import requests


# ============================================================
# SETTINGS
# ============================================================

OUTPUT_FILE = "sentinel2_archive_2026.json"

CATALOGUE_URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)

MAX_CLOUD = 30.0

START_DATE = datetime(
    2026,
    1,
    1
)

# پایان انحصاری
# یعنی داده‌ها تا پایان 22 اوت 2026 بررسی می‌شوند.
END_DATE = datetime(
    2026,
    8,
    23
)

REQUEST_TIMEOUT = 120

RETRY_COUNT = 3

RETRY_DELAY = 5


# ============================================================
# FARS BOUNDING BOX
# ============================================================

WEST = 50.0
SOUTH = 27.0
EAST = 54.5
NORTH = 31.5


# ============================================================
# FARS POLYGON
# ============================================================

bbox_wkt = (
    "POLYGON(("
    f"{WEST} {SOUTH},"
    f"{EAST} {SOUTH},"
    f"{EAST} {NORTH},"
    f"{WEST} {NORTH},"
    f"{WEST} {SOUTH}"
    "))"
)


# ============================================================
# BUILD FILTER
# ============================================================

def build_filter(
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

    spatial_filter = (
        "OData.CSC.Intersects("
        "area=geography'SRID=4326;"
        f"{bbox_wkt}"
        "')"
    )

    date_filter = (
        "ContentDate/Start ge "
        f"{start_iso}"
        " and "
        "ContentDate/Start lt "
        f"{end_iso}"
    )

    return (
        collection_filter
        + " and "
        + product_filter
        + " and "
        + cloud_filter
        + " and "
        + spatial_filter
        + " and "
        + date_filter
    )


# ============================================================
# REQUEST ONE PERIOD
# ============================================================

def get_period_products(
    start_date,
    end_date
):

    query_filter = build_filter(
        start_date,
        end_date
    )

    params = {

        "$filter":
            query_filter,

        "$orderby":
            "ContentDate/Start asc",

        "$top":
            "100",

        "$select":
            "Id,Name,S3Path,ContentDate,GeoFootprint"
    }

    products = []

    next_url = CATALOGUE_URL
    next_params = params

    page = 0


    while next_url:

        page += 1

        print("")
        print(
            f"صفحه {page}"
        )


        response = None


        for attempt in range(
            1,
            RETRY_COUNT + 1
        ):

            try:

                response = requests.get(

                    next_url,

                    params=next_params,

                    timeout=REQUEST_TIMEOUT
                )


                if response.status_code == 200:

                    break


                print(
                    f"HTTP {response.status_code} "
                    f"| تلاش {attempt}/{RETRY_COUNT}"
                )


                if attempt < RETRY_COUNT:

                    time.sleep(
                        RETRY_DELAY
                    )


            except requests.RequestException as error:

                print(
                    f"خطای اتصال: {error}"
                )


                if attempt < RETRY_COUNT:

                    time.sleep(
                        RETRY_DELAY
                    )


        if response is None:

            print(
                "پاسخ از Copernicus دریافت نشد."
            )

            break


        if response.status_code != 200:

            print(
                response.text
            )

            break


        data = response.json()


        values = data.get(
            "value",
            []
        )


        print(
            f"تصاویر این صفحه: "
            f"{len(values)}"
        )


        products.extend(
            values
        )


        next_url = data.get(
            "@odata.nextLink"
        )

        next_params = None


        print(
            f"مجموع این بازه: "
            f"{len(products)}"
        )


    return products


# ============================================================
# BUILD MONTHLY PERIODS
# ============================================================

periods = []

current = START_DATE


while current < END_DATE:

    if current.month == 12:

        next_month = datetime(
            current.year + 1,
            1,
            1
        )

    else:

        next_month = datetime(
            current.year,
            current.month + 1,
            1
        )


    period_end = min(
        next_month,
        END_DATE
    )


    periods.append(
        (
            current,
            period_end
        )
    )


    current = period_end


# ============================================================
# START
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "شروع آرشیو Sentinel-2 سال 2026"
)

print(
    f"بازه: "
    f"{START_DATE.strftime('%Y-%m-%d')}"
    " تا "
    f"{(END_DATE - timedelta(days=1)).strftime('%Y-%m-%d')}"
)

print(
    f"حداکثر ابر: {MAX_CLOUD}%"
)

print(
    "محدوده: Fars Province"
)

print(
    f"تعداد بازه‌های ماهانه: {len(periods)}"
)

print(
    "=========================================="
)


# ============================================================
# COLLECT PRODUCTS
# ============================================================

all_products = []

seen_ids = set()


for start_date, end_date in periods:

    print("")
    print(
        "=========================================="
    )

    print(
        f"بازه: "
        f"{start_date.strftime('%Y-%m-%d')}"
        " تا "
        f"{(end_date - timedelta(days=1)).strftime('%Y-%m-%d')}"
    )

    print(
        "=========================================="
    )


    products = get_period_products(
        start_date,
        end_date
    )


    for product in products:

        product_id = product.get(
            "Id"
        )


        if not product_id:

            continue


        if product_id in seen_ids:

            continue


        seen_ids.add(
            product_id
        )


        all_products.append(
            product
        )


    print(
        f"مجموع آرشیو تا اینجا: "
        f"{len(all_products)}"
    )


# ============================================================
# SORT
# ============================================================

all_products.sort(

    key=lambda product:
        product.get(
            "ContentDate",
            {}
        ).get(
            "Start",
            ""
        )

)


# ============================================================
# GROUP BY ACQUISITION
# ============================================================

acquisitions = {}


for product in all_products:

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


    if not acquisition:

        continue


    acquisitions.setdefault(
        acquisition,
        []
    ).append(
        product
    )


# ============================================================
# BUILD ACQUISITION SUMMARY
# ============================================================

acquisition_list = []


for acquisition_time in sorted(
    acquisitions.keys()
):

    products = acquisitions[
        acquisition_time
    ]


    tiles = []


    for product in products:

        name = product.get(
            "Name",
            ""
        )


        tile = ""


        marker = name.find(
            "_T"
        )


        if marker >= 0:

            tile = name[
                marker + 1:
                marker + 7
            ]


        tiles.append(
            {

                "id":
                    product.get(
                        "Id",
                        ""
                    ),

                "name":
                    name,

                "tile":
                    tile,

                "s3_path":
                    product.get(
                        "S3Path",
                        ""
                    )

            }
        )


    acquisition_list.append(
        {

            "acquisition":
                acquisition_time,

            "tile_count":
                len(tiles),

            "tiles":
                tiles

        }
    )


# ============================================================
# RESULT
# ============================================================

result = {

    "status":
        "SUCCESS",

    "dataset":
        "Sentinel-2 L2A",

    "product_type":
        "S2MSI2A",

    "period":
        {

            "start":
                START_DATE.strftime(
                    "%Y-%m-%d"
                ),

            "end":
                (
                    END_DATE
                    - timedelta(days=1)
                ).strftime(
                    "%Y-%m-%d"
                )

        },

    "area":
        {

            "name":
                "Fars Province",

            "bbox":
                [
                    WEST,
                    SOUTH,
                    EAST,
                    NORTH
                ]

        },

    "max_cloud_percent":
        MAX_CLOUD,

    "product_count":
        len(all_products),

    "acquisition_count":
        len(acquisition_list),

    "products":
        all_products,

    "acquisitions":
        acquisition_list

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
# FINAL
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "آرشیو Sentinel-2 تکمیل شد"
)

print(
    f"تعداد محصولات یکتا: "
    f"{len(all_products)}"
)

print(
    f"تعداد زمان‌های برداشت: "
    f"{len(acquisition_list)}"
)

print(
    f"فایل: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
