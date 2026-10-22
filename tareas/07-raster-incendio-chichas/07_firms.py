"""Paso 7: focos de calor de NASA FIRMS y su cruce con el área quemada de Sentinel-2.

- Focos NRT (VIIRS S-NPP, NOAA-20, NOAA-21 y MODIS) de los archivos públicos de 7 días,
  que no piden clave. La ventana de 7 días se mueve, así que cada corrida se suma a
  salidas/firms_nrt.csv sin borrar lo anterior. Con la variable FIRMS_MAP_KEY (clave gratis
  en https://firms.modaps.eosdis.nasa.gov/api/map_key/) baja además todo set-oct con la API.
- Histórico: archivos anuales por país (Perú), MODIS 2001-2025 y VIIRS S-NPP 2012-2025.
- Cruce: dNBR corregido por offset frente al 15 set en las imágenes del 17, 18 y 20 oct,
  y la huella de cada foco (medio píxel: 187 m VIIRS, 500 m MODIS).
Escribe salidas/firms.json, salidas/firms_nrt.csv y salidas/firms_historico_distrito.csv
"""
import io, json, os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests, rasterio, geopandas as gpd
from rasterio.mask import mask
from rasterio.transform import rowcol
from scipy.ndimage import binary_dilation, distance_transform_edt, label
from shapely.geometry import shape
from pyproj import Transformer

FIRMS = "https://firms.modaps.eosdis.nasa.gov"
S2 = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/L/YH/2026"
PRE = "9/S2C_18LYH_20260915_0_L2A"
POSTS = {"20261017": "10/S2A_18LYH_20261017_0_L2A", "20261018": "10/S2C_18LYH_20261018_0_L2A",
         "20261020": "10/S2A_18LYH_20261020_1_L2A"}
# hora de paso de Sentinel-2 (UTC), del STAC de cada escena
PASO_S2 = {"20261015": "1507", "20261017": "1507", "20261018": "1517", "20261020": "1517"}
NRT = {"VIIRS S-NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2", "VIIRS NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2",
       "VIIRS NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2", "MODIS": "modis-c6.1/csv/MODIS_C6_1"}
API_FUENTES = {"VIIRS S-NPP": "VIIRS_SNPP_NRT", "VIIRS NOAA-20": "VIIRS_NOAA20_NRT",
               "VIIRS NOAA-21": "VIIRS_NOAA21_NRT", "MODIS": "MODIS_NRT"}
HISTORICO = {"MODIS": ("modis", range(2001, 2026)), "VIIRS S-NPP": ("viirs-snpp", range(2012, 2026))}
MALAS = [0, 1, 3, 6, 8, 9, 10, 11]
HA = 0.04
BUF = 0.15                               # grados alrededor del distrito para ver focos vecinos

dist = gpd.read_file("chichas.geojson")
poly = dist.geometry.iloc[0]
W, S, E, N = dist.total_bounds
CAJA = (W - BUF, S - BUF, E + BUF, N + BUF)


def en_caja(df):
    return df[df.latitude.between(CAJA[1], CAJA[3]) & df.longitude.between(CAJA[0], CAJA[2])].copy()


def en_distrito(df):
    pts = gpd.GeoSeries(gpd.points_from_xy(df.longitude, df.latitude), crs=4326)
    return pts.within(poly).values


# 1. Focos NRT ------------------------------------------------------------------------------
def nrt_7d(sensor):
    r = requests.get(f"{FIRMS}/data/active_fire/{NRT[sensor]}_South_America_7d.csv", timeout=180)
    r.raise_for_status()
    todo = pd.read_csv(io.StringIO(r.text))
    df = en_caja(todo)
    df["sensor"] = sensor
    return df, todo.acq_date.min(), todo.acq_date.max()


def nrt_api(sensor, key, desde=date(2026, 9, 1), hasta=date(2026, 10, 21)):
    """API de área: máximo 10 días por consulta."""
    partes, d = [], desde
    while d <= hasta:
        dias = min(10, (hasta - d).days + 1)
        url = f"{FIRMS}/api/area/csv/{key}/{API_FUENTES[sensor]}/{','.join(f'{c:.3f}' for c in CAJA)}/{dias}/{d}"
        partes.append(pd.read_csv(io.StringIO(requests.get(url, timeout=180).text)))
        d += timedelta(days=dias)
    df = pd.concat(partes)
    df["sensor"] = sensor
    return df, str(desde), str(hasta)


