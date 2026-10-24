"""Paso 5: ¿cuánto está ardiendo la puna en 2026 frente a 2012-2025?

- Histórico: NASA FIRMS, archivo anual de Perú de VIIRS S-NPP (375 m), 2012-2025.
- 2026: INPE Queimadas, archivos mensuales de Sudamérica, satélite NPP-375 (el mismo VIIRS
  S-NPP). FIRMS sin clave solo publica 7 días; INPE publica el año en curso completo.
- Comparabilidad: se cuentan los focos de jul–oct 2025 en las dos fuentes. Si coinciden, la
  serie 2012-2025 (FIRMS) y 2026 (INPE) se pueden comparar.
- Hectáreas: MCD64A1 ya publicó jul–ago 2026. Para set–oct se usa la razón histórica
  hectáreas MCD64A1 por foco VIIRS en la puna (2012-2025), con su rango entre años.
Escribe salidas/focos_por_anio.csv, salidas/focos_distrito_2026.csv y salidas/focos_resumen.json
"""
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import requests
from pyproj import Transformer

from comun import COLS, DATOS, FILAS, HA_PIX, PIX, SALIDAS, SINU, TRANSFORM, guardar_json

FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{a}/viirs-snpp_{a}_Peru.csv"
INPE = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/America_Sul/focos_mensal_{a}{m:02d}.csv"
CACHE = DATOS / "focos"
CACHE.mkdir(exist_ok=True)
malla = np.load(DATOS / "malla.npz")
puna, ubigeo = malla["puna"], malla["ubigeo"]
a_sinu = Transformer.from_crs(4326, SINU, always_xy=True)


def firms(anio):
    f = CACHE / f"firms_snpp_{anio}.csv"
    if not f.exists():
        f.write_bytes(requests.get(FIRMS.format(a=anio), timeout=300).content)
    d = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "confidence", "type"])
    return pd.DataFrame({"lat": d.latitude, "lon": d.longitude, "fecha": pd.to_datetime(d.acq_date),
                         "tipo": d["type"], "fuente": "FIRMS"})


def inpe(anio, mes):
    f = CACHE / f"inpe_peru_{anio}{mes:02d}.csv"
    if not f.exists() or (anio, mes) == (2026, 10):          # octubre 2026 sigue creciendo
        r = requests.get(INPE.format(a=anio, m=mes), timeout=600)
        d = pd.read_csv(io.BytesIO(r.content), usecols=["lat", "lon", "data_hora_gmt", "satelite", "pais"])
        d[d.pais == "Peru"].to_csv(f, index=False)
    d = pd.read_csv(f)
    d = d[d.satelite.isin(["NPP-375", "NPP-375D"])]
    return pd.DataFrame({"lat": d.lat, "lon": d.lon, "fecha": pd.to_datetime(d.data_hora_gmt).dt.normalize(),
                         "sat": d.satelite, "fuente": "INPE"})


def en_malla(d):
    x, y = a_sinu.transform(d.lon.to_numpy(), d.lat.to_numpy())
    col = np.floor((x - TRANSFORM.c) / PIX).astype(int)
    fila = np.floor((TRANSFORM.f - y) / PIX).astype(int)
    ok = (fila >= 0) & (fila < FILAS) & (col >= 0) & (col < COLS)
    d = d[ok].copy()
    d["pix"] = fila[ok] * COLS + col[ok]
    d["ubigeo"] = ubigeo.ravel()[d.pix]
    d["puna"] = puna.ravel()[d.pix]
    return d[d.ubigeo > 0]


with ThreadPoolExecutor(6) as ex:
    hist = pd.concat(ex.map(firms, range(2012, 2026)), ignore_index=True)
    nuevos = pd.concat(ex.map(lambda am: inpe(*am), [(2025, m) for m in (7, 8, 9, 10)] +
                              [(2026, m) for m in (7, 8, 9, 10)]), ignore_index=True)
hist, nuevos = en_malla(hist), en_malla(nuevos)
corte = nuevos[nuevos.fecha.dt.year == 2026].fecha.max()
dia_corte = (corte.month, corte.day)
print("Último día con focos INPE 2026:", corte.date())


def ventana(d, anio):
    """1 de julio al día de corte del año dado."""
    return d[(d.fecha >= pd.Timestamp(anio, 7, 1)) & (d.fecha <= pd.Timestamp(anio, *dia_corte))]


# 1. Comparabilidad FIRMS vs INPE en 2025 ------------------------------------------------------
f25 = ventana(hist, 2025)
i25 = ventana(nuevos, 2025)
comp = {"firms_2025_puna": int(f25.puna.sum()), "firms_2025_puna_sin_volcanes": int(f25[f25.tipo == 0].puna.sum()),
        "inpe_2025_puna_NPP-375": int(i25[i25.sat == "NPP-375"].puna.sum()),
        "inpe_2025_puna_NPP-375D": int(i25[i25.sat == "NPP-375D"].puna.sum()),
        "firms_2025_region": len(f25), "inpe_2025_region": len(i25)}
print("Comparabilidad jul–corte 2025:", comp)
# INPE reparte el mismo VIIRS S-NPP en dos etiquetas; juntas reproducen el conteo de FIRMS
i26 = ventana(nuevos, 2026)

# 2. Serie por año en la puna ------------------------------------------------------------------
filas = [{"anio": a, "focos_puna": int(ventana(hist, a).puna.sum()), "focos_region": len(ventana(hist, a)),
          "fuente": "FIRMS VIIRS S-NPP"} for a in range(2012, 2026)]
