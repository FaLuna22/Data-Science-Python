"""Paso 1: la malla de la puna del sur andino a 500 m (malla MODIS).

Para cada píxel de 500 m (21,5 ha) calcula:
- distrito (INEI) y departamento,
- altitud media (Copernicus DEM GLO-90),
- fracción de cada cobertura de ESA WorldCover 2021 (10 m, leído a ~80 m),
- máscara de **puna**: ≥ 3 800 m y al menos la mitad del píxel con pajonal, matorral,
  humedal (bofedal) o musgo/liquen. Es la vegetación que pastan alpacas, llamas y ovinos.
Escribe datos/malla.npz y salidas/malla_resumen.json
"""
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject

from comun import (BBOX, COLS, DATOS, DEPARTAMENTOS, DISTRITOS, FILAS, HA_PIX, SINU, TRANSFORM,
                   buscar, firmar, guardar_json)

FORMA = (FILAS, COLS)
CLASES = {10: "arbol", 20: "matorral", 30: "pastizal", 40: "cultivo", 50: "urbano", 60: "desnudo",
          70: "nieve", 80: "agua", 90: "humedal", 100: "musgo"}
COTA_PUNA = 3800

# 1. Distritos del sur andino ------------------------------------------------------------------
dist = gpd.read_file(DISTRITOS)
dist = dist[dist.IDDPTO.isin(DEPARTAMENTOS) & dist.geometry.notna()].copy()   # Amantaní viene sin polígono
dist["ubigeo"] = dist.IDDIST.astype(int)
ubigeo = rasterize(zip(dist.to_crs(SINU).geometry, dist.ubigeo), out_shape=FORMA,
                   transform=TRANSFORM, fill=0, dtype="int32")
assert ubigeo[0].max() == 0 and ubigeo[-1].max() == 0 and ubigeo[:, 0].max() == 0 and ubigeo[:, -1].max() == 0, \
    "el recorte corta algún distrito: ampliar FILAS/COLS en comun.py"
print("Distritos:", len(dist), "· píxeles en el sur andino:", int((ubigeo > 0).sum()))


# 2. Altitud media: Copernicus DEM a 90 m promediado a 500 m ------------------------------------
def a_malla(origen, src_transform, src_crs, resampling, nodata=None):
    destino = np.full(FORMA, np.nan, dtype="float32")
    reproject(origen.astype("float32"), destino, src_transform=src_transform, src_crs=src_crs,
              src_nodata=nodata, dst_transform=TRANSFORM, dst_crs=SINU, dst_nodata=np.nan,
              resampling=resampling)
    return destino


def leer_dem(it):
    with rasterio.open(firmar(it, "data")) as s:
        return s.read(1), s.transform, s.crs, s.nodata


cota = np.full(FORMA, np.nan, dtype="float32")
dems = buscar("cop-dem-glo-90", bbox=BBOX)
with ThreadPoolExecutor(8) as ex:
    for a, tr, crs, nd in ex.map(leer_dem, dems):
        parte = a_malla(a, tr, crs, Resampling.average, nd)
        cota = np.where(np.isnan(cota), parte, cota)
print("DEM:", len(dems), "tiles · cota máx", np.nanmax(cota))

# 3. Fracciones de WorldCover ------------------------------------------------------------------
fraccion = {n: np.zeros(FORMA, dtype="float32") for n in CLASES.values()}
cubierto = np.zeros(FORMA, dtype="float32")


def leer_wc(it):
    with rasterio.open(firmar(it, "map")) as s:
        f = 8                                        # 10 m → 80 m con las vistas previas del COG
        a = s.read(1, out_shape=(s.height // f, s.width // f), resampling=Resampling.nearest)
        return a, s.transform * s.transform.scale(f, f), s.crs


wcs = buscar("esa-worldcover", bbox=BBOX)
wcs = [it for it in wcs if "2021" in it["id"]]
with ThreadPoolExecutor(4) as ex:
    for a, tr, crs in ex.map(leer_wc, wcs):
        valido = a > 0
        cub = a_malla(valido, tr, crs, Resampling.average)
        nuevo = np.nan_to_num(cub) > 0
        for codigo, nombre in CLASES.items():
            fr = np.nan_to_num(a_malla(a == codigo, tr, crs, Resampling.average))
            fraccion[nombre] = np.where(nuevo & (cubierto == 0), fr, fraccion[nombre])
        cubierto = np.where(nuevo & (cubierto == 0), np.nan_to_num(cub), cubierto)
print("WorldCover:", len(wcs), "tiles")

# 4. Máscara de puna y coordenadas de cada píxel -----------------------------------------------
forraje = fraccion["pastizal"] + fraccion["matorral"] + fraccion["humedal"] + fraccion["musgo"]
puna = (ubigeo > 0) & (cota >= COTA_PUNA) & (forraje >= 0.5)
filas, cols = np.indices(FORMA)
x, y = TRANSFORM * (cols + 0.5, filas + 0.5)
lon, lat = Transformer.from_crs(SINU, 4326, always_xy=True).transform(x, y)

np.savez_compressed(DATOS / "malla.npz", ubigeo=ubigeo, cota=cota, puna=puna, forraje=forraje,
                    lon=lon.astype("float32"), lat=lat.astype("float32"),
                    **{f"wc_{k}": v for k, v in fraccion.items()})

dpto = ubigeo // 10000
resumen = {"pixeles_puna": int(puna.sum()), "ha_puna": round(float(puna.sum() * HA_PIX)),
           "ha_bofedal_en_puna": round(float((fraccion["humedal"] * puna).sum() * HA_PIX)),
           "cota_puna_m": COTA_PUNA,
           "por_departamento": {DEPARTAMENTOS[f"{d:02d}"]: round(float((puna & (dpto == d)).sum() * HA_PIX))
                                for d in sorted(set(dpto[ubigeo > 0]))}}
guardar_json("malla_resumen.json", resumen)
print(resumen)