key = os.environ.get("FIRMS_MAP_KEY")
with ThreadPoolExecutor(4) as ex:
    nuevos = list(ex.map(lambda s: nrt_api(s, key) if key else nrt_7d(s), NRT))
nrt = pd.concat([n[0] for n in nuevos], ignore_index=True)
# ventana cubierta = fechas de los archivos bajados (no solo de los focos), sumada a corridas previas
ventana = [min(n[1] for n in nuevos), max(n[2] for n in nuevos)]
if os.path.exists("salidas/firms.json"):
    previa = json.load(open("salidas/firms.json"))["ventana"]
    ventana = [min(ventana[0], previa[0]), max(ventana[1], previa[1])]
if os.path.exists("salidas/firms_nrt.csv"):
    nrt = pd.concat([pd.read_csv("salidas/firms_nrt.csv", dtype={"acq_time": str}), nrt], ignore_index=True)
nrt["acq_time"] = nrt.acq_time.astype(str).str.zfill(4)
nrt["confidence"] = nrt.confidence.astype(str)
nrt = nrt.drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "sensor"]).sort_values(["acq_date", "acq_time"])
cols = ["latitude", "longitude", "acq_date", "acq_time", "sensor", "satellite", "confidence", "frp", "daynight",
        "scan", "track", "bright_ti4", "brightness", "version"]
nrt = nrt[[c for c in cols if c in nrt]]
nrt.to_csv("salidas/firms_nrt.csv", index=False)
nrt["en_distrito"] = en_distrito(nrt)
print("focos NRT en la caja:", len(nrt), "· en el distrito:", int(nrt.en_distrito.sum()),
      "· ventana", ventana)

# 2. dNBR corregido 15 set -> 17, 18 y 20 oct (misma receta que 05_persistencia.py) -----------
def nbr(p):
    out = []
    for b in ("B8A", "B12", "SCL"):
        with rasterio.open(f"{S2}/{p}/{b}.tif") as s:
            a, tr = mask(s, dist.to_crs(s.crs).geometry, crop=True, nodata=0, filled=True)
            out.append(a[0]); crs = s.crs
    v = (out[0].astype("f4") - out[1]) / (out[0].astype("f4") + out[1] + 1e-6)
    v[np.isin(out[2], MALAS)] = np.nan
    return v, tr, crs


with ThreadPoolExecutor(4) as ex:
    res = dict(zip(["pre", *POSTS], ex.map(nbr, [PRE, *POSTS.values()])))
pre, TR, CRS = res.pop("pre")
quem, valid = {}, {}
for f, (v, _, _) in res.items():
    d = pre - v
    d = d - np.nanmedian(d)
    valid[f] = np.isfinite(d)
    quem[f] = valid[f] & (d >= 0.27)
# robusto = lejos (> 60 m) de huecos internos de la máscara, como en 03_control_nieve.py
cerca = {}
for f in quem:
    hueco = ~valid[f] & binary_dilation(valid[f], iterations=3)
    cerca[f] = binary_dilation(hueco, iterations=3)
rob = {f: quem[f] & ~cerca[f] for f in quem}
union = rob["20261017"] | rob["20261018"] | rob["20261020"]

# 3. Huella de cada foco en la grilla de 20 m ---------------------------------------------
a_utm = Transformer.from_crs(4326, CRS, always_xy=True)
x, y = a_utm.transform(nrt.longitude.values, nrt.latitude.values)
fila, col = rowcol(TR, x, y)
fila, col = np.asarray(fila), np.asarray(col)
dentro_grilla = (fila >= 0) & (fila < pre.shape[0]) & (col >= 0) & (col < pre.shape[1])
radio = np.where(nrt.sensor.str.startswith("VIIRS"), 187.5, 500.0)   # medio píxel nominal en nadir


def toca(m, i):
    """¿Algún píxel de la máscara m cae en la huella del foco i?"""
    if not dentro_grilla[i]:
        return False
    r = int(np.ceil(radio[i] / 20))
    f0, c0 = fila[i], col[i]
    sub = m[max(f0 - r, 0):f0 + r + 1, max(c0 - r, 0):c0 + r + 1]
    return bool(sub.any())


