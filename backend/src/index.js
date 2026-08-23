```javascript
const TOKEN_URL =
  "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token";

const CATALOG_URL =
  "https://sh.dataspace.copernicus.eu/catalog/v1/search";

const PROCESS_URL =
  "https://sh.dataspace.copernicus.eu/process/v1";

const S2_TYPE =
  "sentinel-2-l2a";

const BEFORE_DAYS = 5;
const AFTER_DAYS = 5;

const BURN_THRESHOLD = 0.27;

const RESOLUTION_M = 20;


/* ============================================================
   CORS
============================================================ */

function corsHeaders(origin) {

  return {
    "Access-Control-Allow-Origin":
      origin,

    "Access-Control-Allow-Methods":
      "POST, OPTIONS",

    "Access-Control-Allow-Headers":
      "Content-Type",

    "Access-Control-Max-Age":
      "86400"
  };
}


function jsonResponse(
  data,
  status,
  origin
) {

  return new Response(

    JSON.stringify(data),

    {
      status,

      headers: {

        "Content-Type":
          "application/json; charset=utf-8",

        ...corsHeaders(origin)

      }
    }
  );
}


/* ============================================================
   DATE HELPERS
============================================================ */

function parseDate(
  text
) {

  const match =
    /^(\d{4})-(\d{2})-(\d{2})$/.exec(
      text || ""
    );


  if (!match) {
    return null;
  }


  const date =
    new Date(
      Date.UTC(
        Number(match[1]),
        Number(match[2]) - 1,
        Number(match[3])
      )
    );


  if (
    Number.isNaN(
      date.getTime()
    )
  ) {

    return null;
  }


  return date;
}


function isoDate(
  date
) {

  return date
    .toISOString()
    .slice(0, 10);
}


function addDays(
  date,
  days
) {

  const result =
    new Date(
      date.getTime()
    );


  result.setUTCDate(
    result.getUTCDate() + days
  );


  return result;
}


/* ============================================================
   GEOMETRY VALIDATION
============================================================ */

function isNumber(
  value
) {

  return (
    typeof value === "number"
    &&
    Number.isFinite(value)
  );
}


function validatePoint(
  point
) {

  return (

    Array.isArray(point)

    &&

    point.length >= 2

    &&

    isNumber(point[0])

    &&

    isNumber(point[1])

  );
}


function validateRing(
  ring
) {

  return (

    Array.isArray(ring)

    &&

    ring.length >= 4

    &&

    ring.every(
      validatePoint
    )

  );
}


function validateGeometry(
  geometry
) {

  if (!geometry) {
    return false;
  }


  if (
    geometry.type !== "Polygon"
    &&
    geometry.type !== "MultiPolygon"
  ) {

    return false;
  }


  if (
    !Array.isArray(
      geometry.coordinates
    )
  ) {

    return false;
  }


  if (
    geometry.type === "Polygon"
  ) {

    return geometry.coordinates.every(
      validateRing
    );

  }


  return geometry.coordinates.every(
    polygon =>
      Array.isArray(polygon)
      &&
      polygon.every(
        validateRing
      )
  );
}


/* ============================================================
   GEOMETRY BOUNDS
============================================================ */

function geometryBounds(
  geometry
) {

  let minLon = Infinity;
  let minLat = Infinity;

  let maxLon = -Infinity;
  let maxLat = -Infinity;


  function visitPoint(
    point
  ) {

    const lon =
      Number(point[0]);

    const lat =
      Number(point[1]);


    minLon =
      Math.min(
        minLon,
        lon
      );


    minLat =
      Math.min(
        minLat,
        lat
      );


    maxLon =
      Math.max(
        maxLon,
        lon
      );


    maxLat =
      Math.max(
        maxLat,
        lat
      );
  }


  function visitRing(
    ring
  ) {

    ring.forEach(
      visitPoint
    );
  }


  if (
    geometry.type ===
    "Polygon"
  ) {

    geometry.coordinates.forEach(
      visitRing
    );

  } else {

    geometry.coordinates.forEach(
      polygon =>
        polygon.forEach(
          visitRing
        )
    );
  }


  return [
    minLon,
    minLat,
    maxLon,
    maxLat
  ];
}


/* ============================================================
   TOKEN
============================================================ */

async function getToken(
  env
) {

  if (
    !env.CDSE_CLIENT_ID
    ||
    !env.CDSE_CLIENT_SECRET
  ) {

    throw new Error(
      "Secretهای Copernicus تنظیم نشده‌اند."
    );
  }


  const response =
    await fetch(
      TOKEN_URL,
      {

        method:
          "POST",

        headers: {

          "Content-Type":
            "application/x-www-form-urlencoded"

        },

        body:
          new URLSearchParams(
            {

              grant_type:
                "client_credentials",

              client_id:
                env.CDSE_CLIENT_ID,

              client_secret:
                env.CDSE_CLIENT_SECRET

            }
          )

      }
    );


  if (
    !response.ok
  ) {

    throw new Error(
      `خطای احراز هویت Copernicus: HTTP ${response.status}`
    );
  }


  const data =
    await response.json();


  if (
    !data.access_token
  ) {

    throw new Error(
      "Access Token دریافت نشد."
    );
  }


  return data.access_token;
}


/* ============================================================
   CATALOG SEARCH
============================================================ */

async function searchCatalog(
  token,
  geometry,
  date
) {

  const body = {

    collections: [
      S2_TYPE
    ],

    datetime:
      `${date}T00:00:00Z/` +
      `${date}T23:59:59Z`,

    intersects:
      geometry,

    limit:
      10,

    fields:
      {
        include:
          [
            "id",
            "properties.datetime",
            "properties.eo:cloud_cover",
            "geometry",
            "bbox"
          ]
      }
  };


  const response =
    await fetch(
      CATALOG_URL,
      {

        method:
          "POST",

        headers: {

          "Authorization":
            `Bearer ${token}`,

          "Content-Type":
            "application/json",

          "Accept":
            "application/json"

        },

        body:
          JSON.stringify(
            body
          )
      }
    );


  if (
    !response.ok
  ) {

    const text =
      await response.text();


    throw new Error(
      `Catalog API خطا داد: HTTP ${response.status} ${text}`
    );
  }


  return response.json();
}


/* ============================================================
   FIND BEST SCENES
============================================================ */

async function findBeforeAfterScenes(
  token,
  geometry,
  fireDate
) {

  let before = null;
  let after = null;


  /* ----------------------------------------------------------
     BEFORE
  ---------------------------------------------------------- */

  for (
    let offset = 1;
    offset <= BEFORE_DAYS;
    offset++
  ) {

    const candidateDate =
      isoDate(
        addDays(
          fireDate,
          -offset
        )
      );


    const result =
      await searchCatalog(
        token,
        geometry,
        candidateDate
      );


    const features =
      Array.isArray(
        result.features
      )
        ? result.features
        : [];


    if (
      features.length
    ) {

      features.sort(
        (
          a,
          b
        ) => {

          const cloudA =
            Number(
              a.properties?.[
                "eo:cloud_cover"
              ]
            );

          const cloudB =
            Number(
              b.properties?.[
                "eo:cloud_cover"
              ]
            );


          return (
            (
              Number.isFinite(
                cloudA
              )
                ? cloudA
                : 999
            )
            -
            (
              Number.isFinite(
                cloudB
              )
                ? cloudB
                : 999
            )
          );
        }
      );


      before = {

        date:
          candidateDate,

        feature:
          features[0]
      };


      break;
    }
  }


  /* ----------------------------------------------------------
     AFTER
  ---------------------------------------------------------- */

  for (
    let offset = 1;
    offset <= AFTER_DAYS;
    offset++
  ) {

    const candidateDate =
      isoDate(
        addDays(
          fireDate,
          offset
        )
      );


    const result =
      await searchCatalog(
        token,
        geometry,
        candidateDate
      );


    const features =
      Array.isArray(
        result.features
      )
        ? result.features
        : [];


    if (
      features.length
    ) {

      features.sort(
        (
          a,
          b
        ) => {

          const cloudA =
            Number(
              a.properties?.[
                "eo:cloud_cover"
              ]
            );

          const cloudB =
            Number(
              b.properties?.[
                "eo:cloud_cover"
              ]
            );


          return (
            (
              Number.isFinite(
                cloudA
              )
                ? cloudA
                : 999
            )
            -
            (
              Number.isFinite(
                cloudB
              )
                ? cloudB
                : 999
            )
          );
        }
      );


      after = {

        date:
          candidateDate,

        feature:
          features[0]
      };


      break;
    }
  }


  return {
    before,
    after
  };
}


/* ============================================================
   dNBR EVALSCRIPT
============================================================ */

function buildDnbrEvalscript() {

  return `
