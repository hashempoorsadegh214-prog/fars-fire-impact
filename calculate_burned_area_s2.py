import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import requests
from rasterio.io import MemoryFile


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"
SEARCH_FILE = "sentinel2_search.json"

RESULT_FILE = "burned_area_result.json"
RASTER_FILE = "burned_area_mask.tif"
GEOJSON_FILE = "burned_area.geojson"

CLIENT_ID = os.environ.get(
    "CDSE_CLIENT_ID"
)

CLIENT_SECRET = os.environ.get(
    "CDSE_CLIENT_SECRET"
)

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = (
    "https://sh.dataspace.copernicus.eu/"
    "process/v1"
)

# محدوده اولیه بررسی اطراف مرکز حریق
AOI_RADIUS_KM = 5

# تفکیک خروجی
# B8A و B12 هر دو در 20 متر استفاده می‌شوند
RESOLUTION_M = 20

# آستانه اولیه dNBR
BURN_THRESHOLD = 0.27


# ============================================================
# HELPER
# ============================================================

def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# LOAD FIRE DATA
# ============================================================

with open(
    FIRES_FILE,
    "r",
    encoding="utf-8"
) as file:

    fires_data = json.load(file)


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
    "acq_date"
)

fire_lat = float(
    latest_fire["latitude"]
)

fire_lon = float(
    latest_fire["longitude"]
)


# ============================================================
# LOAD SENTINEL-2 SEARCH RESULT
# ============================================================

with open(
    SEARCH_FILE,
    "r",
    encoding="utf-8"
) as file:

    search_data = json.load(file)


before_data = search_data.get(
    "before",
    {}
)

after_data = search_data.get(
    "after",
    {}
)


before_tiles = before_data.get(
    "tiles",
    []
)

after_product = after_data.get(
    "selected"
)


# ============================================================
# WAITING FOR AFTER IMAGE
# ============================================================

if not before_tiles:

    result = {

        "status":
            "NO_BEFORE_IMAGE",

        "fire": {

            "date":
                fire_date,

            "latitude":
                fire_lat,

            "longitude":
                fire_lon

        }

    }

    save_json(
        RESULT_FILE,
        result
    )

    print(
        "تصویر قبل از حریق پیدا نشد."
    )

    raise SystemExit(0)


if not after_product:

    result = {

        "status":
            "WAITING_FOR_AFTER_IMAGE",

        "message":
            "تصویر Sentinel-2 بعد از حریق هنوز موجود نیست.",

        "fire": {

            "date":
                fire_date,

            "latitude":
                fire_lat,

            "longitude":
                fire_lon

        },

        "before": {

            "date":
                before_data.get(
                    "selected_acquisition"
                ),

            "tile_count":
                len(
                    before_tiles
                )

        },

        "after_search": {

            "start":
                (
                    datetime.strptime(
                        fire_date,
                        "%Y-%m-%d"
                    )
                    + timedelta(days=1)
                ).strftime(
                    "%Y-%m-%d"
                ),

            "end":
                (
                    datetime.strptime(
                        fire_date,
                        "%Y-%m-%d"
                    )
                    + timedelta(days=5)
                ).strftime(
                    "%Y-%m-%d"
                )

        }

    }

    save_json(
        RESULT_FILE,
        result
    )

    print("")
    print(
        "=========================================="
    )

    print(
        "تصویر قبل موجود است."
    )

    print(
        f"تعداد Tile قبل: {len(before_tiles)}"
    )

    print(
        "تصویر بعد هنوز موجود نیست."
    )

    print(
        "وضعیت: WAITING_FOR_AFTER_IMAGE"
    )

    print(
        "=========================================="
    )

    raise SystemExit(0)


# ============================================================
# CHECK CREDENTIALS
# ============================================================

if not CLIENT_ID:

    raise RuntimeError(
        "CDSE_CLIENT_ID تنظیم نشده است."
    )


if not CLIENT_SECRET:

    raise RuntimeError(
        "CDSE_CLIENT_SECRET تنظیم نشده است."
    )


