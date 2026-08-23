const TOKEN_URL =
  "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token";

const SH_BASE =
  "https://sh.dataspace.copernicus.eu";

const STATISTICS_URL =
  `${SH_BASE}/statistics/v1`;

const PROCESS_URL =
  `${SH_BASE}/process/v1`;

const CATALOG_URL =
  `${SH_BASE}/catalog/v1/search`;

const S2_TYPE =
  "sentinel-2-l2a";

const FARS_BOUNDS = [
  50.0,
  27.0,
  54.5,
  31.5
];

const MAX_REGION_AREA_KM2 = 50000;

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

  return Number.isNaN(
    date.getTime()
  )
    ? null
    : date;
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

function isNumber(value) {

  return (
    typeof value === "number"
    &&
    Number.isFinite(value)
  );
}


function validatePoint(
  point
) {

  if (
    !Array.isArray(point)
    ||
    point.length < 2
  ) {

    return false;
  }

  return (
    isNumber(point[0])
    &&
    isNumber(point[1])
  );
}


function validateRing(
  ring
) {

  if (
    !Array.isArray(ring)
    ||
    ring.length < 4
  ) {

    return false;
  }

  return ring.every(
    validatePoint
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
   GEOMETRY BBOX
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

    const lon = point[0];
    const lat = point[1];

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

    for (
      const point
      of ring
    ) {

      visitPoint(
        point
      );
    }
  }


  if (
    geometry.type ===
    "Polygon"
  ) {

    for (
      const ring
      of geometry.coordinates
    ) {

      visitRing(
        ring
      );
    }

  } else {

    for (
      const polygon
      of geometry.coordinates
    ) {

      for (
        const ring
        of polygon
      ) {

        visitRing(
          ring
        );
      }
    }
  }


  return [
    minLon,
    minLat,
    maxLon,
    maxLat
  ];
}


/* ============================================================
   AREA APPROXIMATION
============================================================ */

function approximateAreaKm2(
  geometry
) {

  const bbox =
    geometryBounds(
      geometry
    );

  const minLon = bbox[0];
  const minLat = bbox[1];
  const maxLon = bbox[2];
  const maxLat = bbox[3];

  const lat =
    (
      minLat
      +
      maxLat
    ) / 2;

  const latKm =
    (maxLat - minLat)
    * 111.32;

  const lonKm =
    (maxLon - minLon)
    *
    111.32
    *
    Math.cos(
      lat * Math.PI / 180
    );

  return (
    Math.abs(
      latKm * lonKm
    )
  );
}


/* ============================================================
   CHECK FARS BOUNDS
============================================================ */