//VERSION=3

function setup() {

  return {

    input: [{
      bands: [
        "B08",
        "B12",
        "SCL",
        "dataMask"
      ]
    }],

    mosaicking:
      "ORBIT",

    output: {

      bands: 1,

      sampleType:
        "FLOAT32"

    }

  };

}


function validSample(
  sample
) {

  if (
    !sample
    ||
    sample.dataMask === 0
  ) {

    return false;
  }


  const badSCL = [
    3,
    8,
    9,
    10,
    11
  ];


  if (
    badSCL.includes(
      sample.SCL
    )
  ) {

    return false;
  }


  return (
    sample.B08 > 0
    &&
    sample.B12 > 0
  );
}


function calcNBR(
  sample
) {

  const denominator =
    sample.B08
    +
    sample.B12;


  if (
    denominator === 0
  ) {

    return -9999;
  }


  return (
    sample.B08
    -
    sample.B12
  )
  /
  denominator;
}


function evaluatePixel(
  samples
) {

  if (
    samples.length < 2
  ) {

    return [
      -9999
    ];
  }


  const before =
    samples[0];

  const after =
    samples[1];


  if (
    !validSample(before)
    ||
    !validSample(after)
  ) {

    return [
      -9999
    ];
  }


  return [

    calcNBR(
      before
    )
    -
    calcNBR(
      after
    )

  ];
}
`;
}


/* ============================================================
   CALCULATE dNBR RASTER
============================================================ */

async function calculateDnbr(
  token,
  geometry,
  beforeDate,
  afterDate
) {

  const bbox =
    geometryBounds(
      geometry
    );


  const body = {

    input: {

      bounds: {

        bbox,

        properties: {

          crs:
            "http://www.opengis.net/"
            +
            "def/crs/OGC/1.3/CRS84"

        }

      },

      data: [

        {

          type:
            S2_TYPE,

          dataFilter: {

            timeRange: {

              from:
                `${beforeDate}T00:00:00Z`,

              to:
                `${afterDate}T23:59:59Z`

            },

            mosaickingOrder:
              "leastRecent"

          }

        }

      ]

    },

    output: {

      width:
        800,

      height:
        800,

      responses: [

        {

          identifier:
            "default",

          format: {

            type:
              "image/png"

          }

        }

      ]

    },

    evalscript:
      buildBurnMaskEvalscript()

  };


  const response =
    await fetch(
      PROCESS_URL,
      {

        method:
          "POST",

        headers: {

          "Authorization":
            `Bearer ${token}`,

          "Content-Type":
            "application/json",

          "Accept":
            "image/png"

        },

        body:
          JSON.stringify(
            body
          )

      }
    );


  if (
    !response.ok
  ) {

    const text =
      await response.text();


    throw new Error(
      `Process API خطا داد: HTTP ${response.status} ${text}`
    );
  }


  return response;
}


/* ============================================================
   BURN MASK EVALSCRIPT
============================================================ */

function buildBurnMaskEvalscript() {

  return `