filas.append({"anio": 2026, "focos_puna": int(i26.puna.sum()), "focos_region": len(i26),
              "fuente": "INPE NPP-375 + NPP-375D"})
serie = pd.DataFrame(filas)
serie.to_csv(SALIDAS / "focos_por_anio.csv", index=False)
i26[i26.puna][["lat", "lon", "fecha", "ubigeo"]].round(4).to_csv(SALIDAS / "focos_puna_2026.csv", index=False)
print(serie.to_string(index=False))

# 3. Hectáreas: MCD64A1 jul–ago 2026 + set–corte estimado con la razón ha/foco ---------------
q = np.load(DATOS / "quemas.npz")
qd = pd.DataFrame({k: q[k] for k in ("pix", "anio", "mes", "doy", "puna")})
qp = qd[qd.puna]


def ha_mcd(anio, meses):
    return float(((qp.anio == anio) & qp.mes.isin(meses)).sum() * HA_PIX)


def focos_meses(d, anio, meses):
    v = ventana(d, anio)
    return int((v.puna & v.fecha.dt.month.isin(meses)).sum())


faltan = set(str(m) for m in q["faltan"])          # meses sin MCD64A1 en Planetary Computer
razones = []
for a in range(2012, 2026):
    if {f"{a}-09", f"{a}-10"} & faltan:
        continue
    fo = focos_meses(hist, a, (9, 10))
    if fo >= 20:
        razones.append({"anio": a, "focos_set_oct": fo, "ha_mcd64_set_oct": ha_mcd(a, (9, 10)),
                        "ha_por_foco": ha_mcd(a, (9, 10)) / fo})
raz = pd.DataFrame(razones)
# La mediana entre años y no la razón agregada: 2022 (un año extremo) pesaría demasiado
r_bajo, r_central, r_alto = raz.ha_por_foco.quantile([0.25, 0.5, 0.75])
f26_so = focos_meses(nuevos, 2026, (9, 10))
ha_ja = ha_mcd(2026, (7, 8))
est = {"ha_mcd64_jul_ago_2026": round(ha_ja), "focos_set_corte_2026": f26_so,
       "ha_por_foco_mediana": round(r_central, 2), "ha_por_foco_p25_p75": [round(r_bajo, 2), round(r_alto, 2)],
       "ha_puna_2026_central": round(ha_ja + r_central * f26_so),
       "ha_puna_2026_rango": [round(ha_ja + r_bajo * f26_so), round(ha_ja + r_alto * f26_so)]}
print("Hectáreas 2026:", est)

# 4. Por distrito: focos de puna 2026 frente a su promedio 2012-2025 ---------------------------
h_puna = pd.concat([ventana(hist, a).assign(anio=a) for a in range(2012, 2026)])
h_puna = h_puna[h_puna.puna]
prom = h_puna.groupby("ubigeo").size() / 14
maximo = h_puna.groupby(["ubigeo", "anio"]).size().groupby("ubigeo").max()
d26 = i26[i26.puna].groupby("ubigeo").size().rename("focos_2026").to_frame()
d26["promedio_2012_2025"] = prom.reindex(d26.index).fillna(0).round(1)
d26["maximo_2012_2025"] = maximo.reindex(d26.index).fillna(0).astype(int)
d26["record"] = d26.focos_2026 > d26.maximo_2012_2025
# Hectáreas por distrito con la misma regla que el total: MCD64A1 jul–ago + razón × focos set–oct
so = i26[i26.puna & i26.fecha.dt.month.isin([9, 10])].groupby("ubigeo").size()
qp26 = qp[(qp.anio == 2026) & qp.mes.isin([7, 8])]
ja = (pd.Series(ubigeo.ravel()[qp26.pix]).value_counts() * HA_PIX)
d26 = d26.reindex(d26.index.union(ja.index))
d26["focos_2026"] = d26.focos_2026.fillna(0).astype(int)
d26["promedio_2012_2025"] = prom.reindex(d26.index).fillna(0).round(1)
d26["maximo_2012_2025"] = maximo.reindex(d26.index).fillna(0).astype(int)
d26["record"] = d26.focos_2026 > d26.maximo_2012_2025
d26["focos_set_oct_2026"] = so.reindex(d26.index).fillna(0).astype(int)
d26["ha_mcd64_jul_ago_2026"] = ja.reindex(d26.index).fillna(0).round(1)
d26["ha_est_2026"] = (d26.ha_mcd64_jul_ago_2026 + r_central * d26.focos_set_oct_2026).round(1)
d26.index.name = "ubigeo"
d26.sort_values("focos_2026", ascending=False).to_csv(SALIDAS / "focos_distrito_2026.csv")

media = serie[serie.anio < 2026].focos_puna.mean()
guardar_json("focos_resumen.json", {
    "ventana": f"1 jul – {corte.day} {['', 'ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'set', 'oct', 'nov', 'dic'][corte.month]}",
    "corte": str(corte.date()), "comparabilidad_2025": comp,
    "focos_puna_2026": int(i26.puna.sum()), "media_2012_2025": round(float(media), 1),
    "veces_la_media": round(float(i26.puna.sum() / media), 2),
    "rango_2026": int((serie.focos_puna > serie.focos_puna.iloc[-1]).sum()) + 1,
    "anio_max_previo": int(serie[serie.anio < 2026].sort_values("focos_puna").anio.iloc[-1]),
    "distritos_con_focos_2026": int((d26.focos_2026 > 0).sum()), "distritos_record": int(d26.record.sum()),
    "hectareas": est, "razon_por_anio": raz.round(2).to_dict("records")})
