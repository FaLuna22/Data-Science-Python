"""Paso 7: validación con focos VIIRS de NASA FIRMS (S-NPP, NOAA-20, NOAA-21).

- Baja los CSV públicos de 7 días para Sudamérica (sin clave) y guarda los focos de Chichas
- Zona de fuego = focos con un buffer de 750 m (dos píxeles VIIRS de 375 m)
- dNBR "sembrado con focos": hectáreas quemadas DENTRO de la zona, frente a cada fecha
  posterior con Sentinel-2, y cuánto de la zona se ve sin nubes
- Cruza los parches del paso 4 con los focos
Escribe salidas/focos_firms_chichas.csv y salidas/firms.json
"""
import io, json
import numpy as np
import pandas as pd
import geopandas as gpd
import requests, rasterio
from rasterio.mask import mask
from rasterio.features import rasterize
from shapely.geometry import shape

FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/{0}/csv/{1}_VIIRS_C2_South_America_7d.csv"
SATS = {"S-NPP": ("suomi-npp-viirs-c2", "SUOMI"), "NOAA-20": ("noaa-20-viirs-c2", "J1"),
        "NOAA-21": ("noaa-21-viirs-c2", "J2")}
B = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/18/L/YH/2026"
PRE = "9/S2C_18LYH_20260915_0_L2A"
POSTS = {"20261017": "10/S2A_18LYH_20261017_0_L2A", "20261018": "10/S2C_18LYH_20261018_0_L2A",
         "20261020": "10/S2A_18LYH_20261020_1_L2A", "20261020b": "10/S2B_18LYH_20261020_0_L2A",
         "20261023": "10/S2B_18LYH_20261023_0_L2A"}
MALAS = [0, 1, 3, 6, 8, 9, 10, 11]
BUFFER = 750
HA = 0.04

dist = gpd.read_file("chichas.geojson")
W, S, E, N = dist.total_bounds

# 1. Focos ------------------------------------------------------------------------------
partes = []
for sat, (carpeta, pref) in SATS.items():
    df = pd.read_csv(io.StringIO(requests.get(FIRMS.format(carpeta, pref), timeout=180).text))
    df["sat"] = sat
    partes.append(df)
