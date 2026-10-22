"""Paso 8: tres fuentes de Microsoft Planetary Computer (STAC, sin clave) para validar.

- MOD14A1 / MYD14A1 (MODIS Terra y Aqua, 1 km, diario): ¿hubo fuego en el distrito entre
  el 1 de setiembre y la víspera de la ventana de FIRMS? FireMask 7-9 = fuego.
- MCD64A1 (MODIS, 500 m, mensual, 2001 en adelante): ¿cuánto se quema Chichas cada año y
  dónde se ha quemado antes?
- Landsat 8/9 Collection 2 L2 (30 m): un segundo sensor para el NBR del parche 1 y un dNBR
  independiente con la escena más reciente publicada.
Escribe salidas/planetary.json
"""
import base64, io, json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache
from urllib.parse import urlparse

import numpy as np
import requests, rasterio, geopandas as gpd
from rasterio.mask import mask
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, reproject
from rasterio.transform import from_bounds, from_origin
from rasterio.features import geometry_mask
from shapely.geometry import shape, mapping
from pyproj import Transformer
from PIL import Image

API = "https://planetarycomputer.microsoft.com/api/stac/v1"
SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
dist = gpd.read_file("chichas.geojson")
BBOX = [float(v) for v in dist.total_bounds]
D = json.load(open("salidas/dashboard_data.json"))
parches = D["parches"]


def buscar(coleccion, fechas, **extra):
    cuerpo = {"collections": [coleccion], "bbox": BBOX, "datetime": fechas, "limit": 1000, **extra}
    feats, url = [], f"{API}/search"
    while url:
        r = requests.post(url, json=cuerpo, timeout=120).json()
        feats += r["features"]
        sig = [l for l in r.get("links", []) if l["rel"] == "next"]
        url, cuerpo = (sig[0]["href"], sig[0].get("body", cuerpo)) if sig else (None, None)
    return feats


@lru_cache
def token(cuenta, contenedor):
    return requests.get(f"{SAS}/{cuenta}/{contenedor}", timeout=60).json()["token"]


def firmar(item, asset):
    """Token SAS del contenedor de Azure (el de la colección puede ser de otro contenedor)."""
    href = item["assets"][asset]["href"]
    u = urlparse(href)
    return href + "?" + token(u.netloc.split(".")[0], u.path.split("/")[1])


def recorte(url, geom=dist, all_touched=True, nodata=0):
    with rasterio.open(url) as s:
        a, tr = mask(s, geom.to_crs(s.crs).geometry, crop=True, nodata=nodata, filled=True, all_touched=all_touched)
        return a, tr, s.crs


# 1. MODIS 14A1: fuego diario a 1 km -----------------------------------------------------------
desde, hasta = date(2026, 9, 1), date(2026, 10, 21)
items14 = [it for it in buscar("modis-14A1-061", f"{desde}/{hasta}") if ".h10v10." in it["id"]]
dias = {}


def leer14(it):
    a, tr, crs = recorte(firmar(it, "FireMask"), nodata=0)
    frp, _, _ = recorte(firmar(it, "MaxFRP"), nodata=0)
    ini = date.fromisoformat(it["properties"]["start_datetime"][:10])
    plat = "Terra" if it["id"].startswith("MOD") else "Aqua"
    dentro = ~geometry_mask(dist.to_crs(crs).geometry, a.shape[1:], tr, all_touched=True)
    out = []
    for k in range(a.shape[0]):
        b = a[k]
        fuego = dentro & (b >= 7)
        filas, cols = np.nonzero(fuego)
        pts = []
        for f, c in zip(filas, cols):
            x, y = rasterio.transform.xy(tr, f, c)
            lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x, y)
            pts.append(dict(lon=round(lon, 4), lat=round(lat, 4), conf=int(b[f, c]), frp=round(float(frp[k, f, c]) * 0.1, 1)))
        out.append(dict(fecha=str(ini + timedelta(days=k)), plat=plat, fuego=int(fuego.sum()),
                        nubes=round(float(100 * (dentro & (b == 4)).sum() / dentro.sum()), 1),
                        sin_dato=round(float(100 * (dentro & (b <= 2)).sum() / dentro.sum()), 1), pixeles=pts))
    return out


with ThreadPoolExecutor(8) as ex:
    for lista in ex.map(leer14, items14):
        for d in lista:
            dias.setdefault(d["fecha"], {})[d["plat"]] = d
modis_diario = []
for f in sorted(d for d in dias if d >= str(desde)):
    t, a = dias[f].get("Terra"), dias[f].get("Aqua")
    modis_diario.append(dict(fecha=f, terra=t["fuego"] if t else None, aqua=a["fuego"] if a else None,
                             nubes_terra=t["nubes"] if t else None, nubes_aqua=a["nubes"] if a else None,
                             pixeles=(t["pixeles"] if t else []) + (a["pixeles"] if a else [])))
