const TOKEN_URL =
  "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token";

const PROCESS_URL =
  "https://sh.dataspace.copernicus.eu/process/v1";

const STATISTICS_URL =
  "https://sh.dataspace.copernicus.eu/statistics/v1";

const S2_TYPE =
  "sentinel-2-l2a";

const FARS_BOUNDS = [
  50.0,
  27.0,
  54.5,
  31.5
];

const BEFORE_DAYS = 5;
const AFTER_DAYS = 5;

const BURN_THRESHOLD = 0.27;

const RESOLUTION_M = 20;


/* ============================================================
   CORS
============================================================ */

function corsHeaders(origin) {

  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400"
  };
}


/* ============================================================
   JSON RESPONSE
============================================================ */

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
   DATE
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

  const value =
    new Date(
      date.getTime()
    );

  value.setUTCDate(
    value.getUTCDate() + days
  );

  return value;
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

  const coordinates =
    geometry.coordinates;

  if (
    !Array.isArray(
      coordinates
    )
  ) {
    return false;
  }

  if (
    geometry.type === "Polygon"
  ) {

    return coordinates.every(
      validateRing
    );
  }

  return coordinates.every(
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
      Number(
        point[0]
      );

    const lat =
      Number(
        point[1]
      );

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
   BOUNDS CHECK
============================================================ */

function geometryInsideFars(
  geometry
) {

  const bbox =
    geometryBounds(
      geometry
    );

  return (
    bbox[0] >= FARS_BOUNDS[0]
    &&
    bbox[1] >= FARS_BOUNDS[1]
    &&
    bbox[2] <= FARS_BOUNDS[2]
    &&
    bbox[3] <= FARS_BOUNDS[3]
  );
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
          new URLSearchParams({

            grant_type:
              "client_credentials",

            client_id:
              env.CDSE_CLIENT_ID,

            client_secret:
              env.CDSE_CLIENT_SECRET

          })
      }
    );


  if (
    !response.ok
  ) {

    const text =
      await response.text();

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
   FIND BEFORE / AFTER
============================================================ */

async function findImageDates(
  token,
  geometry,
  fireDate
) {

  let before = null;
  let after = null;


  /*
   * برای سبک بودن کار، وجود تصویر را
   * با Process API روی یک پیکسل مرکزی
   * تست می‌کنیم.
   *
   * Sentinel-2 قبل:
   * 1 تا 5 روز قبل
   */

  const bbox =
    geometryBounds(
      geometry
    );


  async function hasImage(
    date
  ) {

    const body = {

      input: {

        bounds: {

          bbox,

          properties: {

            crs:
              "http://www.opengis.net/"
              + "def/crs/OGC/1.3/CRS84"

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
          2,

        height:
          2,

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

    input: [
      "B04"
    ],

    output: {
      bands: 1
    }

  };

}


function evaluatePixel(
  sample
) {

  return [
    sample.B04
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
              "application/json"
          },

          body:
            JSON.stringify(
              body
            )
        }
      );


    return response.ok;
  }


  for (
    let offset = 1;
    offset <= BEFORE_DAYS;
    offset++
  ) {

    const date =
      isoDate(
        addDays(
          fireDate,
          -offset
        )
      );


    if (
      await hasImage(
        date
      )
    ) {

      before =
        date;

      break;
    }
  }


  for (
    let offset = 1;
    offset <= AFTER_DAYS;
    offset++
  ) {

    const date =
      isoDate(
        addDays(
          fireDate,
          offset
        )
      );


    if (
      await hasImage(
        date
      )
    ) {

      after =
        date;

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

function buildDnbrEvalscript(
  beforeDate,
  afterDate
) {

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

    output: {

      bands: 1,

      sampleType:
        "FLOAT32"

    },

    mosaicking:
      "ORBIT"

  };

}


function preProcessScenes(
  collections
) {

  const allowedDates = [
    "${beforeDate}",
    "${afterDate}"
  ];


  collections.scenes.orbits =
    collections.scenes.orbits.filter(
      function(scene) {

        const date =
          scene.dateFrom
            .split("T")[0];

        return allowedDates.includes(
          date
        );

      }
    );


  return collections;
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
   STATISTICS
============================================================ */

async function calculateStatistics(
  token,
  geometry,
  beforeDate,
  afterDate
) {

  const evalscript =
    buildDnbrEvalscript(
      beforeDate,
      afterDate
    );


  const body = {

    input: {

      bounds: {

        geometry,

        properties: {

          crs:
            "http://www.opengis.net/"
            + "def/crs/OGC/1.3/CRS84"

        }

      },

      data: [

        {

          type:
            S2_TYPE,

          dataFilter: {

            mosaickingOrder:
              "leastCC"

          }

        }

      ]

    },


    aggregation: {

      timeRange: {

        from:
          `${beforeDate}T00:00:00Z`,

        to:
          `${afterDate}T23:59:59Z`

      },

      aggregationInterval: {

        of:
          "P10D"

      },

      lastIntervalBehavior:
        "SHORTEN",

      evalscript,

      resx:
        RESOLUTION_M,

      resy:
        RESOLUTION_M

    },


    calculations: {

      default: {

        histograms: {

          default: {

            bins: [
              -1,
              BURN_THRESHOLD,
              1
            ]

          }

        },

        statistics: {}

      }

    }

  };


  const response =
    await fetch(
      STATISTICS_URL,
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
      `خطای Statistical API: HTTP ${response.status}`
    );
  }


  const data =
    await response.json();


  return data;
}


/* ============================================================
   EXTRACT BURNED PIXELS
============================================================ */

function extractBurnedPixels(
  data
) {

  const item =
    data?.data?.[0];

  const output =
    item?.outputs?.default;

  const band =
    output?.bands?.B0;

  const histogram =
    band?.histogram;


  if (
    !histogram
    ||
    !Array.isArray(
      histogram.bins
    )
  ) {

    throw new Error(
      "Histogram مربوط به dNBR دریافت نشد."
    );
  }


  let burnedPixels = 0;


  for (
    const bin
    of histogram.bins
  ) {

    if (
      Number(
        bin.lowEdge
      )
      >= BURN_THRESHOLD
    ) {

      burnedPixels +=
        Number(
          bin.count || 0
        );
    }
  }


  burnedPixels +=
    Number(
      histogram.overflowCount || 0
    );


  return burnedPixels;
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


  const chunkSize =
    8192;


  let binary = "";


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
            + "def/crs/OGC/1.3/CRS84"

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

    throw new Error(
      `خطای False Color: HTTP ${response.status}`
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
   BURNED MASK IMAGE
============================================================ */

async function getBurnedMask(
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
            + "def/crs/OGC/1.3/CRS84"

        }

      },

      data: [

        {

          type:
            S2_TYPE,

          dataFilter: {

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


    evalscript:
      buildBurnMaskEvalscript(
        beforeDate,
        afterDate
      )

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

    throw new Error(
      `خطای Burn Mask: HTTP ${response.status}`
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
   BURN MASK EVALSCRIPT
============================================================ */

function buildBurnMaskEvalscript(
  beforeDate,
  afterDate
) {

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

    output: {

      bands: 4,

      sampleType:
        "AUTO"

    },

    mosaicking:
      "ORBIT"

  };

}


function preProcessScenes(
  collections
) {

  const allowedDates = [
    "${beforeDate}",
    "${afterDate}"
  ];


  collections.scenes.orbits =
    collections.scenes.orbits.filter(
      function(scene) {

        const date =
          scene.dateFrom
            .split("T")[0];

        return allowedDates.includes(
          date
        );

      }
    );


  return collections;
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


  if (
    !geometryInsideFars(
      geometry
    )
  ) {

    throw new Error(
      "منطقه خارج از محدوده استان فارس است."
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


  const {
    before,
    after
  } =
    await findImageDates(
      token,
      geometry,
      fireDate
    );


  if (!before) {

    throw new Error(
      "تصویر Sentinel-2 قبل از حریق پیدا نشد."
    );
  }


  if (!after) {

    throw new Error(
      "تصویر Sentinel-2 بعد از حریق پیدا نشد."
    );
  }


  const statistics =
    await calculateStatistics(
      token,
      geometry,
      before,
      after
    );


  const burnedPixels =
    extractBurnedPixels(
      statistics
    );


  const pixelAreaHa =
    (
      RESOLUTION_M
      *
      RESOLUTION_M
    )
    /
    10000;


  const burnedAreaHa =
    burnedPixels
    *
    pixelAreaHa;


  const falseColor =
    await getFalseColor(
      token,
      geometry,
      after
    );


  const burnedMask =
    await getBurnedMask(
      token,
      geometry,
      before,
      after
    );


  return {

    status:
      "SUCCESS",

    date,

    region_type:
      regionType,

    region_name:
      regionName || "",

    before_date:
      before,

    after_date:
      after,

    dnbr_threshold:
      BURN_THRESHOLD,

    burned_pixels:
      burnedPixels,

    pixel_area_ha:
      pixelAreaHa,

    burned_area: {

      total_ha:
        Number(
          burnedAreaHa.toFixed(3)
        ),

      inside_fars_ha:
        Number(
          burnedAreaHa.toFixed(3)
        ),

      inside_protected_areas_ha:
        regionType === "protected"
          ? Number(
              burnedAreaHa.toFixed(3)
            )
          : 0,

      inside_hunting_banned_ha:
        regionType === "hunting"
          ? Number(
              burnedAreaHa.toFixed(3)
            )
          : 0

    },

    false_color_url:
      falseColor.dataUrl,

    false_color_bounds:
      falseColor.bounds,

    burned_mask_url:
      burnedMask.dataUrl,

    burned_mask_bounds:
      burnedMask.bounds

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
            "خطای نامشخص در محاسبه."
        },

        400,

        origin
      );
    }

  }

};
