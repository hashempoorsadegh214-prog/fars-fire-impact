import json
import os

import geopandas as gpd
import numpy as np
import rasterio

from rasterio.features import geometry_mask
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    Resampling
)


# ============================================================
# SETTINGS
# ============================================================

MASK_FILE = "burned_area_mask.tif"

FARS_FILE = "fars.geojson"
PROTECTED_FILE = "protected_areas.geojson"
HUNTING_FILE = "hunting_banned.geojson"

RESULT_FILE = "fire_filters_result.json"

# برای منطقه مورد آزمایش:
# 50.64 E , 30.03 N
# UTM Zone 39N
TARGET_EPSG = "EPSG:32639"

TARGET_RESOLUTION_M = 20.0


# ============================================================
# CHECK MASK
# ============================================================

if not os.path.exists(
    MASK_FILE
):

    result = {
        "status":
            "WAITING_FOR_BURNED_AREA_MASK",

        "message":
            "burned_area_mask.tif هنوز وجود ندارد."
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
        "burned_area_mask.tif وجود ندارد."
    )

    raise SystemExit(0)


# ============================================================
# OPEN SOURCE RASTER
# ============================================================

with rasterio.open(
    MASK_FILE
) as src:

    source_data = src.read(
        1
    )

    source_transform = src.transform

    source_crs = src.crs

    source_width = src.width

    source_height = src.height


print("")
print(
    "=========================================="
)

print(
    "اطلاعات رستر سوختگی"
)

print(
    f"CRS اولیه: {source_crs}"
)

print(
    f"ابعاد: "
    f"{source_width} x {source_height}"
)

print(
    "=========================================="
)


# ============================================================
# REPROJECT BURN MASK TO METRIC CRS
# ============================================================

transform, width, height = (
    calculate_default_transform(

        source_crs,

        TARGET_EPSG,

        source_width,

        source_height,

        *rasterio.transform.array_bounds(
            source_height,
            source_width,
            source_transform
        ),

        resolution=TARGET_RESOLUTION_M

    )
)


projected_mask = np.zeros(
    (
        height,
        width
    ),
    dtype=np.uint8
)


reproject(

    source=
        source_data,

    destination=
        projected_mask,

    src_transform=
        source_transform,

    src_crs=
        source_crs,

    dst_transform=
        transform,

    dst_crs=
        TARGET_EPSG,

    resampling=
        Resampling.nearest

)


# ============================================================
# PIXEL AREA
# ============================================================

pixel_area_m2 = (
    TARGET_RESOLUTION_M
    *
    TARGET_RESOLUTION_M
)

pixel_area_ha = (
    pixel_area_m2
    /
    10000.0
)


# ============================================================
# TOTAL BURNED AREA
# ============================================================

burned_mask = (
    projected_mask == 1
)

total_burned_pixels = int(
    burned_mask.sum()
)

total_burned_ha = (
    total_burned_pixels
    *
    pixel_area_ha
)


print("")
print(
    "=========================================="
)

print(
    "محاسبه کل سوختگی"
)

print(
    f"مساحت هر پیکسل: "
    f"{pixel_area_ha:.4f} هکتار"
)

print(
    f"پیکسل‌های سوخته: "
    f"{total_burned_pixels}"
)

print(
    f"کل مساحت سوخته: "
    f"{total_burned_ha:.3f} هکتار"
)

print(
    "=========================================="
)


# ============================================================
# CALCULATE AREA INSIDE GEOJSON
# ============================================================

def calculate_area(
    geojson_file
):

    if not os.path.exists(
        geojson_file
    ):

        print(
            f"فایل پیدا نشد: "
            f"{geojson_file}"
        )

        return 0.0


    layer = gpd.read_file(
        geojson_file
    )


    if layer.empty:

        return 0.0


    # --------------------------------------------------------
    # تبدیل GeoJSON به CRS متری
    # --------------------------------------------------------

    layer = layer.to_crs(
        TARGET_EPSG
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
    # ماسک فضایی
    # --------------------------------------------------------

    inside_mask = geometry_mask(

        geometries,

        out_shape=(
            height,
            width
        ),

        transform=
            transform,

        invert=True

    )


    burned_inside = (
        burned_mask
        &
        inside_mask
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
# CALCULATE FILTERS
# ============================================================

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

        "resolution_m":
            TARGET_RESOLUTION_M,

        "area_ha":
            pixel_area_ha

    },

    "projection": {

        "source_crs":
            str(
                source_crs
            ),

        "target_crs":
            TARGET_EPSG

    }

}


# ============================================================
# SAVE
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
# FINAL
# ============================================================

print("")
print(
    "=========================================="
)

print(
    "نتیجه فیلترهای مکانی"
)

print(
    f"کل سوختگی: "
    f"{total_burned_ha:.3f} هکتار"
)

print(
    f"داخل فارس: "
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