ultimo14 = max(f for f in dias)
print("MODIS 14A1:", len(items14), "ítems ·", modis_diario[0]["fecha"], "a", ultimo14,
      "· días con fuego:", [d["fecha"] for d in modis_diario if (d["terra"] or 0) + (d["aqua"] or 0)])

# 2. MCD64A1: área quemada mensual 2001-2026 ----------------------------------------------------
TILE = ".h10v10."                               # Chichas cae entero en el tile MODIS h10v10
items64 = [it for it in buscar("modis-64A1-061", "2000-11-01/2026-12-31") if TILE in it["id"]]
PIX64 = 463.3127 ** 2 / 1e4                      # ha por píxel de 500 m (sinusoidal)


def leer64(it):
    a, tr, crs = recorte(firmar(it, "Burn_Date"), nodata=-1, all_touched=False)
    return it["properties"]["start_datetime"][:7], a[0], tr, crs


with ThreadPoolExecutor(12) as ex:
    meses64 = sorted(ex.map(leer64, items64), key=lambda t: t[0])
forma64 = meses64[0][1].shape
assert all(m[1].shape == forma64 for m in meses64)
TR64, CRS64 = meses64[0][2], meses64[0][3]
dentro64 = ~geometry_mask(dist.to_crs(CRS64).geometry, forma64, TR64)
anios64 = sorted({int(m[0][:4]) for m in meses64})
ha_anio = {a: 0.0 for a in anios64}
ha_mes = [0.0] * 12
quem_anio = {a: np.zeros(forma64, bool) for a in anios64}
for ym, a, _, _ in meses64:
    q = dentro64 & (a > 0)
    ha_anio[int(ym[:4])] += float(q.sum() * PIX64)
    ha_mes[int(ym[5:7]) - 1] += float(q.sum() * PIX64)
    quem_anio[int(ym[:4])] |= q
veces = np.sum([quem_anio[a] for a in anios64], axis=0)
print("MCD64A1:", len(meses64), "meses ·", meses64[0][0], "a", meses64[-1][0], "· ha totales",
      round(sum(ha_anio.values())), "· píxeles quemados alguna vez", int((veces > 0).sum()))

# años en que se quemó el lugar de cada parche (píxel de 500 m que contiene su centro)
def anios_en(lon, lat):
    x, y = Transformer.from_crs(4326, CRS64, always_xy=True).transform(lon, lat)
    f, c = rasterio.transform.rowcol(TR64, x, y)
    return [a for a in anios64 if quem_anio[a][f, c]] if 0 <= f < forma64[0] and 0 <= c < forma64[1] else []


hist_parches = [dict(id=p["id"], anios=anios_en(p["lon"], p["lat"])) for p in parches]

# capa del mapa: número de años quemados, en la grilla del dashboard
(Sb, Wb), (Nb, Eb) = D["bounds"]
RES = 0.0002
ancho, alto = int((Eb - Wb) / RES), int((Nb - Sb) / RES)
T4 = from_bounds(Wb, Sb, Eb, Nb, ancho, alto)
v4 = np.zeros((alto, ancho), "uint8")
reproject(np.where(dentro64, veces, 0).astype("uint8"), v4, src_transform=TR64, src_crs=CRS64,
          dst_transform=T4, dst_crs="EPSG:4326", resampling=Resampling.nearest, src_nodata=255)
COL_VECES = ["#fed976", "#fd8d3c", "#e31a1c", "#800026"]
rgba = np.zeros((alto, ancho, 4), "uint8")
for k, c in enumerate(COL_VECES, 1):
    sel = (v4 >= k) if k == len(COL_VECES) else (v4 == k)
    rgba[sel] = [int(c[i:i + 2], 16) for i in (1, 3, 5)] + [210]
b = io.BytesIO(); Image.fromarray(rgba).save(b, "PNG", optimize=True)
capa_mcd64 = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

# 3. Landsat 8/9 -------------------------------------------------------------------------------
itemsL = buscar("landsat-c2-l2", "2026-08-01/2026-10-31",
                query={"platform": {"in": ["landsat-8", "landsat-9"]}})
porfecha = {}
for it in itemsL:
    porfecha.setdefault(it["properties"]["datetime"][:10], []).append(it)
utm = dist.to_crs(32718)
xmin, ymin, xmax, ymax = utm.total_bounds
TRL = from_origin(xmin, ymax, 30, 30)
FL = (int(np.ceil((ymax - ymin) / 30)), int(np.ceil((xmax - xmin) / 30)))
dentroL = ~geometry_mask(utm.geometry, FL, TRL)
p1 = gpd.GeoSeries([shape(parches[0]["geom"])], crs=4326).to_crs(32718).iloc[0]
m_p1 = ~geometry_mask([mapping(p1)], FL, TRL, all_touched=True)
anillo = p1.buffer(500).difference(p1.buffer(160))
m_an = ~geometry_mask([mapping(anillo)], FL, TRL)
m_parches = ~geometry_mask([mapping(gpd.GeoSeries([shape(p["geom"])], crs=4326).to_crs(32718).iloc[0])
                            for p in parches], FL, TRL, all_touched=True)


