import json
import time
from datetime import datetime, timedelta

import requests


# ============================================================
# SETTINGS
# ============================================================

BOUNDARY_FILE = "fars.geojson"

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

END_DATE = datetime(
    2026,
    8,
    23
)

REQUEST_TIMEOUT = 120

RETRY_COUNT = 3

RETRY_DELAY = 5


# ============================================================
# LOAD FARS GEOJSON
# ============================================================

with open(
    BOUNDARY_FILE,
    "r",
    encoding="utf-8"
) as file:

    fars = json.load(file)


# ============================================================
# EXTRACT GEOMETRY
# ============================================================

def get_geometry(geojson):

    if geojson.get("type") == "FeatureCollection":

        features = geojson.get(
            "features",
            []
        )

        if not features:

            raise RuntimeError(
                "فایل fars.geojson فاقد Feature است."
            )

        return features[0]["geometry"]


    if geojson.get("type") == "Feature":

        return geojson["geometry"]


    if geojson.get("type") in [
        "Polygon",
        "MultiPolygon"
    ]:

        return geojson


    raise RuntimeError(
        "ساختار fars.geojson قابل شناسایی نیست."
    )


fars_geometry = get_geometry(
    fars
)


# ============================================================
# CREATE WKT
# ============================================================

def geometry_to_wkt(
    geometry
):

    geometry_type = geometry["type"]

    coordinates = geometry["coordinates"]


    # --------------------------------------------------------
    # Polygon
    # --------------------------------------------------------

    if geometry_type == "Polygon":

        rings = []

        for ring in coordinates:

            points = []

            for lon, lat in ring:

                points.append(
                    f"{lon} {lat}"
                )

            rings.append(
                "("
                + ", ".join(points)
                + ")"
            )

        return (
            "POLYGON("
            + ", ".join(rings)
            + ")"
        )


    # --------------------------------------------------------
    # MultiPolygon
    # --------------------------------------------------------

    if geometry_type == "MultiPolygon":

        polygons = []

        for polygon in coordinates:

            rings = []

            for ring in polygon:

                points = []

                for lon, lat in ring:

                    points.append(
                        f"{lon} {lat}"
                    )

                rings.append(
                    "("
                    + ", ".join(points)
                    + ")"
                )

            polygons.append(
                "("
                + ", ".join(rings)
                + ")"
            )

        return (
            "MULTIPOLYGON("
            + ", ".join(polygons)
            + ")"
        )


    raise RuntimeError(
        f"Geometry type unsupported: "
        f"{geometry_type}"
    )


fars_wkt = geometry_to_wkt(
    fars_geometry
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
        f"{fars_wkt}"
        "')"
    )


    date_filter = (
        "ContentDate/Start gt "
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

def request_period(
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

        "$select":
            "Id,Name,S3Path,ContentDate,"
            "GeoFootprint",

        "$top":
            "100"

    }


    products = []

    next_url = None


    for attempt in range(
        1,
        RETRY_COUNT + 1
    ):

        try:

            response = requests.get(

                next_url
                if next_url
                else CATALOGUE_URL,

                params=None
                if next_url
                else params,

                timeout=REQUEST_TIMEOUT

            )


            if response.status_code != 200:

                raise RuntimeError(
                    f"HTTP {response.status_code}: "
                    f"{response.text}"
                )


            data = response.json()


            products.extend(
                data.get(
                    "value",
                    []
                )
            )


            next_url = data.get(
                "@odata.nextLink"
            )


            while next_url:

                page_response = requests.get(
                    next_url,
                    timeout=REQUEST_TIMEOUT
                )


                if page_response.status_code != 200:

                    raise RuntimeError(
                        f"Pagination HTTP "
                        f"{page_response.status_code}"
                    )


                page_data = (
                    page_response.json()
                )


                products.extend(
                    page_data.get(
                        "value",
                        []
                    )
                )


                next_url = (
                    page_data.get(
                        "@odata.nextLink"
                    )
                )


            return products


        except Exception as error:

            print(
                f"خطا در جستجوی "
                f"{start_date.strftime('%Y-%m-%d')} "
                f"تا "
                f"{end_date.strftime('%Y-%m-%d')}: "
                f"{error}"
            )


            if attempt < RETRY_COUNT:

                time.sleep(
                    RETRY_DELAY
                )

            else:

                return []


# ============================================================
# MONTH WINDOWS
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
# ARCHIVE
# ============================================================

all_products = []

seen_ids = set()


print("")
print(
    "=========================================="
)

print(
    "شروع آرشیو Sentinel-2 سال 2026"
)

print(
    f"ابر حداکثر: {MAX_CLOUD}%"
)

print(
    f"تعداد بازه‌ها: {len(periods)}"
)

print(
    "=========================================="
)


for start_date, end_date in periods:

    print("")
    print(
        f"جستجو: "
        f"{start_date.strftime('%Y-%m-%d')}"
        " → "
        f"{end_date.strftime('%Y-%m-%d')}"
    )


    products = request_period(
        start_date,
        end_date
    )


    print(
        f"تعداد محصولات این بازه: "
        f"{len(products)}"
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


# ============================================================
# SORT
# ============================================================

all_products.sort(

    key=lambda item:
        item.get(
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

    start = (
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


    if not start:
        continue


    acquisitions.setdefault(
        start,
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

        if "_T" in name:

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
                    - timedelta(
                        days=1
                    )
                ).strftime(
                    "%Y-%m-%d"
                )

        },

    "area":
        "Fars Province",

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
    f"تعداد محصولات: "
    f"{len(all_products)}"
)

print(
    f"تعداد برداشت‌های زمانی: "
    f"{len(acquisition_list)}"
)

print(
    f"فایل: {OUTPUT_FILE}"
)

print(
    "=========================================="
)
