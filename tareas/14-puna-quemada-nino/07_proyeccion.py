"""Paso 7: parte por distrito para la temporada de lluvias 2026-27 y el inicio de la de fuego 2027.

Para cada distrito del sur andino con puna quemada en 2026:
1. **Fuego 2026**: focos VIIRS en la puna frente a 2012-2025 y hectáreas estimadas (paso 5).
2. **Lluvia esperada si el Niño es fuerte**: la anomalía de diciembre a marzo que tuvo la puna
   del distrito en los 5 Niños fuertes desde 1981 (1982-83, 1991-92, 1997-98, 2015-16 y
   2023-24). No es un pronóstico: es lo que pasó las veces anteriores.
3. **Pasto que no se recupera**: con los eventos 2002-2025 (paso 6), la probabilidad de que un
   píxel quemado llegue a julio–setiembre del año siguiente con al menos la mitad de su
   cicatriz, según la lluvia que tuvo. Se aplica a las hectáreas 2026 con la mezcla de
   lluvias de los Niños fuertes.
4. **Población**: WorldPop 2026 (100 m) que vive en la puna del distrito.
5. **Prioridad** con tres criterios explícitos, sin índice compuesto (A, B y C abajo).
Además, el caso Chichas: cómo se recuperó lo que ardió en 2002 y en 2013.
Escribe salidas/distritos_prioridad.csv, salidas/distritos.geojson, salidas/proyeccion.json
"""
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.warp import Resampling, reproject

from comun import DATOS, DEPARTAMENTOS, DISTRITOS, HA_PIX, SALIDAS, SINU, TRANSFORM, guardar_json

warnings.filterwarnings("ignore", "Mean of empty slice")
NINOS_FUERTES = [1982, 1991, 1997, 2015, 2023]                  # año de inicio de la temporada
WORLDPOP = ("https://data.worldpop.org/GIS/Population/Global_2015_2030/R2024B/2026/PER/v1/"
            "100m/constrained/per_pop_2026_CN_100m_R2024B_v1.tif")
CORTES, ETIQ = [-100, -15, 15, 400], ["Seca (< −15 %)", "Normal (±15 %)", "Húmeda (> +15 %)"]

malla = np.load(DATOS / "malla.npz")
ubigeo_g, puna_g = malla["ubigeo"], malla["puna"]
idx_puna = np.flatnonzero(puna_g)
ub_puna = ubigeo_g.ravel()[idx_puna]

# 1. Población WorldPop 2026 en la malla de 500 m -------------------------------------------------
wp = DATOS / "worldpop_per_2026.tif"
if not wp.exists():
    wp.write_bytes(requests.get(WORLDPOP, timeout=600).content)
pob = np.zeros(ubigeo_g.shape, dtype="float32")
with rasterio.open(wp) as s:
    a = s.read(1).astype("float32")
    a[a == s.nodata] = 0
    reproject(a, pob, src_transform=s.transform, src_crs=s.crs, dst_transform=TRANSFORM, dst_crs=SINU,
              resampling=Resampling.sum)
ub = pd.Series(ubigeo_g.ravel())
dist_tab = pd.DataFrame({"ha_puna": ub[puna_g.ravel()].value_counts() * HA_PIX,
                         "pob_puna": pd.Series(pob.ravel()[puna_g.ravel()]).groupby(ub[puna_g.ravel()].values).sum(),
                         "pob_total": pd.Series(pob.ravel()).groupby(ub.values).sum()}).drop(index=0, errors="ignore")

# 2. Lluvia de diciembre a marzo en los Niños fuertes ------------------------------------------
ll = np.load(DATOS / "lluvia_defm.npz")
temporadas = list(ll["temporadas"])
anom = pd.DataFrame(ll["anom"][[temporadas.index(y) for y in NINOS_FUERTES]].T, columns=NINOS_FUERTES)
anom["ubigeo"] = ub_puna
por_dist = anom.groupby("ubigeo").mean()
lluvia = pd.DataFrame({"anom_nino_fuerte": por_dist.mean(axis=1).round(1),
                       "anom_nino_min": por_dist.min(axis=1).round(1),
                       "anom_nino_max": por_dist.max(axis=1).round(1)})
for y in NINOS_FUERTES:
    lluvia[f"anom_{y}"] = por_dist[y].round(1)
clases_nino = pd.cut(por_dist.stack(), CORTES, labels=ETIQ).groupby(level=0).value_counts(normalize=True).unstack()

# 3. Probabilidad de no recuperarse según la lluvia (eventos 2002-2025) ---------------------------
E = pd.read_csv(SALIDAS / "eventos.csv.gz")
A = E[(E.cicatriz <= -0.05) & ~E.reincide].dropna(subset=["d_seca1", "anom_lluvia1"]).copy()
A["sin_recuperar"] = A.d_seca1 / A.cicatriz >= 0.5               # ≥ la mitad de la cicatriz en jul–set Y+1
A["lluvia"] = pd.cut(A.anom_lluvia1, CORTES, labels=ETIQ)
p_clase = A.groupby("lluvia", observed=True).sin_recuperar.mean()
n_clase = A.groupby("lluvia", observed=True).size()
p_normal = float(A[A.lluvia == ETIQ[1]].sin_recuperar.mean())
print("P(sin recuperar en jul–set siguiente):", p_clase.round(3).to_dict(), n_clase.to_dict())

