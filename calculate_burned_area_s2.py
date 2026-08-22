import json
import os
from datetime import datetime, timedelta

import numpy as np
import rasterio
import requests
from rasterio.io import MemoryFile


# ============================================================
# SETTINGS
# ============================================================

SELECTED_FIRE_FILE = (
    "selected_protected_fire_2026.json"
)

RESULT_FILE = (
    "burned_area_result.json"
)

RASTER_FILE = (
    "burned_area_mask.tif"
)

CLIENT_ID = os.environ.get(
    "CDSE_CLIENT_ID"
)

CLIENT_SECRET = os.environ.get(
    "CDSE_CLIENT_SECRET"
)

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/"
    "protocol/openid-connect/token"
)

PROCESS_URL = (
    "https://sh.dataspace.copernicus.eu/"
    "process/v1"
)

# شعاع محدوده محاسبه اطراف نقطه حریق
AOI_RADIUS_KM = 5

# تفکیک مکانی خروجی
RESOLUTION_M = 20

# آستانه اولیه dNBR
BURN_THRESHOLD = 0.27


# ============================================================
# LOAD SELECTED FIRE
# ============================================================

with open(
    SELECTED_FIRE_FILE,
    "r",
    encoding="utf-8"
) as file:

    selected_data = json.load(
        file
    )


fire = selected_data.get(
    "fire"
)

before_data = selected_data.get(
    "before"
)

after_data = selected_data.get(
    "after"
)


if not fire:
    raise RuntimeError(
        "fire در selected_protected_fire_2026.json پیدا نشد."
    )


if not before_data:
    raise RuntimeError(
        "تصویر قبل پیدا نشد."
    )


if not after_data:
    raise RuntimeError(
        "تصویر بعد پیدا نشد."
    )


# ============================================================
# FIRE INFORMATION
# ============================================================

fire_date = fire.get(
    "acq_date"
)

fire_time = fire.get(
    "acq_time",
    ""
)

fire_lat = float(
    fire["latitude"]
)

fire_lon = float(
    fire["longitude"]
)

before_date = before_data.get(
    "date"
)

after_date = after_data.get(
    "date"
)

inside_protected = selected_data.get(
    "inside_protected_areas",
    False
)

inside_hunting = selected_data.get(
    "inside_hunting_banned",
    False
)


print("")
print(
    "=========================================="
)

print(
    "حریق حفاظتی انتخاب‌شده"
)

print(
    f"تاریخ حریق: {fire_date}"
)

print(
    f"زمان حریق: {fire_time}"
)

print(
    f"Latitude: {fire_lat}"
)

print(
    f"Longitude: {fire_lon}"
)

print(
    f"داخل مناطق چهارگانه: "
    f"{inside_protected}"
)

print(
    f"داخل شکار ممنوع: "
    f"{inside_hunting}"
)

print(
    f"تصویر قبل: {before_date}"
)

print(
    f"Tile قبل: "
    f"{before_data.get('tile_count', 0)}"
)

print(
    f"تصویر بعد: {after_date}"
)

print(
    f"Tile بعد: "
    f"{after_data.get('tile_count', 0)}"
)

print(
    "=========================================="
)


# ============================================================
# CHECK CREDENTIALS
# ============================================================

if not CLIENT_ID:

    raise RuntimeError(
        "CDSE_CLIENT_ID در GitHub Secrets تنظیم نشده است."
    )


if not CLIENT_SECRET:

    raise RuntimeError(
        "CDSE_CLIENT_SECRET در GitHub Secrets تنظیم نشده است."
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
# BUILD AOI
# ============================================================

lat_delta = (
    AOI_RADIUS_KM / 111.0
)

cos_lat = np.cos(
    np.radians(
        fire_lat
    )
)

if abs(cos_lat) < 0.01:

    raise RuntimeError(
        "محاسبه طول جغرافیایی AOI نامعتبر است."
    )


lon_delta = (
    AOI_RADIUS_KM
    /
    (
        111.0
        *
        cos_lat
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
            (
                max_lon
                - min_lon
            )
            *
            111000
            *
            cos_lat
        )
        /
        RESOLUTION_M
    )
)

height = max(
    1,
    int(
        (
            (
                max_lat
                - min_lat
            )
            *
            111000
        )
        /
        RESOLUTION_M
    )
)


print("")
print(
    f"AOI radius: "
    f"{AOI_RADIUS_KM} km"
)

print(
    f"Output size: "
    f"{width} x {height}"
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

        }

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
# GET NBR
# ============================================================

def get_nbr(
    date_string
):

    next_date = (
        datetime.strptime(
            date_string,
            "%Y-%m-%d"
        )
        + timedelta(
            days=1
        )
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
                        "http://www.opengis.net/"
                        "def/crs/OGC/1.3/CRS84"

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
                                f"{next_date}T00:00:00Z"

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
            "خطا در Sentinel Hub Process API:\n"
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
# BEFORE NBR
# ============================================================

print("")
print(
    f"در حال دریافت NBR قبل: "
    f"{before_date}"
)


(
    nbr_before,
    transform,
    crs,
    raster_width,
    raster_height
) = get_nbr(
    before_date
)


print(
    "NBR قبل دریافت شد."
)


# ============================================================
# AFTER NBR
# ============================================================

print("")
print(
    f"در حال دریافت NBR بعد: "
    f"{after_date}"
)


(
    nbr_after,
    _,
    _,
    _,
    _
) = get_nbr(
    after_date
)


print(
    "NBR بعد دریافت شد."
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


# ============================================================
# BURN MASK
# ============================================================

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
# SAVE BURN MASK
# ============================================================

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
# RESULT
# ============================================================

result = {

    "status":
        "SUCCESS",

    "fire": {

        "date":
            fire_date,

        "time":
            fire_time,

        "latitude":
            fire_lat,

        "longitude":
            fire_lon,

        "inside_protected_areas":
            inside_protected,

        "inside_hunting_banned":
            inside_hunting

    },

    "sentinel2": {

        "before_date":
            before_date,

        "after_date":
            after_date,

        "before_tile_count":
            before_data.get(
                "tile_count",
                0
            ),

        "after_tile_count":
            after_data.get(
                "tile_count",
                0
            )

    },

    "method": {

        "index":
            "NBR",

        "formula":
            "NBR = (B8A - B12) / (B8A + B12)",

        "difference":
            "dNBR = NBR_before - NBR_after",

        "threshold":
            BURN_THRESHOLD,

        "resolution_m":
            RESOLUTION_M,

        "aoi_radius_km":
            AOI_RADIUS_KM

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

    }

}


# ============================================================
# SAVE RESULT
# ============================================================

with open(
    RESULT_FILE,
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
# FINAL REPORT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "نتیجه محاسبه سوختگی حریق حفاظتی"
)

print(
    f"حریق: {fire_date}"
)

print(
    f"مختصات: "
    f"{fire_lat}, {fire_lon}"
)

print(
    f"داخل مناطق چهارگانه: "
    f"{inside_protected}"
)

print(
    f"داخل شکار ممنوع: "
    f"{inside_hunting}"
)

print(
    f"تصویر قبل: {before_date}"
)

print(
    f"تصویر بعد: {after_date}"
)

print(
    f"آستانه dNBR: "
    f"{BURN_THRESHOLD}"
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
    "=========================================="
)