function geometryInsideFarsBox(
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
   GET COPERNICUS TOKEN
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
      "CDSE credentials are not configured."
    );
  }


  const response =
    await fetch(
      TOKEN_URL,
      {
        method: "POST",

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


  if (!response.ok) {

    const text =
      await response.text();

    throw new Error(
      `Copernicus token error ${response.status}: ${text}`
    );
  }


  const data =
    await response.json();


  if (
    !data.access_token
  ) {

    throw new Error(
      "Copernicus access token missing."
    );
  }


  return data.access_token;
}


/* ============================================================
   CATALOG SEARCH
============================================================ */

async function searchScenes(
  token,
  geometry,
  startDate,
  endDate
) {

  const body = {

    datetime:
      `${startDate}T00:00:00Z/` +
      `${endDate}T23:59:59Z`,

    collections: [
      "sentinel-2-l2a"
    ],

    intersects:
      geometry,

    limit:
      20

  };


  const response =
    await fetch(
      CATALOG_URL,
      {
        method: "POST",

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


  if (!response.ok) {

    const text =
      await response.text();

    throw new Error(
      `Catalog error ${response.status}: ${text}`
    );
  }


  return response.json();
}


/* ============================================================
   FIND BEFORE / AFTER
============================================================ */

async function findBeforeAfter(
  token,
  geometry,
  fireDate
) {

  let before = null;
  let after = null;


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


    const result =
      await searchScenes(
        token,
        geometry,
        date,
        date
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

      before = {
        date,
        feature:
          features[0]
      };

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


    const result =
      await searchScenes(
        token,
        geometry,
        date,
        date
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

      after = {
        date,
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
        "B8A",
        "B12",
        "SCL",
        "dataMask"
      ]
    }],

    mosaicking: "ORBIT",

    output: [
      {
        id: "dnbr",
        bands: 1,
        sampleType: "FLOAT32"
      },
      {
        id: "dataMask",
        bands: 1,
        sampleType: "UINT8"
      }
    ]

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
      function(orbit) {

        const date =
          orbit.dateFrom
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
    sample.B8A > 0
    &&
    sample.B12 > 0
  );

}


function calcNBR(
  sample
) {

  const denominator =
    sample.B8A
    +
    sample.B12;


  if (
    denominator === 0
  ) {

    return -9999;

  }


  return (
    sample.B8A
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

    return {

      dnbr: [
        -9999
      ],

      dataMask: [
        0
      ]

    };

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

    return {

      dnbr: [
        -9999
      ],

      dataMask: [
        0
      ]

    };

  }


  const nbrBefore =
    calcNBR(
      before
    );

  const nbrAfter =
    calcNBR(
      after
    );


  return {

    dnbr: [
      nbrBefore
      -
      nbrAfter
    ],

    dataMask: [
      1
    ]

  };

}
`;
}


/* ============================================================
   STATISTICAL REQUEST
============================================================ */

async function calculateDnbrStatistics(
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


  const statsBody = {

    input: {

      bounds: {

        geometry,

        properties: {

          crs:
            "http://www.opengis.net/def/crs/EPSG/0/4326"

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

        of: "P10D"

      },

      evalscript,

      resx:
        RESOLUTION_M,

      resy:
        RESOLUTION_M

    },


    calculations: {

      dnbr: {

        histograms: {

          default: {

            bins: [
              -1.0,
              0.0,
              BURN_THRESHOLD,
              1.0
            ]

          }

        },

        statistics: {

          default: {}

        }

      }

    }

  };


  const response =
    await fetch(
      STATISTICS_URL,
      {

        method: "POST",

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
            statsBody
          )

      }
    );


  if (!response.ok) {

    const text =
      await response.text();

    throw new Error(
      `Statistics error ${response.status}: ${text}`
    );
  }


  return response.json();
}


/* ============================================================
   PARSE BURNED AREA
============================================================ */

function parseBurnedArea(
  statistics
) {

  const first =
    statistics?.data?.[0];

  const output =
    first?.outputs?.dnbr;

  const band =
    output?.bands?.B0;

  const histogram =
    band?.histogram;

  if (!histogram) {

    throw new Error(
      "dNBR histogram was not returned."
    );
  }


  let burnedPixels = 0;


  for (
    const bin
    of histogram.bins || []
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


  if (
    Number(
      histogram.overflowCount
    )
    > 0
  ) {

    burnedPixels +=
      Number(
        histogram.overflowCount
      );

  }


  const pixelAreaHa =
    (
      RESOLUTION_M
      *
      RESOLUTION_M
    )
    /
    10000;


  return {

    burnedPixels,

    pixelAreaHa,

    burnedAreaHa:
      burnedPixels
      *
      pixelAreaHa,

    statistics

  };

}


/* ============================================================
   FALSE COLOR PROCESS API
============================================================ */

async function getFalseColor(
  token,
  geometry,
  date
) {

  const evalscript = `
//VERSION=3

function setup() {

  return {

    input: [{
      bands: [
        "B08",
        "B04",
        "B03",
        "SCL"
      ]
    }],

    output: {
      bands: 3,
      sampleType: "AUTO"
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
    badSCL.includes(
      sample.SCL
    )
  ) {

    return [
      0,
      0,
      0
    ];

  }


  return [

    2.5 * sample.B08,

    2.5 * sample.B04,

    2.5 * sample.B03

  ];

}
`;


  const requestBody = {

    input: {

      bounds: {

        geometry,

        properties: {

          crs:
            "http://www.opengis.net/def/crs/EPSG/0/4326"

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


    evalscript

  };


  const response =
    await fetch(
      PROCESS_URL,
      {

        method: "POST",

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
            requestBody
          )

      }
    );


  if (!response.ok) {

    const text =
      await response.text();

    throw new Error(
      `False Color error ${response.status}: ${text}`
    );
  }


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


  const base64 =
    btoa(
      binary
    );


  const bbox =
    geometryBounds(
      geometry
    );


  return {

    dataUrl:
      `data:image/png;base64,${base64}`,

    bounds: [
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
  requestData,
  env
) {

  const {

    date,

    regionType,

    regionName,

    geometry

  } = requestData;


  if (!parseDate(date)) {

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
    !geometryInsideFarsBox(
      geometry
    )
  ) {

    throw new Error(
      "منطقه انتخاب‌شده خارج از محدوده فارس است."
    );
  }


  const areaKm2 =
    approximateAreaKm2(
      geometry
    );


  if (
    areaKm2 >
    MAX_REGION_AREA_KM2
  ) {

    throw new Error(
      "محدوده انتخاب‌شده بیش از حد بزرگ است."
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
    await findBeforeAfter(
      token,
      geometry,
      fireDate
    );


  if (!before) {

    throw new Error(
      "تصویر Sentinel-2 قبل از تاریخ انتخاب‌شده پیدا نشد."
    );
  }


  if (!after) {

    throw new Error(
      "تصویر Sentinel-2 بعد از تاریخ انتخاب‌شده پیدا نشد."
    );
  }


  const statistics =
    await calculateDnbrStatistics(
      token,
      geometry,
      before.date,
      after.date
    );


  const burned =
    parseBurnedArea(
      statistics
    );


  const falseColor =
    await getFalseColor(
      token,
      geometry,
      after.date
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
      before.date,

    after_date:
      after.date,

    dnbr_threshold:
      BURN_THRESHOLD,

    burned_area: {

      total_ha:
        Number(
          burned.burnedAreaHa.toFixed(3)
        ),

      inside_fars_ha:
        Number(
          burned.burnedAreaHa.toFixed(3)
        ),

      inside_protected_areas_ha:
        regionType === "protected"
          ? Number(
              burned.burnedAreaHa.toFixed(3)
            )
          : 0,

      inside_hunting_banned_ha:
        regionType === "hunting"
          ? Number(
              burned.burnedAreaHa.toFixed(3)
            )
          : 0

    },

    burned_pixels:
      burned.burnedPixels,

    pixel_area_ha:
      burned.pixelAreaHa,

    false_color_url:
      falseColor.dataUrl,

    false_color_bounds:
      falseColor.bounds

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
          status: 204,

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
      url.pathname !==
      "/calculate"
    ) {

      return jsonResponse(
        {
          status:
            "OK",

          message:
            "FARS FIRE IMPACT API"
        },

        200,

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
            "خطای نامشخص"
        },

        400,

        origin
      );

    }

  }

};
