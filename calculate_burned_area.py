import json
import os
from datetime import datetime, timedelta
import requests
from pyproj import Transformer
import rasterio
from rasterio.io import MemoryFile


# ============================================================
# SETTINGS
# ============================================================

FIRES_FILE = "fires.json"

CLIENT_ID = os.environ.get("CDSE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("CDSE_CLIENT_SECRET")

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = (
    "https://sh.dataspace.copernicus.eu/"
    "api/v1/process"
)

COLLECTION_ID = (
    "byoc-162ee729-86a7-45bc-9cfe-c01f718e3216"
)

# شعاع بررسی اطراف آخرین حریق
RADIUS_METERS = 3000


# ============================================================
# CHECK SECRETS
# ============================================================

if not CLIENT_ID:
    raise RuntimeError(
        "CDSE_CLIENT_ID در GitHub Secrets پیدا نشد."
    )

if not CLIENT_SECRET:
    raise RuntimeError(
        "CDSE_CLIENT_SECRET در GitHub Secrets پیدا نشد."
    )


# ============================================================
# LOAD LATEST FIRE
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
        "هیچ حریقی در fires.json پیدا نشد."
    )


latest_fire = fires[0]


FIRE_LAT = float(
    latest_fire["latitude"]
)

FIRE_LON = float(
    latest_fire["longitude"]
)

FIRE_DATE = latest_fire.get(
    "acq_date",
    ""
)


if not FIRE_DATE:

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
    f"تاریخ: {FIRE_DATE}"
)

print(
    f"Latitude: {FIRE_LAT}"
)

print(
    f"Longitude: {FIRE_LON}"
)

print(
    "=========================================="
)


# ============================================================
# GET ACCESS TOKEN
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
        "خطا در دریافت توکن Copernicus: "
        f"{token_response.status_code}\n"
        f"{token_response.text}"
    )


access_token = token_response.json().get(
    "access_token"
)


if not access_token:

    raise RuntimeError(
        "access_token از Copernicus دریافت نشد."
    )


print(
    "توکن با موفقیت دریافت شد."
)


# ============================================================
# CONVERT WGS84 TO UTM ZONE 39N
# ============================================================

transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32639",
    always_xy=True
)


x,
y = transformer.transform(
    FIRE_LON,
    FIRE_LAT
)


# ============================================================
# BUILD BBOX
# ============================================================

min_x = x - RADIUS_METERS
max_x = x + RADIUS_METERS

min_y = y - RADIUS_METERS
max_y = y + RADIUS_METERS


width = int(
    (max_x - min_x) / 300
)

height = int(
    (max_y - min_y) / 300
)


print("")
print(
    f"اندازه پنجره: "
    f"{width} × {height} پیکسل"
)


# ============================================================
# DATE RANGE
# ============================================================

start_dt = datetime.strptime(
    FIRE_DATE,
    "%Y-%m-%d"
)

end_dt = start_dt + timedelta(
    days=1
)


start_iso = (
    start_dt.strftime(
        "%Y-%m-%dT00:00:00Z"
    )
)

end_iso = (
    end_dt.strftime(
        "%Y-%m-%dT00:00:00Z"
    )
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
        "BF",
        "CP",
        "DOB"
      ]
    }],

    output: {

      bands: 3,

      sampleType: "FLOAT32"

    }

  };

}


function evaluatePixel(sample) {

  return [
    sample.BF,
    sample.CP,
    sample.DOB
  ];

}
"""


# ============================================================
# PROCESS REQUEST
# ============================================================

request_body = {

    "input": {

        "bounds": {

            "bbox": [
                min_x,
                min_y,
                max_x,
                max_y
            ],

            "properties": {

                "crs": "http://www.opengis.net/def/crs/EPSG/0/32639"

            }

        },

        "data": [

            {

                "type":
                    COLLECTION_ID,

                "dataFilter": {

                    "timeRange": {

                        "from":
                            start_iso,

                        "to":
                            end_iso

                    }

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


print("")
print(
    "دریافت Burnt Area..."
)


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
        f"HTTP: {response.status_code}\n"
        f"{response.text}"
    )


print(
    "داده Burnt Area دریافت شد."
)


# ============================================================
# READ TIFF
# ============================================================

with MemoryFile(
    response.content
) as memfile:

    with memfile.open() as src:

        bf = src.read(1)
        cp = src.read(2)
        dob = src.read(3)


# ============================================================
# TARGET DAY OF YEAR
# ============================================================

target_date = datetime.strptime(
    FIRE_DATE,
    "%Y-%m-%d"
)

target_doy = (
    target_date.timetuple().tm_yday
)


# ============================================================
# CALCULATE BURNED AREA
# ============================================================

PIXEL_AREA_M2 = 300 * 300

PIXEL_AREA_HA = (
    PIXEL_AREA_M2 / 10000
)


burned_area_ha = 0.0

valid_pixels = 0

burn_pixels = 0


rows = bf.shape[0]
cols = bf.shape[1]


for row in range(rows):

    for col in range(cols):

        raw_bf = float(
            bf[row, col]
        )

        raw_cp = float(
            cp[row, col]
        )

        raw_dob = float(
            dob[row, col]
        )


        # ----------------------------------------------------
        # Scaling
        # ----------------------------------------------------

        BF = raw_bf / 1000.0

        CP = raw_cp / 1000.0

        DOB = raw_dob


        if BF < 0:
            continue

        if CP < 0:
            continue

        if DOB < 0:
            continue


        valid_pixels += 1


        # ----------------------------------------------------
        # فقط سوختگی همان روز
        # ----------------------------------------------------

        if int(round(DOB)) != target_doy:
            continue


        # ----------------------------------------------------
        # حداقل احتمال معتبر بودن سوختگی
        # ----------------------------------------------------

        if CP < 0.5:
            continue


        if BF <= 0:
            continue


        burn_pixels += 1


        burned_area_ha += (
            BF *
            PIXEL_AREA_HA
        )


# ============================================================
# RESULT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "نتیجه محاسبه"
)

print(
    f"پیکسل‌های معتبر: "
    f"{valid_pixels}"
)

print(
    f"پیکسل‌های دارای سوختگی: "
    f"{burn_pixels}"
)

print(
    f"مساحت سوخته: "
    f"{burned_area_ha:.3f} هکتار"
)

print(
    "=========================================="
)


# ============================================================
# SAVE RESULT
# ============================================================

result = {

    "status":
        "SUCCESS",

    "fire": {

        "date":
            FIRE_DATE,

        "latitude":
            FIRE_LAT,

        "longitude":
            FIRE_LON,

        "satellite":
            latest_fire.get(
                "satellite",
                ""
            )

    },

    "burned_area": {

        "hectares":
            round(
                burned_area_ha,
                3
            ),

        "pixel_resolution_m":
            300,

        "pixel_area_ha":
            PIXEL_AREA_HA,

        "valid_pixels":
            valid_pixels,

        "burned_pixels":
            burn_pixels,

        "cp_threshold":
            0.5,

        "search_radius_m":
            RADIUS_METERS

    },

    "product": {

        "name":
            "Copernicus Burnt Area 2025-present Daily V4",

        "collection_id":
            COLLECTION_ID

    }

}


with open(
    "burned_area_result.json",
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
    "فایل burned_area_result.json ساخته شد."
)
