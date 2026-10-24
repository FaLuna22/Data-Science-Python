"""Paso 6: ¿el pajonal quemado se recupera peor cuando la lluvia que sigue al fuego es escasa?

Experimento natural con 25 temporadas (2001-2025). Cada **evento** es un píxel de puna que
MCD64A1 marca quemado entre julio y diciembre del año Y, sin quemas en los 3 años previos.
Su **control** es la mediana de los píxeles de puna sin quemar (Y-3 a Y+3) de la misma celda
de 0,25° y la misma franja de 200 m de altitud: sufren la misma sequía, pero no el fuego.

    Δ(t) = [NBR quemado − NBR control](t) − [lo mismo, mismo mes calendario, 2 años previos]

Δ = 0 es "igual que antes del fuego frente a su vecino"; Δ < 0 es la cicatriz que todavía se
ve. Es una diferencia en diferencias por píxel y por mes del año: la sequía que afecta a todo
el pajonal y la estacionalidad propia de cada sitio se restan; queda lo que agrega el fuego.
Prueba placebo: con solo el año Y-2 como base, el año Y-1 (sin fuego) debe dar Δ ≈ 0.
Luego se cruza Δ con la lluvia de diciembre a marzo que siguió al fuego (CHIRPS, en el mismo
píxel) y con El Niño (ONI). El mismo cálculo con NDVI muestra el "rebrote tierno".
Escribe salidas/eventos.csv.gz, salidas/curvas.csv y salidas/recuperacion.json
"""
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from comun import DATOS, DEPARTAMENTOS, HA_PIX, SALIDAS, guardar_json

warnings.filterwarnings("ignore", "Mean of empty slice")
SIN_DATO = -128
malla = np.load(DATOS / "malla.npz")
ind = np.load(DATOS / "indices_mensual.npz")
idx_puna, meses = ind["idx_puna"], ind["meses"]
SERIES = {"nbr": ind["nbr"], "ndvi": ind["ndvi"]}
t_de = {int(m): i for i, m in enumerate(meses)}                # aaaamm → fila de la serie
col_de = np.full(malla["puna"].size, -1, dtype="int64")
col_de[idx_puna] = np.arange(idx_puna.size)