# ============================================================
# GET TOKEN
# ============================================================

print("")
print(
    "دریافت توکن Copernicus..."
)


token_response = requests.post(

    TOKEN_URL,

    data={

        "grant_type":
            "client_credentials",

        "client_id":
            CLIENT_ID,

        "client_secret":
            CLIENT_SECRET

    },

    timeout=60

)


if token_response.status_code != 200:

    raise RuntimeError(
        "خطا در دریافت توکن Copernicus:\n"
        f"HTTP {token_response.status_code}\n"
        f"{token_response.text}"
    )


access_token = token_response.json().get(
    "access_token"
)


if not access_token:

    raise RuntimeError(
        "access_token دریافت نشد."
    )


# ============================================================
# AOI
# ============================================================

lat_delta = (
    AOI_RADIUS_KM / 111.0
)

lon_delta = (
    AOI_RADIUS_KM
    /
    (
        111.0
        *
        np.cos(
            np.radians(
                fire_lat
            )
        )
    )
)


min_lon = fire_lon - lon_delta
max_lon = fire_lon + lon_delta

min_lat = fire_lat - lat_delta
max_lat = fire_lat + lat_delta


bbox = [
    min_lon,
    min_lat,
    max_lon,
    max_lat
]


# ============================================================
# OUTPUT SIZE
# ============================================================

width = max(
    1,
    int(
        (
            (max_lon - min_lon)
            * 111000
            * np.cos(
                np.radians(
                    fire_lat
                )
            )
        )
        / RESOLUTION_M
    )
)

height = max(
    1,
    int(
        (
            (max_lat - min_lat)
            * 111000
        )
        / RESOLUTION_M
    )
)


print("")
print(
    f"AOI: {AOI_RADIUS_KM} km"
)

print(
    f"اندازه خروجی: "
    f"{width} × {height}"
)


# ============================================================
# GET DATE FROM PRODUCTS
# ============================================================

before_start = (
    before_data.get(
        "selected_acquisition"
    )
)


if not before_start:

    raise RuntimeError(
        "تاریخ تصویر قبل مشخص نیست."
    )


before_date = (
    before_start[:10]
)


after_start = (
    after_product
    .get(
        "ContentDate",
        {}
    )
    .get(
        "Start",
        ""
    )
)


if not after_start:

    raise RuntimeError(
        "تاریخ تصویر بعد مشخص نیست."
    )


after_date = (
    after_start[:10]
)


# ============================================================
# EVALSCRIPT
# ============================================================

EVALSCRIPT = """
//VERSION=3

function setup() {

    return {

        input: [{
            bands: [
                "B8A",
                "B12"
            ],

            units: "REFLECTANCE"
        }],

        output: {

            bands: 1,

            sampleType: "FLOAT32"

        },

        mosaicking: "SIMPLE"

    };

}


function evaluatePixel(sample) {

    let denominator =
        sample.B8A +
        sample.B12;

    if (denominator === 0) {

        return [-9999];

    }

    let nbr =
        (
            sample.B8A -
            sample.B12
        )
        /
        denominator;

    return [nbr];

}
"""


# ============================================================
# PROCESS REQUEST
# ============================================================