todos = pd.concat(partes)
ventana = (todos.acq_date.min(), todos.acq_date.max())
f = todos[todos.latitude.between(S - .03, N + .03) & todos.longitude.between(W - .03, E + .03)].copy()
utc = pd.to_datetime(f.acq_date + " " + f.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M")
f["hora_lima"] = (utc - pd.Timedelta(hours=5)).dt.strftime("%Y-%m-%d %H:%M")
g = gpd.GeoDataFrame(f, geometry=gpd.points_from_xy(f.longitude, f.latitude), crs=4326)
utm = dist.estimate_utm_crs()
g_utm, d_utm = g.to_crs(utm), dist.to_crs(utm)
g["en_distrito"] = g_utm.within(d_utm.buffer(1000).union_all()).values   # límite simplificado: 1 km de holgura
g = g[g.en_distrito]
g_utm = g.to_crs(utm)
g.drop(columns="geometry").to_csv("salidas/focos_firms_chichas.csv", index=False)
print(f"{len(g)} focos en Chichas · ventana FIRMS {ventana}")

zona = g_utm.buffer(BUFFER).union_all()

# 2. dNBR dentro de la zona de fuego -------------------------------------------------------
def leer(p):
    out = []
    for b in ("B8A", "B12", "SCL"):
        with rasterio.open(f"{B}/{p}/{b}.tif") as s:
            a, tr = mask(s, dist.to_crs(s.crs).geometry, crop=True, nodata=0, filled=True)
            out.append(a[0]); crs = s.crs
    n = (out[0].astype("f4") - out[1]) / (out[0].astype("f4") + out[1] + 1e-6)
    n[np.isin(out[2], MALAS)] = np.nan
    return n, tr, crs

pre, TR, CRS = leer(PRE)
zona_px = rasterize([gpd.GeoSeries([zona], crs=utm).to_crs(CRS).iloc[0]], out_shape=pre.shape, transform=TR).astype(bool)
dentro_dist = rasterize([d_utm.to_crs(CRS).geometry.iloc[0]], out_shape=pre.shape, transform=TR).astype(bool)
zona_px &= dentro_dist
ha_zona = float(zona_px.sum() * HA)
por_fecha, q, vis = [], {}, {}
for fecha, p in POSTS.items():
    post, _, _ = leer(p)
    d = pre - post
    ok = np.isfinite(d)
    q[fecha] = ok & (d >= .27)
    vis[fecha] = ok
    por_fecha.append(dict(
        fecha=fecha[:8], escena=p.split("/")[1],
        zona_visible_pct=round(float(100 * (ok & zona_px).sum() / zona_px.sum()), 1),
        ha_zona_027=round(float((q[fecha] & zona_px).sum() * HA), 1),
        ha_zona_044=round(float((ok & (d >= .44) & zona_px).sum() * HA), 1),
        ha_fuera_027=round(float((q[fecha] & ~zona_px & dentro_dist).sum() * HA), 1),
        dnbr_medio_zona=round(float(np.nanmean(d[zona_px])), 3)))
    print(por_fecha[-1])
pers = q["20261017"] & q["20261018"] & zona_px
q20 = q["20261020"] & zona_px
res_pers = dict(zona_17_y_18=round(float(pers.sum() * HA), 1),
                # mismo día, otro satélite: ¿coinciden?
                zona_20_ambos_s2=round(float((q20 & q["20261020b"]).sum() * HA), 1),
                zona_20_visible_en_s2b=round(float((q20 & vis["20261020b"]).sum() * HA), 1),
                # ¿se desvanece la cicatriz? solo donde el 23 oct se ve el suelo
                zona_20_visible_23=round(float((q20 & vis["20261023"]).sum() * HA), 1),
                zona_20_sigue_23=round(float((q20 & q["20261023"]).sum() * HA), 1))

# 3. Parches con y sin focos ---------------------------------------------------------------
dd = json.load(open("salidas/dashboard_data.json"))
for pch in dd["parches"]:
    geom = gpd.GeoSeries([shape(pch["geom"])], crs=4326).to_crs(utm).iloc[0]
    dmin = float(g_utm.distance(geom).min())
    pch["dist_foco_m"] = round(dmin)
    pch["con_foco"] = dmin <= BUFFER
con = [p for p in dd["parches"] if p["con_foco"]]

# 4. Pasadas ---------------------------------------------------------------------------------
pas = (g.groupby(["hora_lima", "sat"])
        .agg(focos=("frp", "size"), frp_total=("frp", "sum"), frp_max=("frp", "max"),
             alta=("confidence", lambda c: int((c == "h").sum() + (c == "high").sum())))
        .reset_index().sort_values("hora_lima"))
out = dict(
    ventana=ventana, n_focos=int(len(g)), buffer_m=BUFFER, ha_zona=round(ha_zona, 1),
    primer_foco=g.hora_lima.min(), ultimo_foco=g.hora_lima.max(),
    focos_por_sat=g.sat.value_counts().to_dict(),
    focos_por_dia=g.acq_date.value_counts().sort_index().to_dict(),
    frp_total=round(float(g.frp.sum()), 1), frp_max=round(float(g.frp.max()), 1),
    pasadas=[{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in pas.to_dict("records")],
    por_fecha=por_fecha, persistencia=res_pers,
    parches=[dict(id=p["id"], con_foco=p["con_foco"], dist_foco_m=p["dist_foco_m"]) for p in dd["parches"]],
    ha_parches_con_foco=round(sum(p["ha"] for p in con), 1),
    ha_parches_sin_foco=round(sum(p["ha"] for p in dd["parches"] if not p["con_foco"]), 1),
    zona_geom=json.loads(gpd.GeoSeries([zona], crs=utm).to_crs(4326).simplify(0.0002).to_json())["features"][0]["geometry"],
    focos=[dict(lat=r.latitude, lon=r.longitude, sat=r.sat, hora=r.hora_lima, frp=r.frp,
                conf=r.confidence, dn=r.daynight) for r in g.itertuples()],
)
json.dump(out, open("salidas/firms.json", "w"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ("focos", "zona_geom", "pasadas", "parches")}, indent=1, default=str))