cota = malla["cota"].ravel()[idx_puna]
lat, lon = malla["lat"].ravel()[idx_puna], malla["lon"].ravel()[idx_puna]
ubigeo = malla["ubigeo"].ravel()[idx_puna]
llave = ((np.floor(lat / 0.25).astype(int) * 1000 + np.floor(lon / 0.25).astype(int)) * 100
         + (cota // 200).astype(int))                           # celda 0,25° × franja de 200 m

lluvia = np.load(DATOS / "lluvia_defm.npz")
temporadas = list(lluvia["temporadas"])
anom = lluvia["anom"]                                           # temporadas × píxeles de puna
clima = pd.read_csv(SALIDAS / "lluvia_por_temporada.csv").set_index("anio_fuego")

q = np.load(DATOS / "quemas.npz")
qd = pd.DataFrame({"pix": q["pix"], "anio": q["anio"], "mes": q["mes"], "puna": q["puna"]})
qd = qd[qd.puna].copy()
qd["c"] = col_de[qd.pix]
qd["tq"] = (qd.anio - 2000) * 12 + qd.mes - 1                    # meses desde ene 2000

ANTES, DESPUES = 24, 36                                          # meses antes y después de jul Y
VENT = ANTES + DESPUES
T = np.arange(-ANTES, DESPUES)                                   # t = 0 es julio del año Y


def filas_de(y):
    """Filas de la serie de jul Y-2 a jun Y+3 (−1 si el mes no existe todavía)."""
    out = []
    for k in T:
        a, m = divmod(6 + int(k), 12)
        out.append(t_de.get((y + a) * 100 + m + 1, -1))
    return np.array(out)


def a_float(v):
    v = v.astype("float32")
    v[v == SIN_DATO] = np.nan
    return v / 100


def delta_de(serie, filas, ev_c, ctrl_c, llaves_ctrl, buenas):
    """Δ(t) de cada evento: diferencia con su control, menos el mismo mes de los años base."""
    ok = filas >= 0
    vc = np.full((ctrl_c.size, VENT), np.nan, dtype="float32")
    vc[:, ok] = a_float(serie[np.ix_(filas[ok], ctrl_c)]).T
    med = pd.DataFrame(vc).groupby(llaves_ctrl).median().loc[buenas]
    vb = np.full((ev_c.size, VENT), np.nan, dtype="float32")
    vb[:, ok] = a_float(serie[np.ix_(filas[ok], ev_c)]).T
    d = vb - med.loc[llave[ev_c]].to_numpy(dtype="float32")
    base2 = np.nanmean(np.stack([d[:, 0:12], d[:, 12:24]]), axis=0)     # 2 años previos
    delta = d - np.tile(base2, VENT // 12)
    placebo = d[:, 12:24] - d[:, 0:12]                                   # año Y-1 frente a Y-2
    return delta, placebo, vb


eventos, curvas, placebos = [], [], []
for y in range(2002, 2026):
    jul = (y - 2000) * 12 + 6
    tem = qd[(qd.tq >= jul) & (qd.tq < jul + 6)]
    if tem.empty:
        continue
    cand = tem.groupby("c").tq.min()
    previas = qd[(qd.tq >= jul - 36) & (qd.tq < jul)].c.unique()          # limpio antes
    cand = cand[~cand.index.isin(previas)]
    reinc = qd[(qd.tq >= jul + 6) & (qd.tq < jul + 30)].c.unique()        # vuelve a arder en 2 años
    sucios = qd[(qd.tq >= jul - 36) & (qd.tq < jul + 36)].c.unique()
    limpio = np.ones(idx_puna.size, bool)
    limpio[sucios] = False
    ctrl_c = np.flatnonzero(limpio & np.isin(llave, np.unique(llave[cand.index])))
    n_ctrl = pd.Series(llave[ctrl_c]).value_counts()
    buenas = n_ctrl[n_ctrl >= 10].index
    ev_c = cand.index[np.isin(llave[cand.index], buenas)].to_numpy()
    if ev_c.size == 0:
        continue
    filas = filas_de(y)
    dl, pl, vb = delta_de(SERIES["nbr"], filas, ev_c, ctrl_c, llave[ctrl_c], buenas)
    dv, _, _ = delta_de(SERIES["ndvi"], filas, ev_c, ctrl_c, llave[ctrl_c], buenas)

    def tramo(delta, t0, t1):
        return np.nanmean(delta[:, ANTES + t0:ANTES + t1 + 1], axis=1)

    k = cand.loc[ev_c].to_numpy() - jul                          # 0 = jul … 5 = dic
    cic = np.array([np.nanmean(dl[i, ANTES + k[i] + 1:ANTES + k[i] + 3]) for i in range(ev_c.size)])
    it = temporadas.index(y) if y in temporadas else None
    it2 = temporadas.index(y + 1) if (y + 1) in temporadas else None
    ev = pd.DataFrame({
        "c": ev_c, "anio": y, "mes_quema": k + 7, "ubigeo": ubigeo[ev_c], "cota": cota[ev_c],
        "lat": lat[ev_c].round(4), "lon": lon[ev_c].round(4),
        "nbr_previo": np.nanmean(vb[:, 12:24], axis=1),
        "cicatriz": cic,                          # Δ NBR 1-2 meses después de la quema
        "d_lluvia1": tramo(dl, 7, 9),             # feb–abr Y+1: primer rebrote (≈ 6 meses)
        "d_seca1": tramo(dl, 12, 14),             # jul–set Y+1: arranque de la siguiente temporada
        "d_lluvia2": tramo(dl, 19, 21),           # feb–abr Y+2 (≈ 18 meses)
        "d_seca2": tramo(dl, 24, 26),             # jul–set Y+2
        "ndvi_lluvia1": tramo(dv, 7, 9),          # el mismo Δ con NDVI: verdor del rebrote
        "placebo": np.nanmean(pl, axis=1),
        "reincide": np.isin(ev_c, reinc),
        "anom_lluvia1": anom[it][ev_c] if it is not None else np.nan,
        "anom_lluvia2": anom[it2][ev_c] if it2 is not None else np.nan,
        "oni": clima.oni_def.get(y, np.nan), "enso": clima.enso.get(y, None),
    })
    eventos.append(ev)
    limpios = ~ev.reincide.to_numpy()
    curvas.append(pd.DataFrame({"anio": y, "t": T, "nbr": np.nanmean(dl[limpios], axis=0),
                                "ndvi": np.nanmean(dv[limpios], axis=0),
                                "n": np.sum(~np.isnan(dl[limpios]), axis=0)}))
    print(y, "eventos:", ev_c.size, "· cicatriz NBR:", round(float(np.nanmean(cic)), 3),
          "· Δ feb–abr Y+1:", round(float(np.nanmean(ev.d_lluvia1)), 3),
          "· Δ jul–set Y+1:", round(float(np.nanmean(ev.d_seca1)), 3),
          "· placebo:", round(float(np.nanmean(ev.placebo)), 3))

E = pd.concat([e.dropna(axis=1, how="all") for e in eventos], ignore_index=True)
E["dpto"] = (E.ubigeo // 10000).map(lambda d: DEPARTAMENTOS[f"{d:02d}"])
E.round(4).to_csv(SALIDAS / "eventos.csv.gz", index=False)
curv = pd.concat(curvas, ignore_index=True)
curv.round(4).to_csv(SALIDAS / "curvas.csv", index=False)

# Analizables: cicatriz clara (ΔNBR ≤ −0,05) y sin reincidencia; así Δ mide recuperación
CORTES, ETIQ = [-100, -15, 15, 400], ["Seca (< −15 %)", "Normal (±15 %)", "Húmeda (> +15 %)"]
A = E[(E.cicatriz <= -0.05) & ~E.reincide].dropna(subset=["d_lluvia1", "anom_lluvia1"]).copy()
A["queda1"] = A.d_lluvia1 / A.cicatriz                           # fracción de la cicatriz que queda
A["queda_seca1"] = A.d_seca1 / A.cicatriz
A["lluvia"] = pd.cut(A.anom_lluvia1, CORTES, labels=ETIQ)
agg = dict(eventos=("c", "size"), temporadas=("anio", "nunique"), anom_lluvia=("anom_lluvia1", "mean"),
           cicatriz=("cicatriz", "mean"), d_lluvia1=("d_lluvia1", "mean"), d_seca1=("d_seca1", "mean"),
           d_lluvia2=("d_lluvia2", "mean"), queda1=("queda1", "median"), queda_seca1=("queda_seca1", "median"),
           ndvi_lluvia1=("ndvi_lluvia1", "mean"))
por_lluvia = A.groupby("lluvia", observed=True).agg(**agg).round(3)
por_enso = A.groupby("enso").agg(**agg, anios=("anio", lambda s: sorted(set(map(int, s))))).round(3)
print(por_lluvia.to_string())
print(por_enso.to_string())

# Regresión: Δ según la lluvia, a igual cicatriz, altitud y departamento; errores por temporada
A["lluvia10"] = A.anom_lluvia1 / 10
A["cota100"] = A.cota / 100


def regresion(y, datos):
    datos = datos.dropna(subset=[y])
    m = smf.ols(f"{y} ~ lluvia10 + cicatriz + cota100 + C(dpto)", data=datos).fit(
        cov_type="cluster", cov_kwds={"groups": datos.anio})
    return {"coef_por_10pct_lluvia": round(m.params["lluvia10"], 4),
            "ic95": [round(v, 4) for v in m.conf_int().loc["lluvia10"]],
            "p": round(m.pvalues["lluvia10"], 4), "coef_cicatriz": round(m.params["cicatriz"], 3),
            "n": int(m.nobs), "temporadas": int(datos.anio.nunique()), "r2": round(m.rsquared, 3)}


reg = {y: regresion(y, A) for y in ("d_lluvia1", "d_seca1", "d_lluvia2")}
print(reg)

# Reincidencia según la lluvia (todos los eventos)
E["lluvia"] = pd.cut(E.anom_lluvia1, CORTES, labels=ETIQ)
reincide = E.groupby("lluvia", observed=True).reincide.mean().round(3)

# ¿Arde más la puna la temporada que sigue a una lluvia escasa?
qt = pd.read_csv(SALIDAS / "quemas_por_temporada.csv").set_index("anio")
fo = pd.read_csv(SALIDAS / "focos_por_anio.csv").set_index("anio")
rng = range(2002, 2026)
sig = pd.DataFrame({"anom_previa": clima.anomalia_pct.shift(1).reindex(rng),
                    "enso_previo": clima.enso.shift(1).reindex(rng),
                    "ha_puna": qt.ha_puna.reindex(rng), "focos_puna": fo.focos_puna.reindex(rng),
                    "incompleto": qt.meses_faltantes.reindex(rng).notna()})
completo = sig[~sig.incompleto]
rho_ha = completo[["anom_previa", "ha_puna"]].corr(method="spearman").iloc[0, 1]
rho_fo = sig.dropna(subset=["focos_puna"])[["anom_previa", "focos_puna"]].corr(method="spearman").iloc[0, 1]
print("Spearman lluvia previa vs ha:", round(rho_ha, 2), "· vs focos:", round(rho_fo, 2))

guardar_json("recuperacion.json", {
    "indice": "NBR (MOD09A1)", "eventos_total": int(len(E)), "ha_eventos": round(len(E) * HA_PIX),
    "eventos_analizados": int(len(A)), "temporadas": sorted(map(int, A.anio.unique())),
    "placebo_medio": round(float(E.placebo.mean()), 4), "cicatriz_media": round(float(A.cicatriz.mean()), 3),
    "ndvi_lluvia1_medio": round(float(A.ndvi_lluvia1.mean()), 3),
    "por_lluvia": por_lluvia.reset_index().astype({"lluvia": str}).to_dict("records"),
    "por_enso": por_enso.reset_index().to_dict("records"),
    "regresion": reg, "reincidencia_por_lluvia": {str(k): v for k, v in reincide.items()},
    "temporada_siguiente": {"spearman_lluvia_previa_vs_ha": round(rho_ha, 3),
                            "spearman_lluvia_previa_vs_focos": round(rho_fo, 3),
                            "tabla": sig.reset_index(names="anio").round(1).to_dict("records")},
})