def leer_banda(it, asset, resamp=Resampling.nearest):
    with rasterio.open(firmar(it, asset)) as s:
        with WarpedVRT(s, crs="EPSG:32718", transform=TRL, width=FL[1], height=FL[0], resampling=resamp, nodata=0) as v:
            return v.read(1)


def nbr_landsat(fecha):
    nir = np.zeros(FL, "f4"); sw = np.zeros(FL, "f4"); qa = np.zeros(FL, "uint16")
    for it in porfecha[fecha]:                  # filas 070 y 071 del mismo paso: se mosaican
        a, b, q = leer_banda(it, "nir08"), leer_banda(it, "swir22"), leer_banda(it, "qa_pixel")
        vacio = qa == 0
        nir[vacio], sw[vacio], qa[vacio] = a[vacio], b[vacio], q[vacio]
    # QA_PIXEL: bits 1 nube dilatada, 2 cirro, 3 nube, 4 sombra, 5 nieve, 7 agua
    ok = (qa > 0) & ((qa & (1 << 1 | 1 << 2 | 1 << 3 | 1 << 4 | 1 << 5 | 1 << 7)) == 0)
    r_nir, r_sw = nir * 2.75e-5 - 0.2, sw * 2.75e-5 - 0.2
    v = (r_nir - r_sw) / (r_nir + r_sw + 1e-6)
    v[~ok | (nir == 0)] = np.nan
    return fecha, v, porfecha[fecha][0]["properties"]["platform"]


with ThreadPoolExecutor(4) as ex:
    nbrL = {f: (v, plat) for f, v, plat in ex.map(nbr_landsat, sorted(porfecha))}
serieL = []
for f, (v, plat) in nbrL.items():
    claro = np.isfinite(v)
    serieL.append(dict(fecha=f.replace("-", ""), plat=plat,
                       nubes_distrito=round(float(100 * (1 - claro[dentroL].mean())), 1),
                       nubes_parche=round(float(100 * (1 - claro[m_p1].mean())), 1),
                       nbr_parche=round(float(np.nanmean(v[m_p1])), 4) if claro[m_p1].mean() > 0.5 else None,
                       nbr_control=round(float(np.nanmean(v[m_an])), 4) if claro[m_an].mean() > 0.5 else None))
limpias = [s for s in serieL if s["nubes_distrito"] < 15]
preL = max((s for s in limpias if s["fecha"] <= "20260920"), key=lambda s: s["fecha"])
postL = max(limpias, key=lambda s: s["fecha"])
dL = nbrL[f"{preL['fecha'][:4]}-{preL['fecha'][4:6]}-{preL['fecha'][6:]}"][0] - \
     nbrL[f"{postL['fecha'][:4]}-{postL['fecha'][4:6]}-{postL['fecha'][6:]}"][0]
dL = dL - np.nanmedian(dL[dentroL])
okL = np.isfinite(dL) & dentroL
HAL = 0.09
landsat = dict(pre=preL["fecha"], post=postL["fecha"], serie=serieL,
               ha_027=round(float((okL & (dL >= 0.27)).sum() * HAL), 1),
               ha_027_parches=round(float((okL & m_parches & (dL >= 0.27)).sum() * HAL), 1),
               dnbr_parches=round(float(np.nanmean(dL[okL & m_parches])), 3),
               dnbr_resto=round(float(np.nanmean(dL[okL & ~m_parches])), 3),
               posterior_al_fuego=postL["fecha"] >= "20261019")
print("Landsat:", len(serieL), "fechas · par", preL["fecha"], "->", postL["fecha"], json.dumps(
    {k: v for k, v in landsat.items() if k != "serie"}))

out = dict(
    modis14=dict(diario=modis_diario, ultimo=ultimo14, items=len(items14),
                 dias_fuego=[d["fecha"] for d in modis_diario if (d["terra"] or 0) + (d["aqua"] or 0)]),
    mcd64=dict(anios=anios64, ha_anio={a: round(v, 1) for a, v in ha_anio.items()}, ha_mes=[round(v, 1) for v in ha_mes],
               primer_mes=meses64[0][0], ultimo_mes=meses64[-1][0],
               ha_alguna_vez=round(float((veces > 0).sum() * PIX64), 1),
               ha_2_o_mas=round(float((veces >= 2).sum() * PIX64), 1), max_veces=int(veces.max()),
               parches=hist_parches, capa=capa_mcd64, colores=COL_VECES),
    landsat=landsat,
)
json.dump(out, open("salidas/planetary.json", "w"), ensure_ascii=False)
print("listo")
