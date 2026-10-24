"""Paso 4: El Niño y la lluvia de la puna, 1981-2026.

- ONI de NOAA CPC (anomalía de temperatura del mar en Niño 3.4). Cada temporada de lluvias
  (diciembre del año Y a marzo de Y+1) se clasifica por su ONI de DEF.
- CHIRPS v3 (0,05°, mensual): lluvia acumulada de diciembre a marzo, que es cuando rebrota el
  pajonal, en cada píxel de puna. Anomalía en % frente a 1991-2020.
Escribe datos/lluvia_defm.npz, salidas/oni.csv y salidas/lluvia_por_temporada.csv
"""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.windows import from_bounds

from comun import DATOS, DEPARTAMENTOS, SALIDAS

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
CHIRPS = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/monthly/global/tifs/chirps-v3.0.{a}.{m:02d}.tif"
VENTANA = (-76.0, -19.0, -68.0, -11.0)
NORMAL = range(1991, 2021)


def clase_enso(oni):
    if oni >= 1.5:
        return "Niño fuerte"
    if oni >= 0.5:
        return "Niño"
    if oni <= -0.5:
        return "Niña"
    return "Neutro"


# 1. ONI -----------------------------------------------------------------------------------------
oni = pd.read_csv(StringIO(requests.get(ONI_URL, timeout=60).text), sep=r"\s+")
oni.to_csv(SALIDAS / "oni.csv", index=False)
djf = oni[oni.SEAS == "DJF"].set_index("YR").ANOM                  # DJF de Y+1 → temporada Y
print("ONI hasta:", oni.iloc[-1].SEAS, oni.iloc[-1].YR, oni.iloc[-1].ANOM)

# 2. CHIRPS: lluvia de diciembre a marzo -------------------------------------------------------
malla = np.load(DATOS / "malla.npz")
puna = malla["puna"].ravel()
lon, lat = malla["lon"].ravel()[puna], malla["lat"].ravel()[puna]
ubigeo = malla["ubigeo"].ravel()[puna]


def leer(am):
    a, m = am
    with rasterio.open("/vsicurl/" + CHIRPS.format(a=a, m=m)) as s:
        w = from_bounds(*VENTANA, s.transform)
        arr = s.read(1, window=w)
        tr = s.window_transform(w)
    fila = np.clip(((lat - tr.f) / tr.e).astype(int), 0, arr.shape[0] - 1)
    col = np.clip(((lon - tr.c) / tr.a).astype(int), 0, arr.shape[1] - 1)
    return am, np.maximum(arr[fila, col], 0)


ultimo = (2026, 9)
meses = [(a, m) for a in range(1981, 2027) for m in (12, 1, 2, 3) if (a, m) <= ultimo]
with ThreadPoolExecutor(8) as ex:
    mm = dict(ex.map(leer, meses))

temporadas = [y for y in range(1981, 2026) if all((a, m) in mm for a, m in
                                                   [(y, 12), (y + 1, 1), (y + 1, 2), (y + 1, 3)])]
defm = np.stack([mm[(y, 12)] + mm[(y + 1, 1)] + mm[(y + 1, 2)] + mm[(y + 1, 3)] for y in temporadas])
clima = defm[[temporadas.index(y) for y in NORMAL]].mean(axis=0)
anom = 100 * (defm / np.maximum(clima, 1) - 1)
np.savez_compressed(DATOS / "lluvia_defm.npz", temporadas=np.array(temporadas),
                    defm=defm.astype("float32"), anom=anom.astype("float32"), normal=clima.astype("float32"))

# 3. Serie regional: ¿los Niños secan la puna del sur? -----------------------------------------
dpto = ubigeo // 10000
filas = []
for k, y in enumerate(temporadas):
    o = float(djf.get(y + 1, np.nan))
    f = {"temporada": f"{y}-{str(y + 1)[2:]}", "anio_fuego": y, "oni_def": o, "enso": clase_enso(o),
         "lluvia_mm": round(float(defm[k].mean())), "anomalia_pct": round(float(anom[k].mean()), 1)}
    for d, nombre in DEPARTAMENTOS.items():
        sel = dpto == int(d)
        f[f"anom_{nombre}"] = round(float(anom[k][sel].mean()), 1)
    filas.append(f)
t = pd.DataFrame(filas)
t.to_csv(SALIDAS / "lluvia_por_temporada.csv", index=False)
print(t[["temporada", "oni_def", "enso", "lluvia_mm", "anomalia_pct"]].to_string(index=False))
print(t.groupby("enso").anomalia_pct.agg(["mean", "count"]).round(1))