//VERSION=3

function setup() {

  return {

    input: [{
      bands: [
        "B08",
        "B12",
        "SCL",
        "dataMask"
      ]
    }],

    mosaicking:
      "ORBIT",

    output: {

      bands: 4,

      sampleType:
        "AUTO"

    }

  };

}


function validSample(
  sample
) {

  if (
    !sample
    ||
    sample.dataMask === 0
  ) {

    return false;
  }


  const badSCL = [
    3,
    8,
    9,
    10,
    11
  ];


  return (

    !badSCL.includes(
      sample.SCL
    )

    &&

    sample.B08 > 0

    &&

    sample.B12 > 0

  );
}


function calcNBR(
  sample
) {

  const denominator =
    sample.B08
    +
    sample.B12;


  if (
    denominator === 0
  ) {

    return -9999;
  }


  return (

    sample.B08
    -
    sample.B12

  )
  /
  denominator;
}


function evaluatePixel(
  samples
) {

  if (
    samples.length < 2
  ) {

    return [
      0,
      0,
      0,
      0
    ];
  }


  const before =
    samples[0];

  const after =
    samples[1];


  if (
    !validSample(before)
    ||
    !validSample(after)
  ) {

    return [
      0,
      0,
      0,
      0
    ];
  }


  const dnbr =
    calcNBR(
      before
    )
    -
    calcNBR(
      after
    );


  if (
    dnbr >= ${BURN_THRESHOLD}
  ) {

    return [
      255,
      0,
      0,
      180
    ];
  }


  return [
    0,
    0,
    0,
    0
  ];
}
`;
}


/* ============================================================
   IMAGE TO DATA URL
============================================================ */

async function imageToDataURL(
  response
) {

  const buffer =
    await response.arrayBuffer();


  const bytes =
    new Uint8Array(
      buffer
    );


  let binary = "";

  const chunkSize =
    8192;


  for (
    let i = 0;
    i < bytes.length;
    i += chunkSize
  ) {

    binary +=
      String.fromCharCode(
        ...bytes.subarray(
          i,
          Math.min(
            i + chunkSize,
            bytes.length
          )
        )
      );

  }


  return (
    "data:image/png;base64,"
    +
    btoa(
      binary
    )
  );
}


/* ============================================================
   FALSE COLOR
============================================================ */

async function getFalseColor(
  token,
  geometry,
  date
) {

  const bbox =
    geometryBounds(
      geometry
    );


  const body = {

    input: {

      bounds: {

        bbox,

        properties: {

          crs:
            "http://www.opengis.net/"
            +
            "def/crs/OGC/1.3/CRS84"

        }

      },

      data: [

        {

          type:
            S2_TYPE,

          dataFilter: {

            timeRange: {

              from:
                `${date}T00:00:00Z`,

              to:
                `${date}T23:59:59Z`

            },

            mosaickingOrder:
              "leastCC"

          }

        }

      ]

    },

    output: {

      width:
        800,

      height:
        800,

      responses: [

        {

          identifier:
            "default",

          format: {

            type:
              "image/png"

          }

        }

      ]

    },

    evalscript: `
