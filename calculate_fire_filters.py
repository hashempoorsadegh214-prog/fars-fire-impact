import json
import os

import geopandas as gpd
import rasterio
from rasterio.mask import mask
from shapely.geometry import shape


# ============================================================
# SETTINGS
# ============================================================

MASK_FILE = "burned_area_mask.tif"

FARS_FILE = "fars.geojson"
PROTECTED_FILE = "protected_areas.geojson"
HUNTING_FILE = "hunting_banned.geojson"

RESULT_FILE = "fire_filters_result.json"


# ============================================================
# CHECK BURN MASK
# ============================================================

if not os.path.exists(MASK_FILE):

    result = {
        "status": "WAITING_FOR_BURNED_AREA_MASK",
        "message":
            "هنوز burned_area_mask.tif تولید نشده است."
    }

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

    print(
        "burned_area_mask.tif هنوز موجود نیست."
    )

    raise SystemExit(0)


# ============================================================
# READ RASTER
# ============================================================

with rasterio.open(
    MASK_FILE
) as src:

    raster_crs = src.crs

    transform = src.transform

    pixel_width = abs(
        transform.a
    )

    pixel_height = abs(
        transform.e
    )

    pixel_area_m2 = (
        pixel_width
        *
        pixel_height
    )

    pixel_area_ha = (
        pixel_area_m2
        /
        10000.0
    )

    raster_data = src.read(1)


# ============================================================
# TOTAL BURNED AREA
# ============================================================

total_burned_pixels = int(
    (raster_data == 1).sum()
)

total_burned_ha = (
    total_burned_pixels
    *
    pixel_area_ha
)


# ============================================================
# CALCULATE AREA INSIDE GEOJSON
# ============================================================

def calculate_area(
    geojson_file
):

    layer = gpd.read_file(
        geojson_file
    )

    if layer.empty:
        return 0.0

    # تبدیل لایه به CRS رستر
    if layer.crs != raster_crs:

        layer = layer.to_crs(
            raster_crs
        )

    geometries = []

    for geometry in layer.geometry:

        if geometry is None:
            continue

        if geometry.is_empty:
            continue

        geometries.append(
            geometry
        )

    if not geometries:
        return 0.0

    # --------------------------------------------------------
    # Mask فقط برای محدوده موردنظر
    # --------------------------------------------------------

    with rasterio.open(
        MASK_FILE
    ) as src:

        clipped, _ = mask(
            src,
            geometries,
            crop=False,
            filled=False
        )

    burned_inside = (
        clipped[0] == 1
    )

    burned_pixels = int(
        burned_inside.sum()
    )

    area_ha = (
        burned_pixels
        *
        pixel_area_ha
    )

    return area_ha


# ============================================================
# CALCULATIONS
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "محاسبه فیلترهای مکانی"
)

print(
    f"مساحت هر پیکسل: "
    f"{pixel_area_ha:.6f} هکتار"
)

print(
    f"کل مساحت سوخته: "
    f"{total_burned_ha:.3f} هکتار"
)

print(
    "=========================================="
)


fars_area = calculate_area(
    FARS_FILE
)

protected_area = calculate_area(
    PROTECTED_FILE
)

hunting_area = calculate_area(
    HUNTING_FILE
)


# ============================================================
# RESULT
# ============================================================

result = {

    "status":
        "SUCCESS",

    "burned_area": {

        "total_ha":
            round(
                total_burned_ha,
                3
            ),

        "inside_fars_ha":
            round(
                fars_area,
                3
            ),

        "inside_protected_areas_ha":
            round(
                protected_area,
                3
            ),

        "inside_hunting_banned_ha":
            round(
                hunting_area,
                3
            )

    },

    "pixel": {

        "width_m":
            pixel_width,

        "height_m":
            pixel_height,

        "area_ha":
            pixel_area_ha

    }

}


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
# PRINT
# ============================================================

print("")
print(
    "=========================================="
)

print(
    f"کل حریق: "
    f"{total_burned_ha:.3f} هکتار"
)

print(
    f"داخل استان فارس: "
    f"{fars_area:.3f} هکتار"
)

print(
    f"مناطق چهارگانه: "
    f"{protected_area:.3f} هکتار"
)

print(
    f"مناطق شکار ممنوع: "
    f"{hunting_area:.3f} هکتار"
)

print(
    "=========================================="
)

print(
    f"نتیجه در {RESULT_FILE} ذخیره شد."
)
