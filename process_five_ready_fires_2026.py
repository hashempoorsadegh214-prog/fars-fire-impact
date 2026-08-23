import json
import os
from datetime import datetime, timedelta

import numpy as np
import requests
import rasterio
from rasterio.io import MemoryFile


# ============================================================
# SETTINGS
# ============================================================

INPUT_FILE = (
    "selected_five_ready_fires_2026.json"
)

OUTPUT_FILE = (
    "five_fires_burned_area_result.json"
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

AOI_RADIUS_KM = 5.0

RESOLUTION_M = 20

BURN_THRESHOLD = 0.27


# ============================================================
# LOAD SELECTED FIRES
# ============================================================

with open(
    INPUT_FILE,
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
        "selected_five_ready_fires_2026.json خالی است."
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
# BUILD AOI
# ============================================================

def build_aoi(
    lat,
    lon
):

    lat_delta = (
        AOI_RADIUS_KM / 111.0
    )


    cos_lat = np.cos(
        np.radians(
            lat
        )
    )


    if abs(cos_lat) < 0.01:

        raise RuntimeError(
            "خطا در محاسبه AOI."
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


    min_lon = lon - lon_delta
    max_lon = lon + lon_delta

    min_lat = lat - lat_delta
    max_lat = lat + lat_delta


    bbox = [

        min_lon,
        min_lat,
        max_lon,
        max_lat

    ]


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


    return (
        bbox,
        width,
        height
    )


# ============================================================
# GET NBR
# ============================================================

def get_nbr(
    date_string,
    bbox,
    width,
    height
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
            "خطا در دریافت Sentinel-2:\n"
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

            width_out = src.width

            height_out = src.height


    return (
        array,
        transform,
        crs,
        width_out,
        height_out
    )


# ============================================================
# PROCESS ONE FIRE
# ============================================================

def process_fire(
    item,
    index
):

    fire = item.get(
        "fire",
        {}
    )

    before = item.get(
        "before"
    )

    after = item.get(
        "after"
    )


    if not before or not after:

        raise RuntimeError(
            "تصویر قبل یا بعد موجود نیست."
        )


    fire_date = fire.get(
        "acq_date",
        ""
    )

    fire_time = fire.get(
        "acq_time",
        ""
    )

    latitude = float(
        fire["latitude"]
    )

    longitude = float(
        fire["longitude"]
    )


    before_date = before.get(
        "date"
    )

    after_date = after.get(
        "date"
    )


    print("")
    print(
        "=========================================="
    )

    print(
        f"حریق {index}/{len(fires)}"
    )

    print(
        f"تاریخ: {fire_date}"
    )

    print(
        f"زمان: {fire_time}"
    )

    print(
        f"مختصات: "
        f"{latitude}, {longitude}"
    )

    print(
        f"قبل: {before_date}"
    )

    print(
        f"بعد: {after_date}"
    )

    print(
        "=========================================="
    )


    bbox, width, height = build_aoi(
        latitude,
        longitude
    )


    print(
        f"AOI: {width} x {height}"
    )


    # --------------------------------------------------------
    # BEFORE
    # --------------------------------------------------------

    print(
        f"NBR قبل: {before_date}"
    )


    nbr_before, transform, crs, rw, rh = get_nbr(

        before_date,

        bbox,

        width,

        height

    )


    print(
        "NBR قبل دریافت شد."
    )


    # --------------------------------------------------------
    # AFTER
    # --------------------------------------------------------

    print(
        f"NBR بعد: {after_date}"
    )


    nbr_after, _, _, _, _ = get_nbr(

        after_date,

        bbox,

        width,

        height

    )


    print(
        "NBR بعد دریافت شد."
    )


    # --------------------------------------------------------
    # VALID PIXELS
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # dNBR
    # --------------------------------------------------------

    dnbr = (
        nbr_before
        -
        nbr_after
    )


    # --------------------------------------------------------
    # BURN MASK
    # --------------------------------------------------------

    burned_mask = (

        valid

        &

        (dnbr >= BURN_THRESHOLD)

    )


    # --------------------------------------------------------
    # AREA
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # SAVE MASK
    # --------------------------------------------------------

    mask_file = (
        f"burned_area_mask_fire_{index}.tif"
    )


    with rasterio.open(

        mask_file,

        "w",

        driver="GTiff",

        height=rh,

        width=rw,

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


    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    result = {

        "id":
            index,

        "fire": {

            "date":
                fire_date,

            "time":
                fire_time,

            "latitude":
                latitude,

            "longitude":
                longitude

        },

        "sentinel2": {

            "before_date":
                before_date,

            "after_date":
                after_date,

            "before_tile_count":
                before.get(
                    "tile_count",
                    0
                ),

            "after_tile_count":
                after.get(
                    "tile_count",
                    0
                )

        },

        "method": {

            "index":
                "NBR",

            "dNBR_threshold":
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

        },

        "mask":
            mask_file

    }


    print(
        f"پیکسل سوخته: "
        f"{burned_pixels}"
    )

    print(
        f"مساحت سوخته: "
        f"{burned_area_ha:.3f} هکتار"
    )


    return result


# ============================================================
# PROCESS FIVE FIRES
# ============================================================

results = []

failed = []


for index, item in enumerate(
    fires,
    start=1
):

    try:

        result = process_fire(
            item,
            index
        )

        results.append(
            result
        )


    except Exception as error:

        print("")
        print(
            f"خطا در حریق {index}: "
            f"{error}"
        )


        failed.append(
            {

                "id":
                    index,

                "error":
                    str(error)

            }
        )


# ============================================================
# SUMMARY
# ============================================================

result_file = {

    "status":
        "SUCCESS",

    "count":
        len(fires),

    "processed":
        len(results),

    "failed":
        failed,

    "results":
        results

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
        result_file,
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
    "پردازش ۵ حریق تمام شد"
)

print(
    f"تعداد ورودی: "
    f"{len(fires)}"
)

print(
    f"موفق: "
    f"{len(results)}"
)

print(
    f"ناموفق: "
    f"{len(failed)}"
)

print(
    f"خروجی: "
    f"{OUTPUT_FILE}"
)

print(
    "=========================================="
)

for result in results:

    print(
        f"#{result['id']} | "
        f"{result['fire']['date']} | "
        f"{result['burned_area']['hectares']:.3f} هکتار"
    )