nrt["toca_17"] = [toca(rob["20261017"], i) for i in range(len(nrt))]
nrt["toca_18"] = [toca(rob["20261018"], i) for i in range(len(nrt))]
nrt["toca_20"] = [toca(rob["20261020"], i) for i in range(len(nrt))]
nrt["toca_alguna"] = nrt.toca_17 | nrt.toca_18 | nrt.toca_20
# ¿el foco es anterior o posterior al paso de Sentinel-2 del 17 oct?
nrt["momento"] = nrt.acq_date.str.replace("-", "") + nrt.acq_time
nrt["antes_s2_17"] = nrt.momento < "20261017" + PASO_S2["20261017"]

# Área quemada confirmada por focos: unión robusta 17/18/20 a <= 375 m de un foco VIIRS o
# 1 km de un foco MODIS (un píxel entero, por el error de geolocalización)
centros = np.zeros(pre.shape, bool)
ok = dentro_grilla & nrt.en_distrito.values
viirs = ok & nrt.sensor.str.startswith("VIIRS").values
centros[fila[viirs], col[viirs]] = True
d_viirs = distance_transform_edt(~centros) * 20 if centros.any() else np.full(pre.shape, np.inf)
centros_m = np.zeros(pre.shape, bool)
centros_m[fila[ok & ~viirs], col[ok & ~viirs]] = True
d_modis = distance_transform_edt(~centros_m) * 20 if centros_m.any() else np.full(pre.shape, np.inf)
cerca_foco = (d_viirs <= 375) | (d_modis <= 1000)
lab, n = label(union, structure=np.ones((3, 3)))
con_foco = np.unique(lab[union & cerca_foco])
confirmado = np.isin(lab, con_foco[con_foco > 0])          # parche entero si un foco lo toca

# 4. Parches del dashboard: focos por parche -----------------------------------------------
parches = json.load(open("salidas/dashboard_data.json"))["parches"]
pts = gpd.GeoSeries(gpd.points_from_xy(nrt.longitude, nrt.latitude), crs=4326).to_crs(CRS)
por_parche = []
for p in parches:
    g = gpd.GeoSeries([shape(p["geom"])], crs=4326).to_crs(CRS).iloc[0]
    m = (pts.distance(g) <= np.where(nrt.sensor.str.startswith("VIIRS"), 375, 1000)).values
    sub = nrt[m]
    por_parche.append(dict(id=p["id"], focos=int(len(sub)), focos_viirs=int(sub.sensor.str.startswith("VIIRS").sum()),
                           primero=(sub.acq_date.iloc[0] + " " + sub.acq_time.iloc[0]) if len(sub) else None,
                           ultimo=(sub.acq_date.iloc[-1] + " " + sub.acq_time.iloc[-1]) if len(sub) else None,
                           frp_max=round(float(sub.frp.max()), 1) if len(sub) else None))
print("parches con foco:", sum(p["focos"] > 0 for p in por_parche), "de", len(por_parche))

# 5. Histórico por país -------------------------------------------------------------------------
def anual(args):
    sensor, (carpeta, anio) = args
    r = requests.get(f"{FIRMS}/data/country/{carpeta}/{anio}/{carpeta}_{anio}_Peru.csv", timeout=300)
    if r.status_code != 200:
        return None
    df = en_caja(pd.read_csv(io.StringIO(r.text)))
    df["sensor"] = sensor
    return df


tareas = [(s, (c, a)) for s, (c, anios) in HISTORICO.items() for a in anios]
with ThreadPoolExecutor(8) as ex:
    hist = pd.concat([h for h in ex.map(anual, tareas) if h is not None], ignore_index=True)
hist = hist[en_distrito(hist)]
if "type" in hist:
    hist = hist[hist.type == 0]                        # 0 = presunto incendio de vegetación
hist[["latitude", "longitude", "acq_date", "acq_time", "sensor", "confidence", "frp", "daynight"]].to_csv(
    "salidas/firms_historico_distrito.csv", index=False)
