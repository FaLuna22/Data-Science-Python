"""Paso 3: NBR y NDVI mensuales de cada píxel de puna, feb 2000 – oct 2026.

MOD09A1 (Terra, reflectancia de superficie, 8 días, 500 m) en la misma malla que MCD64A1.
- NBR = (b2 − b7) / (b2 + b7): infrarrojo cercano contra onda corta (2,1 µm). Ve la biomasa
  quemada y la ceniza; es el índice del dNBR.
- NDVI = (b2 − b1) / (b2 + b1): solo verdor.
Se usa MOD09A1 y no MOD13A1 porque MOD13 elige el día de NDVI máximo de cada 16 días: en la
puna esa regla esconde el fuego (prueba con las quemas de 2022: el NBR cae −0,18 al mes
siguiente y el NDVI de MOD13 no cambia).
Filtro con sur_refl_state_500m: sin nubes, sombra, nieve ni vecino de nube. Mediana mensual.
Escribe datos/indices_mensual.npz (meses × píxeles de puna, ×100 en int8; -128 = sin dato)
"""
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import numpy as np

from comun import DATOS, buscar, leer_tiles

SIN_DATO = -128
warnings.filterwarnings("ignore", "All-NaN slice")      # meses nublados: quedan como sin dato
malla = np.load(DATOS / "malla.npz")
idx_puna = np.flatnonzero(malla["puna"])

items = [it for it in buscar("modis-09A1-061", "2000-02-01/2026-12-31") if it["id"].startswith("MOD09A1")]
grupos = {}
for it in items:
    grupos.setdefault(it["id"].split(".")[1], []).append(it)       # A2026081 → [h10v10, h11v10]
grupos = {k: v for k, v in grupos.items() if len(v) == 2}


def mes_de(fecha):
    d = date(int(fecha[1:5]), 1, 1) + timedelta(days=int(fecha[5:]) - 1 + 4)   # día central
    return d.year * 100 + d.month


def despejado(st):
    return (((st & 3) == 0) & ((st >> 2) & 1 == 0) & ((st >> 10) & 1 == 0) &
            ((st >> 12) & 1 == 0) & ((st >> 13) & 1 == 0) & ((st >> 15) & 1 == 0))


def leer(fecha):
    par = grupos[fecha]
    b = {n: leer_tiles(par, f"sur_refl_b0{n}").ravel()[idx_puna].astype("float32") for n in (1, 2, 7)}
    st = leer_tiles(par, "sur_refl_state_500m").ravel()[idx_puna].astype("int32")
    ok = despejado(st) & (b[1] > 0) & (b[2] > 0) & (b[7] > 0)
    nbr = np.where(ok, (b[2] - b[7]) / (b[2] + b[7]), np.nan)
    ndvi = np.where(ok, (b[2] - b[1]) / (b[2] + b[1]), np.nan)
    return fecha, nbr.astype("float32"), ndvi.astype("float32")


meses = sorted({mes_de(f) for f in grupos})
pos = {m: i for i, m in enumerate(meses)}
print("MOD09A1:", len(grupos), "compuestos ·", meses[0], "a", meses[-1])

# Mediana mensual sin guardar todo en float: se acumulan los 3-4 compuestos de cada mes
salida = {n: np.full((len(meses), idx_puna.size), SIN_DATO, dtype="int8") for n in ("nbr", "ndvi")}
pendientes = {}
with ThreadPoolExecutor(16) as ex:
    for n, (fecha, nbr, ndvi) in enumerate(ex.map(leer, sorted(grupos))):
        m = mes_de(fecha)
        pendientes.setdefault(m, []).append((nbr, ndvi))
        for viejo in [k for k in pendientes if k < m]:          # el mes anterior ya está completo
            for j, nombre in enumerate(("nbr", "ndvi")):
                med = np.nanmedian(np.stack([p[j] for p in pendientes[viejo]]), axis=0)
                salida[nombre][pos[viejo]] = np.where(np.isnan(med), SIN_DATO,
                                                      np.clip(np.round(med * 100), -127, 127)).astype("int8")
            del pendientes[viejo]
        if n % 100 == 0:
            print(f"  {n}/{len(grupos)}", fecha, flush=True)
for viejo, lista in pendientes.items():
    for j, nombre in enumerate(("nbr", "ndvi")):
        med = np.nanmedian(np.stack([p[j] for p in lista]), axis=0)
        salida[nombre][pos[viejo]] = np.where(np.isnan(med), SIN_DATO,
                                              np.clip(np.round(med * 100), -127, 127)).astype("int8")

np.savez_compressed(DATOS / "indices_mensual.npz", nbr=salida["nbr"], ndvi=salida["ndvi"],
                    idx_puna=idx_puna, meses=np.array(meses))
cob = (salida["nbr"] != SIN_DATO).mean(axis=1)
print("Cobertura media por mes:", round(float(cob.mean()), 3), "· peor:", meses[int(cob.argmin())], round(float(cob.min()), 3))