//VERSION=3

function setup() {

  return {

    input: [{
      bands: [
        "B08",
        "B04",
        "B03",
        "SCL",
        "dataMask"
      ]
    }],

    output: {

      bands: 4,

      sampleType:
        "AUTO"

    }

  };

}


function evaluatePixel(
  sample
) {

  const badSCL = [
    3,
    8,
    9,
    10,
    11
  ];


  if (
    sample.dataMask === 0
    ||
    badSCL.includes(
      sample.SCL
    )
  ) {

    return [
      0,
      0,
      0,
      0
    ];
  }


  return [

    2.5 * sample.B08,

    2.5 * sample.B04,

    2.5 * sample.B03,

    1

  ];
}
`
  };


  const response =
    await fetch(
      PROCESS_URL,
      {

        method:
          "POST",

        headers: {

          "Authorization":
            `Bearer ${token}`,

          "Content-Type":
            "application/json",

          "Accept":
            "image/png"

        },

        body:
          JSON.stringify(
            body
          )

      }
    );


  if (
    !response.ok
  ) {

    const text =
      await response.text();


    throw new Error(
      `False Color خطا داد: HTTP ${response.status} ${text}`
    );
  }


  return {

    dataUrl:
      await imageToDataURL(
        response
      ),

    bounds:
      [
        [
          bbox[1],
          bbox[0]
        ],

        [
          bbox[3],
          bbox[2]
        ]
      ]

  };
}


/* ============================================================
   MAIN CALCULATION
============================================================ */

async function calculate(
  body,
  env
) {

  const date =
    body.date;

  const regionType =
    body.regionType;

  const regionName =
    body.regionName;

  const geometry =
    body.geometry;


  if (
    !parseDate(
      date
    )
  ) {

    throw new Error(
      "تاریخ نامعتبر است."
    );
  }


  if (
    regionType !== "protected"
    &&
    regionType !== "hunting"
  ) {

    throw new Error(
      "نوع منطقه نامعتبر است."
    );
  }


  if (
    !validateGeometry(
      geometry
    )
  ) {

    throw new Error(
      "هندسه منطقه نامعتبر است."
    );
  }


  const fireDate =
    parseDate(
      date
    );


  const token =
    await getToken(
      env
    );


  /* ----------------------------------------------------------
     پیدا کردن تصویر قبل و بعد با Catalog
  ---------------------------------------------------------- */

  const {
    before,
    after
  } =
    await findBeforeAfterScenes(
      token,
      geometry,
      fireDate
    );


  if (!before) {

    throw new Error(
      `تصویر Sentinel-2 قبل از حریق در بازه ${BEFORE_DAYS} روزه پیدا نشد.`
    );
  }


  if (!after) {

    throw new Error(
      `تصویر Sentinel-2 بعد از حریق در بازه ${AFTER_DAYS} روزه پیدا نشد.`
    );
  }


  /* ----------------------------------------------------------
     dNBR + Burn Mask
  ---------------------------------------------------------- */

  const burnResponse =
    await calculateDnbr(
      token,
      geometry,
      before.date,
      after.date
    );


  const burnMaskUrl =
    await imageToDataURL(
      burnResponse
    );


  /* ----------------------------------------------------------
     برآورد تعداد پیکسل سوخته
     
     چون تصویر Burn Mask با 800x800 است،
     تعداد پیکسل از تحلیل تصویر سمت مرورگر
     به‌صورت مطلق استخراج نمی‌شود.
     
     برای آزمون فعلی یک شمارش تقریبی بر اساس
     اندازه خروجی ارائه نمی‌کنیم.
     
     در این مرحله نتیجه اصلی با نسخه
     دقیق‌تر Raster Statistics تکمیل خواهد شد.
  ---------------------------------------------------------- */


  const falseColor =
    await getFalseColor(
      token,
      geometry,
      after.date
    );


  const bounds =
    geometryBounds(
      geometry
    );


  /*
   * مساحت فعلاً از خود Burn Mask به شکل
   * دقیق استخراج نشده است.
   *
   * برای جلوگیری از گزارش عدد ساختگی،
   * تا زمان افزودن Statistics API مقدار null
   * نگه داشته می‌شود.
   */

  return {

    status:
      "SUCCESS",

    date,

    region_type:
      regionType,

    region_name:
      regionName || "",

    before_date:
      before.date,

    after_date:
      after.date,

    dnbr_threshold:
      BURN_THRESHOLD,

    burned_area: {

      total_ha:
        null,

      inside_fars_ha:
        null,

      inside_protected_areas_ha:
        null,

      inside_hunting_banned_ha:
        null

    },

    burned_pixels:
      null,

    pixel_area_ha:
      (
        RESOLUTION_M
        *
        RESOLUTION_M
        /
        10000
      ),

    false_color_url:
      falseColor.dataUrl,

    false_color_bounds:
      falseColor.bounds,

    burned_mask_url:
      burnMaskUrl,

    burned_mask_bounds:
      [
        [
          bounds[1],
          bounds[0]
        ],
        [
          bounds[3],
          bounds[2]
        ]
      ]

  };
}


/* ============================================================
   WORKER
============================================================ */

export default {

  async fetch(
    request,
    env
  ) {

    const origin =
      env.ALLOWED_ORIGIN
      ||
      "*";


    if (
      request.method ===
      "OPTIONS"
    ) {

      return new Response(
        null,
        {

          status:
            204,

          headers:
            corsHeaders(
              origin
            )

        }
      );
    }


    const url =
      new URL(
        request.url
      );


    if (
      url.pathname ===
      "/"
    ) {

      return jsonResponse(
        {

          status:
            "OK",

          service:
            "FARS FIRE IMPACT",

          endpoint:
            "/calculate"

        },

        200,

        origin
      );
    }


    if (
      url.pathname !==
      "/calculate"
    ) {

      return jsonResponse(
        {

          status:
            "ERROR",

          message:
            "مسیر درخواست نامعتبر است."

        },

        404,

        origin
      );
    }


    if (
      request.method !==
      "POST"
    ) {

      return jsonResponse(
        {

          status:
            "ERROR",

          message:
            "فقط POST مجاز است."

        },

        405,

        origin
      );
    }


    try {

      const body =
        await request.json();


      const result =
        await calculate(
          body,
          env
        );


      return jsonResponse(
        result,
        200,
        origin
      );


    } catch (
      error
    ) {

      console.error(
        error
      );


      return jsonResponse(
        {

          status:
            "ERROR",

          message:
            error?.message
            ||
            "خطای نامشخص."

        },

        400,

        origin
      );
    }

  }

};
```