def get_nbr(date_string):

    next_day = (
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )
        + timedelta(days=1)
    ).strftime(
        "%Y-%m-%d"
    )


    request_body = {

        "input": {

            "bounds": {

                "bbox":
                    bbox,

                "properties": {

                    "crs":
                        "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

                }

            },

            "data": [

                {

                    "type":
                        "S2L2A",

                    "dataFilter": {

                        "timeRange": {

                            "from":
                                f"{date_string}T00:00:00Z",

                            "to":
                                f"{next_day}T00:00:00Z"

                        },

                        "mosaickingOrder":
                            "leastCC"

                    }

                }

            ]

        },

        "output": {

            "width":
                width,

            "height":
                height,

            "responses": [

                {

                    "identifier":
                        "default",

                    "format": {

                        "type":
                            "image/tiff"

                    }

                }

            ]

        },

        "evalscript":
            EVALSCRIPT

    }


    response = requests.post(

        PROCESS_URL,

        headers={

            "Authorization":
                f"Bearer {access_token}",

            "Content-Type":
                "application/json"

        },

        json=request_body,

        timeout=180

    )


    if response.status_code != 200:

        raise RuntimeError(
            "خطا در Process API:\n"
            f"HTTP {response.status_code}\n"
            f"{response.text}"
        )


    with MemoryFile(
        response.content
    ) as memfile:

        with memfile.open() as src:

            array = src.read(1)

            transform = src.transform

            crs = src.crs

            raster_width = src.width
            raster_height = src.height


    return (
        array,
        transform,
        crs,
        raster_width,
        raster_height
    )


# ============================================================
# GET BEFORE / AFTER NBR
# ============================================================

print("")
print(
    f"NBR قبل: {before_date}"
)


nbr_before, transform, crs, raster_width, raster_height = (
    get_nbr(
        before_date
    )
)


print(
    f"NBR بعد: {after_date}"
)


nbr_after, _, _, _, _ = (
    get_nbr(
        after_date
    )
)


# ============================================================
# VALID PIXELS
# ============================================================

valid = (

    np.isfinite(
        nbr_before
    )

    &

    np.isfinite(
        nbr_after
    )

    &

    (nbr_before > -1)

    &

    (nbr_before < 1)

    &

    (nbr_after > -1)

    &

    (nbr_after < 1)

)


# ============================================================
# dNBR
# ============================================================

dnbr = (
    nbr_before
    -
    nbr_after
)


burned_mask = (
    valid
    &
    (dnbr >= BURN_THRESHOLD)
)


# ============================================================
# AREA
# ============================================================

pixel_area_m2 = (
    RESOLUTION_M
    *
    RESOLUTION_M
)


pixel_area_ha = (
    pixel_area_m2
    /
    10000.0
)


burned_pixels = int(
    burned_mask.sum()
)


burned_area_ha = (
    burned_pixels
    *
    pixel_area_ha
)


# ============================================================
# SAVE BURN MASK RASTER
# ============================================================

import rasterio


with rasterio.open(

    RASTER_FILE,

    "w",

    driver="GTiff",

    height=raster_height,

    width=raster_width,

    count=1,

    dtype="uint8",

    crs=crs,

    transform=transform,

    nodata=0

) as dst:

    dst.write(
        burned_mask.astype(
            "uint8"
        ),
        1
    )


# ============================================================
# SAVE RESULT
# ============================================================

result = {

    "status":
        "SUCCESS",

    "fire": {

        "date":
            fire_date,

        "latitude":
            fire_lat,

        "longitude":
            fire_lon

    },

    "sentinel2": {

        "before_date":
            before_date,

        "after_date":
            after_date,

        "before_tile_count":
            len(before_tiles),

        "after_product":
            after_product.get(
                "Name",
                ""
            )

    },

    "method": {

        "index":
            "NBR",

        "difference":
            "dNBR = NBR_before - NBR_after",

        "threshold":
            BURN_THRESHOLD,

        "resolution_m":
            RESOLUTION_M

    },

    "burned_area": {

        "pixels":
            burned_pixels,

        "pixel_area_ha":
            pixel_area_ha,

        "hectares":
            round(
                burned_area_ha,
                3
            )

    },

    "files": {

        "mask":
            RASTER_FILE,

        "geojson":
            GEOJSON_FILE

    }

}


save_json(
    RESULT_FILE,
    result
)


# ============================================================
# PRINT RESULT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "نتیجه محاسبه سوختگی"
)

print(
    f"پیکسل سوخته: "
    f"{burned_pixels}"
)

print(
    f"مساحت سوخته: "
    f"{burned_area_ha:.3f} هکتار"
)

print(
    f"آستانه dNBR: "
    f"{BURN_THRESHOLD}"
)

print(
    "=========================================="
)