hist["anio"] = hist.acq_date.str[:4].astype(int)
hist["mes"] = hist.acq_date.str[5:7].astype(int)
print("focos históricos en el distrito:", len(hist))
anios = list(range(2001, 2027))
nrt_d = nrt[nrt.en_distrito]
por_anio = {s: [int(((hist.sensor == s) & (hist.anio == a)).sum()) for a in anios] for s in HISTORICO}
por_mes = {s: [int(((hist.sensor == s) & (hist.mes == m)).sum()) for m in range(1, 13)] for s in HISTORICO}
# días con focos por temporada, y focos de oct 2026 aparte (no están en el archivo anual)
oct26 = {s: int((nrt_d.sensor == s).sum()) for s in nrt_d.sensor.unique()}

# 6. Salida ------------------------------------------------------------------------------------
pasadas = (nrt.groupby(["acq_date", "acq_time", "sensor", "daynight"])
           .agg(focos=("frp", "size"), frp=("frp", "sum"), en_distrito=("en_distrito", "sum"),
                toca=("toca_alguna", "sum")).reset_index())
out = dict(
    corte=str(date.today()), con_api=bool(key),
    ventana=ventana,
    paso_s2=PASO_S2,
    focos=[dict(lat=round(r.latitude, 5), lon=round(r.longitude, 5), fecha=r.acq_date, hora=r.acq_time,
                sensor=r.sensor, sat=str(r.satellite), conf=str(r.confidence), frp=float(r.frp), dn=r.daynight,
                dist=bool(r.en_distrito), t17=bool(r.toca_17), t18=bool(r.toca_18), t20=bool(r.toca_20),
                antes17=bool(r.antes_s2_17)) for r in nrt.itertuples()],
    pasadas=[dict(fecha=r.acq_date, hora=r.acq_time, sensor=r.sensor, dn=r.daynight, focos=int(r.focos),
                  frp=round(float(r.frp), 1), en_distrito=int(r.en_distrito), toca=int(r.toca)) for r in pasadas.itertuples()],
    resumen=dict(
        focos_caja=int(len(nrt)), focos_distrito=int(len(nrt_d)),
        focos_distrito_viirs=int(nrt_d.sensor.str.startswith("VIIRS").sum()),
        focos_distrito_toca=int(nrt_d.toca_alguna.sum()),
        focos_distrito_toca_17=int(nrt_d.toca_17.sum()),
        focos_antes_s2_17=int(nrt_d.antes_s2_17.sum()),
        focos_antes_s2_17_toca_17=int((nrt_d.antes_s2_17 & nrt_d.toca_17).sum()),
        focos_despues_s2_17=int((~nrt_d.antes_s2_17).sum()),
        focos_despues_s2_17_toca_18_20=int((~nrt_d.antes_s2_17 & (nrt_d.toca_18 | nrt_d.toca_20)).sum()),
        primer_foco=(nrt_d.acq_date.iloc[0] + " " + nrt_d.acq_time.iloc[0]) if len(nrt_d) else None,
        ultimo_foco=(nrt_d.acq_date.iloc[-1] + " " + nrt_d.acq_time.iloc[-1]) if len(nrt_d) else None,
        dias_con_foco=sorted(nrt_d.acq_date.unique().tolist()),
        frp_max=round(float(nrt_d.frp.max()), 1) if len(nrt_d) else None,
        ha_robusto={f: round(float(rob[f].sum() * HA), 1) for f in rob},
        ha_union_robusta=round(float(union.sum() * HA), 1),
        ha_union_cerca_foco=round(float((union & cerca_foco).sum() * HA), 1),
        ha_confirmadas=round(float(confirmado.sum() * HA), 1),
        ha_17_confirmadas=round(float((rob["20261017"] & confirmado).sum() * HA), 1)),
    por_parche=por_parche,
    historico=dict(anios=anios, por_anio=por_anio, meses=list(range(1, 13)), por_mes=por_mes,
                   oct_2026_nrt=oct26, total=int(len(hist)),
                   focos_oct=int((hist.mes == 10).sum()), focos_set_nov=int(hist.mes.isin([9, 10, 11]).sum()),
                   anio_max={s: anios[int(np.argmax(v))] for s, v in por_anio.items()}),
)
json.dump(out, open("salidas/firms.json", "w"), ensure_ascii=False)
print(json.dumps(out["resumen"], indent=1, ensure_ascii=False))
print(json.dumps({k: v for k, v in out["historico"].items() if k not in ("anios",)}, ensure_ascii=False))
