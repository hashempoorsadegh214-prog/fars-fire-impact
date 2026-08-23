import json
import os

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import (
    calculate_default_transform,
    reproject,
    Resampling,
)


# ============================================================
# SETTINGS
# ============================================================

RESULT_FILE = "five_fires_spatial_filters_result.json"

FARS_FILE = "fars.geojson"
PROTECTED_FILE = "protected_areas.geojson"
HUNTING_FILE = "hunting_banned.geojson"

TARGET_EPSG = "EPSG:32639"
TARGET_RESOLUTION_M = 20.0


# ============================================================
# LOAD GEOJSON LAYERS
# ============================================================

def load_layer(path):

    if not os.path.exists(path):
        raise RuntimeError(
            f"فایل پیدا نشد: {path}"
        )

    layer = gpd.read_file(path)

    if layer.empty:
        raise RuntimeError(
            f"لایه خالی است: {path}"
        )

    layer = layer.to_crs(
        TARGET_EPSG
    )

    geometries = [
        geometry
        for geometry in layer.geometry
        if geometry is not None
        and not geometry.is_empty
    ]

    if not geometries:
        raise RuntimeError(
            f"هندسه معتبر در {path} پیدا نشد."
        )

    return geometries


fars_geometries = load_layer(
    FARS_FILE
)

protected_geometries = load_layer(
    PROTECTED_FILE
)

hunting_geometries = load_layer(
    HUNTING_FILE
)


# ============================================================
# PROCESS ONE MASK
# ============================================================

def calculate_filter_areas(
    mask_file
):

    if not os.path.exists(mask_file):
        raise RuntimeError(
            f"ماسک پیدا نشد: {mask_file}"
        )

    with rasterio.open(
        mask_file
    ) as src:

        source_data = src.read(1)

        source_transform = src.transform

        source_crs = src.crs

        source_width = src.width

        source_height = src.height


    # --------------------------------------------------------
    # Reproject burned mask to metric CRS
    # --------------------------------------------------------

    bounds = rasterio.transform.array_bounds(
        source_height,
        source_width,
        source_transform
    )

    transform, width, height = (
        calculate_default_transform(

            source_crs,
            TARGET_EPSG,

            source_width,
            source_height,

            *bounds,

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

        source=source_data,

        destination=projected_mask,

        src_transform=source_transform,

        src_crs=source_crs,

        dst_transform=transform,

        dst_crs=TARGET_EPSG,

        resampling=Resampling.nearest
    )


    burned_mask = (
        projected_mask == 1
    )


    pixel_area_ha = (
        TARGET_RESOLUTION_M
        *
        TARGET_RESOLUTION_M
        /
        10000.0
    )


    total_pixels = int(
        burned_mask.sum()
    )

    total_ha = (
        total_pixels
        *
        pixel_area_ha
    )


    # --------------------------------------------------------
    # Spatial filter helper
    # --------------------------------------------------------

    def area_inside(
        geometries
    ):

        inside = geometry_mask(

            geometries,

            out_shape=(
                height,
                width
            ),

            transform=transform,

            invert=True
        )

        burned_inside = (
            burned_mask
            &
            inside
        )

        pixels = int(
            burned_inside.sum()
        )

        return (
            pixels,
            pixels * pixel_area_ha
        )


    # --------------------------------------------------------
    # Calculate
    # --------------------------------------------------------

    fars_pixels, fars_ha = area_inside(
        fars_geometries
    )

    protected_pixels, protected_ha = area_inside(
        protected_geometries
    )

    hunting_pixels, hunting_ha = area_inside(
        hunting_geometries
    )


    return {

        "total": {

            "pixels":
                total_pixels,

            "hectares":
                round(
                    total_ha,
                    3
                )

        },

        "inside_fars": {

            "pixels":
                fars_pixels,

            "hectares":
                round(
                    fars_ha,
                    3
                )

        },

        "inside_protected_areas": {

            "pixels":
                protected_pixels,

            "hectares":
                round(
                    protected_ha,
                    3
                )

        },

        "inside_hunting_banned": {

            "pixels":
                hunting_pixels,

            "hectares":
                round(
                    hunting_ha,
                    3
                )

        },

        "pixel_area_ha":
            pixel_area_ha
    }


# ============================================================
# PROCESS FIVE FIRES
# ============================================================

results = []

failed = []


for index in range(
    1,
    6
):

    mask_file = (
        f"burned_area_mask_fire_{index}.tif"
    )

    print("")
    print(
        "=========================================="
    )

    print(
        f"حریق {index}/5"
    )

    print(
        f"ماسک: {mask_file}"
    )


    try:

        areas = calculate_filter_areas(
            mask_file
        )


        result = {

            "id":
                index,

            "mask":
                mask_file,

            "total_burned_ha":
                areas["total"]["hectares"],

            "inside_fars_ha":
                areas["inside_fars"]["hectares"],

            "inside_protected_areas_ha":
                areas[
                    "inside_protected_areas"
                ][
                    "hectares"
                ],

            "inside_hunting_banned_ha":
                areas[
                    "inside_hunting_banned"
                ][
                    "hectares"
                ]

        }


        results.append(
            result
        )


        print(
            f"کل سوختگی: "
            f"{result['total_burned_ha']:.3f} هکتار"
        )

        print(
            f"داخل فارس: "
            f"{result['inside_fars_ha']:.3f} هکتار"
        )

        print(
            f"مناطق چهارگانه: "
            f"{result['inside_protected_areas_ha']:.3f} هکتار"
        )

        print(
            f"شکار ممنوع: "
            f"{result['inside_hunting_banned_ha']:.3f} هکتار"
        )


    except Exception as error:

        print(
            f"خطا: {error}"
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
# SAVE
# ============================================================

output = {

    "status":
        "SUCCESS",

    "processed":
        len(results),

    "failed":
        failed,

    "results":
        results
}


with open(
    RESULT_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        output,
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
    "فیلتر مکانی ۵ حریق تمام شد"
)

print(
    f"موفق: {len(results)}"
)

print(
    f"ناموفق: {len(failed)}"
)

print(
    f"خروجی: {RESULT_FILE}"
)

print(
    "=========================================="
)