# 4. Tabla por distrito ----------------------------------------------------------------------
f = pd.read_csv(SALIDAS / "focos_distrito_2026.csv").set_index("ubigeo")
d = gpd.read_file(DISTRITOS)
d = d[d.IDDPTO.isin(DEPARTAMENTOS) & d.geometry.notna()].copy()
d["ubigeo"] = d.IDDIST.astype(int)
d = d.set_index("ubigeo")[["NOMBDIST", "NOMBPROV", "NOMBDEP", "geometry"]]
t = d.drop(columns="geometry").join(dist_tab).join(lluvia).join(f)
t = t[t.ha_puna.fillna(0) > 0].copy()
for c in ("focos_2026", "focos_set_oct_2026"):
    t[c] = t[c].fillna(0).astype(int)
for c in ("promedio_2012_2025", "ha_est_2026", "ha_mcd64_jul_ago_2026"):
    t[c] = t[c].fillna(0)
t["record"] = t.record.fillna(False).astype(bool)
mezcla = clases_nino.reindex(t.index).fillna(0)
t["p_sin_recuperar_nino"] = sum(mezcla[c] * p_clase.get(c, np.nan) for c in ETIQ).round(3)
t["ha_sin_recuperar_jul2027"] = (t.ha_est_2026 * t.p_sin_recuperar_nino).round(1)
t["ha_sin_recuperar_si_normal"] = (t.ha_est_2026 * p_normal).round(1)
t["veces_promedio"] = (t.focos_2026 / t.promedio_2012_2025.replace(0, np.nan)).round(2)

# Criterios (se muestran por separado, como en un parte de situación)
t["A_fuego_anormal"] = (t.record & (t.focos_2026 >= 10)) | ((t.veces_promedio >= 2) & (t.focos_2026 >= 10))
t["B_lluvia_nino_seca"] = t.anom_nino_fuerte <= -15
t["C_area_relevante"] = t.ha_est_2026 >= 100
n_crit = t[["A_fuego_anormal", "B_lluvia_nino_seca", "C_area_relevante"]].sum(axis=1)
t["prioridad"] = np.select([n_crit == 3, n_crit == 2, t.focos_2026 + t.ha_est_2026 > 0],
                           ["Alta", "Media", "Baja"], "Sin fuego 2026")
orden = {"Alta": 0, "Media": 1, "Baja": 2, "Sin fuego 2026": 3}
t = t.sort_values(["prioridad", "ha_sin_recuperar_jul2027"], key=lambda s: s.map(orden) if s.name == "prioridad" else -s)
for c in ("ha_puna", "pob_puna", "pob_total"):
    t[c] = t[c].fillna(0).round()
t.to_csv(SALIDAS / "distritos_prioridad.csv")
print(t.prioridad.value_counts())
print(t.head(15)[["NOMBDIST", "NOMBDEP", "focos_2026", "veces_promedio", "ha_est_2026", "anom_nino_fuerte",
                  "ha_sin_recuperar_jul2027", "pob_puna", "prioridad"]].to_string())

g = d.join(t[["prioridad", "focos_2026", "ha_est_2026", "anom_nino_fuerte", "ha_sin_recuperar_jul2027",
              "pob_puna", "record", "veces_promedio"]], how="inner").reset_index()
g["geometry"] = g.geometry.simplify(0.003)
g.to_file(SALIDAS / "distritos.geojson", driver="GeoJSON")

# 5. Caso Chichas: lo que ardió en 2002 y 2013, año por año ---------------------------------------
CHICHAS = 40604
casos = {}
for y in (2002, 2013):
    sel = E[(E.ubigeo == CHICHAS) & (E.anio == y)]
    casos[str(y)] = {"pixeles": int(len(sel)), "ha": round(len(sel) * HA_PIX),
                     "cicatriz": round(float(sel.cicatriz.mean()), 3) if len(sel) else None,
                     "d_lluvia1": round(float(sel.d_lluvia1.mean()), 3) if len(sel) else None,
                     "d_seca1": round(float(sel.d_seca1.mean()), 3) if len(sel) else None,
                     "d_lluvia2": round(float(sel.d_lluvia2.mean()), 3) if len(sel) else None,
                     "anom_lluvia1": round(float(sel.anom_lluvia1.mean()), 1) if len(sel) else None,
                     "enso": sel.enso.iloc[0] if len(sel) else None}
ch = t.loc[CHICHAS].to_dict() if CHICHAS in t.index else {}

alta = t[t.prioridad == "Alta"]
guardar_json("proyeccion.json", {
    "ninos_fuertes": NINOS_FUERTES,
    "p_sin_recuperar_por_lluvia": {k: round(float(v), 3) for k, v in p_clase.items()},
    "n_por_lluvia": {k: int(v) for k, v in n_clase.items()}, "p_sin_recuperar_normal": round(p_normal, 3),
    "distritos_por_prioridad": t.prioridad.value_counts().to_dict(),
    "ha_est_2026_total": round(float(t.ha_est_2026.sum())),
    "ha_sin_recuperar_jul2027_total": round(float(t.ha_sin_recuperar_jul2027.sum())),
    "ha_sin_recuperar_si_normal_total": round(float(t.ha_sin_recuperar_si_normal.sum())),
    "alta": {"distritos": int(len(alta)), "ha_est_2026": round(float(alta.ha_est_2026.sum())),
             "ha_sin_recuperar_jul2027": round(float(alta.ha_sin_recuperar_jul2027.sum())),
             "pob_puna": round(float(alta.pob_puna.sum())), "focos_2026": int(alta.focos_2026.sum())},
    "pob_puna_distritos_con_fuego": round(float(t[t.prioridad != "Sin fuego 2026"].pob_puna.sum())),
    "chichas": {"2026": {k: (v if not isinstance(v, (np.floating, np.integer, np.bool_)) else v.item())
                         for k, v in ch.items()}, "historia": casos},
})
