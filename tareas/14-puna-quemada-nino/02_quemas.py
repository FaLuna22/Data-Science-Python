"""Paso 2: todas las quemas que MODIS registró en el sur andino, nov 2000 – último mes publicado.

MCD64A1 v061 (500 m, mensual) da el día del año en que se quemó cada píxel (Burn_Date > 0).
Guarda una fila por píxel quemado y mes: índice del píxel, año, mes y día del año.
Escribe datos/quemas.npz y salidas/quemas_por_temporada.csv
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from comun import DATOS, HA_PIX, SALIDAS, buscar, leer_tiles

malla = np.load(DATOS / "malla.npz")
region, puna = malla["ubigeo"] > 0, malla["puna"]

items = buscar("modis-64A1-061", "2000-11-01/2026-12-31")
por_mes = {}
for it in items:
    por_mes.setdefault(it["properties"]["start_datetime"][:7], []).append(it)
todos = [str(p) for p in pd.period_range("2000-11", max(por_mes), freq="M")]
faltan = [m for m in todos if m not in por_mes]       # meses que Planetary Computer no tiene
print("MCD64A1:", len(items), "ítems ·", min(por_mes), "a", max(por_mes), "· faltan:", faltan)


def leer(mes):
    a = leer_tiles(por_mes[mes], "Burn_Date")
    if a is None:
        return mes, None
    idx = np.flatnonzero((a > 0) & region)
    return mes, (idx, a.ravel()[idx])


filas = []
with ThreadPoolExecutor(12) as ex:
    for mes, r in ex.map(leer, sorted(por_mes)):
        if r is None:
            print("  incompleto:", mes)
            continue
        idx, doy = r
        filas.append(pd.DataFrame({"pix": idx.astype("int32"), "anio": int(mes[:4]),
                                   "mes": int(mes[5:]), "doy": doy.astype("int16")}))
q = pd.concat(filas, ignore_index=True)
q["puna"] = puna.ravel()[q.pix]
np.savez_compressed(DATOS / "quemas.npz", **{c: q[c].to_numpy() for c in q.columns},
                    ultimo_mes=max(por_mes), faltan=np.array(faltan))

# Temporada de fuego = julio a diciembre (la sequía estacional); la lluvia llega de dic a mar
temp = q[q.mes >= 7].groupby(["anio", "puna"]).size().unstack(fill_value=0) * HA_PIX
temp.columns = ["ha_fuera_de_puna", "ha_puna"]
temp = temp.round().astype(int)
temp["meses_faltantes"] = [",".join(m for m in faltan if m.startswith(str(a)) and int(m[5:]) >= 7) for a in temp.index]
temp.to_csv(SALIDAS / "quemas_por_temporada.csv")
print(temp.tail(12))
print("Píxeles de puna quemados alguna vez:", q[q.puna].pix.nunique())
