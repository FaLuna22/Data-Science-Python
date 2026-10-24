"""Paso 8: la web del parte de situación (un solo HTML, sin librerías ni internet).

Mapa y gráficos son SVG generados aquí con los resultados de los pasos 1 a 7, y toman sus
colores de variables CSS, así que se leen igual en tema claro y oscuro.
Escribe web.html (la página que se publica) y salidas/web_datos.json
"""
import html
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from comun import AQUI, HA_PIX, SALIDAS

J = lambda n: json.load(open(SALIDAS / n, encoding="utf-8"))
malla_r, focos_r, rec, proy = J("malla_resumen.json"), J("focos_resumen.json"), J("recuperacion.json"), J("proyeccion.json")
lluvia = pd.read_csv(SALIDAS / "lluvia_por_temporada.csv")
focos_anio = pd.read_csv(SALIDAS / "focos_por_anio.csv")
curvas = pd.read_csv(SALIDAS / "curvas.csv")
eventos = pd.read_csv(SALIDAS / "eventos.csv.gz")
dist = pd.read_csv(SALIDAS / "distritos_prioridad.csv")
geo = gpd.read_file(SALIDAS / "distritos.geojson")
puntos = pd.read_csv(SALIDAS / "focos_puna_2026.csv")


def num(x, d=0):
    """Formato peruano del INEI: espacio fino para miles, coma decimal."""
    s = f"{x:,.{d}f}"
    return s.replace(",", " ").replace(".", ",")


def pct(x, d=0, signo=True):
    return ("+" if signo and x > 0 else "") + num(x, d).replace("-", "−") + " %"


esc = html.escape

# ---------------------------------------------------------------------------------------------
# Mapa: proyección equirectangular con corrección de coseno (suficiente para 7° de latitud)
# ---------------------------------------------------------------------------------------------
W_MAPA = 720
lon0, lat0, lon1, lat1 = geo.total_bounds
k_lat = np.cos(np.radians((lat0 + lat1) / 2))
escala = W_MAPA / ((lon1 - lon0) * k_lat)
H_MAPA = (lat1 - lat0) * escala


def xy(lon, lat):
    return (lon - lon0) * k_lat * escala, (lat1 - lat) * escala


def ruta(geom):
    partes = []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for p in polys:
        for anillo in [p.exterior, *p.interiors]:
            c = [xy(x, y) for x, y in anillo.coords]
            partes.append("M" + "L".join(f"{a:.1f} {b:.1f}" for a, b in c) + "Z")
    return "".join(partes)


CLASE = {"Alta": "p-alta", "Media": "p-media", "Baja": "p-baja", "Sin fuego 2026": "p-nada"}
info = {}
caminos = []
for _, r in geo.iterrows():
    u = int(r.ubigeo)
    fila = dist[dist.ubigeo == u]
    if fila.empty:
        continue
    f = fila.iloc[0]
    info[u] = {"n": f.NOMBDIST.title(), "p": f.NOMBPROV.title(), "d": f.NOMBDEP.title(), "pr": f.prioridad,
               "fo": int(f.focos_2026), "vp": None if pd.isna(f.veces_promedio) else float(f.veces_promedio),
               "re": bool(f.record), "ha": float(f.ha_est_2026), "ll": float(f.anom_nino_fuerte),
               "sr": float(f.ha_sin_recuperar_jul2027), "po": int(f.pob_puna), "hp": float(f.ha_puna)}
    caminos.append(f'<path d="{ruta(r.geometry)}" class="{CLASE[f.prioridad]}" data-u="{u}"></path>')

dep = geo.dissolve(by=geo.ubigeo // 10000)
bordes = "".join(f'<path d="{ruta(g)}" class="dep"></path>' for g in dep.geometry)
pts = "".join('<circle cx="{:.1f}" cy="{:.1f}" r="1.1"></circle>'.format(*xy(lo, la))
              for lo, la in zip(puntos.lon, puntos.lat))
etiquetas = ""
for d_cod, g in dep.geometry.items():
    nombre = {3: "Apurímac", 4: "Arequipa", 5: "Ayacucho", 8: "Cusco", 18: "Moquegua", 21: "Puno", 23: "Tacna"}[d_cod]
    c = g.representative_point()
    x, y = xy(c.x, c.y)
    etiquetas += f'<text x="{x:.0f}" y="{y:.0f}" class="dep-n">{nombre.upper()}</text>'
mapa_svg = (f'<svg viewBox="0 0 {W_MAPA} {H_MAPA:.0f}" class="mapa" role="img" '
            f'aria-label="Mapa de distritos del sur andino por prioridad">'
            f'<g class="distritos">{"".join(caminos)}</g><g class="bordes">{bordes}</g>'
            f'<g class="focos">{pts}</g><g>{etiquetas}</g></svg>')


# ---------------------------------------------------------------------------------------------
# Gráficos SVG
# ---------------------------------------------------------------------------------------------
def eje_y(vals, y_de, x0, x1, fmt):
    out = ""
    for v in vals:
        y = y_de(v)
        out += f'<line x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}" class="{"cero" if v == 0 else "grid"}"></line>'
        out += f'<text x="{x0 - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{fmt(v)}</text>'
    return out


def grafico_lluvia():
    W, H, L, R, T, B = 760, 300, 48, 12, 16, 46
    d = lluvia.copy()
    n = len(d) + 1
    bw = (W - L - R) / n
    y_de = lambda v: T + (40 - v) / 100 * (H - T - B)                 # de +40 % a −60 %
    s = eje_y([40, 20, 0, -20, -40, -60], y_de, L, W - R, lambda v: pct(v))
    for i, r in d.iterrows():
        x = L + i * bw
        y0, y1 = sorted([y_de(0), y_de(r.anomalia_pct)])
        cl = {"Niño fuerte": "b-nf", "Niño": "b-n", "Niña": "b-na", "Neutro": "b-ne"}[r.enso]
        s += (f'<rect x="{x + 1:.1f}" y="{y0:.1f}" width="{bw - 2:.1f}" height="{max(y1 - y0, 0.5):.1f}" class="{cl}">'
              f'<title>{r.temporada} · {r.enso} (ONI {num(r.oni_def, 2)}) · lluvia dic–mar {pct(r.anomalia_pct, 1)}</title></rect>')
        if r.enso == "Niño fuerte":
            s += f'<text x="{x + bw / 2:.1f}" y="{y1 + 13:.1f}" class="lab" text-anchor="middle">{r.temporada[:4]}</text>'
        if i % 5 == 0:
            s += f'<text x="{x + bw / 2:.1f}" y="{H - B + 16}" class="tick" text-anchor="middle">{r.temporada[:4]}</text>'
    x = L + len(d) * bw
    s += (f'<rect x="{x + 1:.1f}" y="{T}" width="{bw - 2:.1f}" height="{H - T - B}" class="b-pron">'
          f'<title>2026-27: pronóstico de SENAMHI entre normal e inferior a lo normal</title></rect>'
          f'<text x="{x - 4:.1f}" y="{T + 10}" class="lab" text-anchor="end">2026-27 ?</text>')
    s += f'<text x="{L}" y="{H - 8}" class="tick">Temporada de lluvias (dic–mar) · anomalía frente a 1991-2020, puna del sur andino</text>'
    return f'<svg viewBox="0 0 {W} {H}" class="graf" role="img" aria-label="Anomalía de lluvia por temporada">{s}</svg>'


def curva_promedio(col):
    c = curvas[(curvas.t >= -12) & (curvas.t <= 30)].copy()
    c["w"] = c[col] * c.n
    g = c.groupby("t")[["w", "n"]].sum()
    return (g.w / g.n).reindex(range(-12, 31))


def grafico_indices():
    W, H, L, R, T, B = 760, 280, 48, 110, 16, 40
    nbr, ndvi = curva_promedio("nbr"), curva_promedio("ndvi")
    lo, hi = -0.14, 0.04
    x_de = lambda t: L + (t + 12) / 42 * (W - L - R)
    y_de = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    s = eje_y([0.04, 0, -0.04, -0.08, -0.12], y_de, L, W - R, lambda v: num(v, 2).replace("-", "−"))
    for t0, t1 in ((7, 9), (19, 21)):
        s += f'<rect x="{x_de(t0 - .5):.1f}" y="{T}" width="{x_de(t1 + .5) - x_de(t0 - .5):.1f}" height="{H - T - B}" class="lluvia-band"></rect>'
    s += f'<line x1="{x_de(0):.1f}" x2="{x_de(0):.1f}" y1="{T}" y2="{H - B}" class="marca"></line>'
    s += f'<text x="{x_de(0) + 4:.1f}" y="{T + 10}" class="lab">jul: empieza la temporada de fuego</text>'
    s += f'<text x="{x_de(8):.1f}" y="{H - B - 6}" class="lab" text-anchor="middle">lluvias</text>'
    s += f'<text x="{x_de(20):.1f}" y="{H - B - 6}" class="lab" text-anchor="middle">lluvias</text>'
    for serie, cl, nombre in ((ndvi, "l-ndvi", "NDVI (verdor)"), (nbr, "l-nbr", "NBR (biomasa)")):
        p = "M" + "L".join(f"{x_de(t):.1f} {y_de(v):.1f}" for t, v in serie.items() if not np.isnan(v))
        s += f'<path d="{p}" class="{cl}"></path>'
        ult = serie.dropna().iloc[-1]
        s += f'<text x="{x_de(30) + 6:.1f}" y="{y_de(ult) + 4:.1f}" class="lab {cl}-t">{nombre}</text>'
    for t in range(-12, 31, 6):
        s += f'<text x="{x_de(t):.1f}" y="{H - B + 16}" class="tick" text-anchor="middle">{t:+d}</text>'
    s += f'<text x="{L}" y="{H - 6}" class="tick">Meses desde julio del año del fuego · Δ frente a puna vecina sin quemar</text>'
    return f'<svg viewBox="0 0 {W} {H}" class="graf" role="img" aria-label="NDVI y NBR después del fuego">{s}</svg>'


def grafico_recuperacion():
    W, H, L, R, T, B = 760, 290, 48, 150, 16, 52
    pasos = [("cicatriz", "1–2 meses"), ("d_lluvia1", "feb–abr +1"), ("d_seca1", "jul–set +1"),
             ("d_lluvia2", "feb–abr +2"), ("d_seca2", "jul–set +2")]
    A = eventos[(eventos.cicatriz <= -0.05) & ~eventos.reincide].copy()
    A["lluvia"] = pd.cut(A.anom_lluvia1, [-100, -15, 15, 400], labels=["Seca", "Normal", "Húmeda"])
    g = A.groupby("lluvia", observed=True)[[p for p, _ in pasos]].mean()
    n = A.groupby("lluvia", observed=True).size()
    lo, hi = -0.16, 0.02
    x_de = lambda i: L + 20 + i / (len(pasos) - 1) * (W - L - R - 40)
    y_de = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    s = eje_y([0, -0.04, -0.08, -0.12, -0.16], y_de, L, W - R, lambda v: num(v, 2).replace("-", "−"))
    for i, (_, et) in enumerate(pasos):
        s += f'<text x="{x_de(i):.1f}" y="{H - B + 16}" class="tick" text-anchor="middle">{et}</text>'
    for clase, cl in (("Húmeda", "l-humeda"), ("Normal", "l-normal"), ("Seca", "l-seca")):
        if clase not in g.index:
            continue
        v = g.loc[clase]
        p = "M" + "L".join(f"{x_de(i):.1f} {y_de(v[c]):.1f}" for i, (c, _) in enumerate(pasos) if not np.isnan(v[c]))
        s += f'<path d="{p}" class="{cl}"></path>'
        for i, (c, et) in enumerate(pasos):
            if not np.isnan(v[c]):
                s += (f'<circle cx="{x_de(i):.1f}" cy="{y_de(v[c]):.1f}" r="3.5" class="{cl}-p">'
                      f'<title>{clase} · {et}: ΔNBR {num(v[c], 3).replace("-", "−")}</title></circle>')
        s += (f'<text x="{x_de(len(pasos) - 1) + 10:.1f}" y="{y_de(v["d_seca2"]) + 4:.1f}" class="lab {cl}-t">'
              f'{clase} · {num(n[clase])} píxeles</text>')
    s += f'<text x="{L}" y="{H - 10}" class="tick">ΔNBR medio del píxel quemado frente a su vecino sin quemar (0 = recuperado). Lluvia dic–mar tras el fuego: seca &lt; −15 %, húmeda &gt; +15 %.</text>'
    return f'<svg viewBox="0 0 {W} {H}" class="graf" role="img" aria-label="Recuperación según la lluvia">{s}</svg>'


def grafico_focos():
    W, H, L, R, T, B = 760, 240, 48, 12, 22, 34
    d = focos_anio
    bw = (W - L - R) / len(d)
    tope = 4000
    y_de = lambda v: T + (tope - v) / tope * (H - T - B)
    s = eje_y([0, 1000, 2000, 3000, 4000], y_de, L, W - R, lambda v: num(v))
    media = d[d.anio < 2026].focos_puna.mean()
    for i, r in d.iterrows():
        x = L + i * bw
        cl = "b-2026" if r.anio == 2026 else "b-hist"
        s += (f'<rect x="{x + 3:.1f}" y="{y_de(r.focos_puna):.1f}" width="{bw - 6:.1f}" height="{y_de(0) - y_de(r.focos_puna):.1f}" class="{cl}">'
              f'<title>{r.anio}: {num(r.focos_puna)} focos en la puna (1 jul – {focos_r["ventana"].split("– ")[1]})</title></rect>')
        s += f'<text x="{x + bw / 2:.1f}" y="{H - B + 15}" class="tick" text-anchor="middle">{r.anio}</text>'
        if r.anio == 2026:
            s += f'<text x="{x + bw / 2:.1f}" y="{y_de(r.focos_puna) - 6:.1f}" class="lab" text-anchor="middle">{num(r.focos_puna)}</text>'
    s += (f'<line x1="{L}" x2="{W - R}" y1="{y_de(media):.1f}" y2="{y_de(media):.1f}" class="media"></line>'
          f'<text x="{L + 4}" y="{y_de(media) - 5:.1f}" class="lab">media 2012-2025: {num(media)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" class="graf" role="img" aria-label="Focos de calor en la puna por año">{s}</svg>'


# ---------------------------------------------------------------------------------------------
# Textos y tablas
# ---------------------------------------------------------------------------------------------
ha26 = focos_r["hectareas"]
nf = lluvia[lluvia.enso == "Niño fuerte"]
reg = rec["regresion"]
pl = {r["lluvia"]: r for r in rec["por_lluvia"]}
p_rec = proy["p_sin_recuperar_por_lluvia"]
seca, normal = "Seca (< −15 %)", "Normal (±15 %)"
alta = dist[dist.prioridad == "Alta"]


def fila_tabla(r):
    vp = "—" if pd.isna(r.veces_promedio) else f"{num(r.veces_promedio, 1)}×"
    rec_ = '<span class="chip">récord</span>' if r.record else ""
    return (f'<tr data-u="{int(r.ubigeo)}"><td><b>{esc(r.NOMBDIST.title())}</b><span class="sub">{esc(r.NOMBPROV.title())}, {esc(r.NOMBDEP.title())}</span></td>'
            f'<td class="n">{num(r.focos_2026)} {rec_}</td><td class="n">{vp}</td><td class="n">{num(r.ha_est_2026)}</td>'
            f'<td class="n">{pct(r.anom_nino_fuerte)}</td><td class="n">{num(r.ha_sin_recuperar_jul2027)}</td>'
            f'<td class="n">{num(r.pob_puna)}</td></tr>')


tabla_alta = "".join(fila_tabla(r) for _, r in alta.head(20).iterrows())
media_d = dist[dist.prioridad == "Media"].head(12)
tabla_media = "".join(fila_tabla(r) for _, r in media_d.iterrows())

datos = {"info": info}
(SALIDAS / "web_datos.json").write_text(json.dumps({"kpis": {
    "focos_2026": focos_r["focos_puna_2026"], "veces": focos_r["veces_la_media"],
    "ha_2026": ha26["ha_puna_2026_central"], "ha_rango": ha26["ha_puna_2026_rango"],
    "lluvia_nino_fuerte": round(float(nf.anomalia_pct.mean()), 1),
    "ha_sin_recuperar": proy["ha_sin_recuperar_jul2027_total"],
    "ha_sin_recuperar_normal": proy["ha_sin_recuperar_si_normal_total"]}}, ensure_ascii=False, indent=1))

plantilla = (AQUI / "plantilla_web.html").read_text(encoding="utf-8")
reemplazos = {
    "{{FECHA}}": "24 de octubre de 2026",
    "{{VENTANA}}": focos_r["ventana"],
    "{{FOCOS_2026}}": num(focos_r["focos_puna_2026"]),
    "{{VECES}}": num(focos_r["veces_la_media"], 1),
    "{{RANGO_2026}}": f'{focos_r["rango_2026"]}.º',
    "{{MEDIA_FOCOS}}": num(focos_r["media_2012_2025"]),
    "{{DIST_RECORD}}": num(focos_r["distritos_record"]),
    "{{DIST_FOCOS}}": num(focos_r["distritos_con_focos_2026"]),
    "{{HA_2026}}": num(round(ha26["ha_puna_2026_central"], -2)),
    "{{HA_2026_LO}}": num(round(ha26["ha_puna_2026_rango"][0], -2)),
    "{{HA_2026_HI}}": num(round(ha26["ha_puna_2026_rango"][1], -2)),
    "{{HA_JUL_AGO}}": num(ha26["ha_mcd64_jul_ago_2026"]),
    "{{HA_POR_FOCO}}": num(ha26["ha_por_foco_mediana"], 1),
    "{{LLUVIA_NF}}": pct(nf.anomalia_pct.mean()),
    "{{LLUVIA_8283}}": pct(float(nf[nf.anio_fuego == 1982].anomalia_pct.iloc[0])),
    "{{LLUVIA_9192}}": pct(float(nf[nf.anio_fuego == 1991].anomalia_pct.iloc[0])),
    "{{LLUVIA_1516}}": pct(float(nf[nf.anio_fuego == 2015].anomalia_pct.iloc[0])),
    "{{LLUVIA_9798}}": pct(float(nf[nf.anio_fuego == 1997].anomalia_pct.iloc[0])),
    "{{LLUVIA_2324}}": pct(float(nf[nf.anio_fuego == 2023].anomalia_pct.iloc[0])),
    "{{HA_SIN_REC}}": num(round(proy["ha_sin_recuperar_jul2027_total"], -2)),
    "{{HA_SIN_REC_NORMAL}}": num(round(proy["ha_sin_recuperar_si_normal_total"], -2)),
    "{{P_SECA}}": pct(100 * p_rec.get(seca, np.nan), signo=False),
    "{{P_NORMAL}}": pct(100 * p_rec.get(normal, np.nan), signo=False),
    "{{P_HUMEDA}}": pct(100 * p_rec.get("Húmeda (> +15 %)", np.nan), signo=False),
    "{{EVENTOS}}": num(rec["eventos_analizados"]),
    "{{EVENTOS_TOTAL}}": num(rec["eventos_total"]),
    "{{HA_EVENTOS}}": num(round(rec["ha_eventos"], -3)),
    "{{N_TEMPORADAS}}": str(len(rec["temporadas"])),
    "{{CICATRIZ}}": num(rec["cicatriz_media"], 2).replace("-", "−"),
    "{{NDVI_LL1}}": num(rec["ndvi_lluvia1_medio"], 3).replace("-", "−"),
    "{{PLACEBO}}": num(rec["placebo_medio"], 3).replace("-", "−"),
    "{{COEF_SECA1}}": num(reg["d_seca1"]["coef_por_10pct_lluvia"], 4).replace("-", "−"),
    "{{IC_SECA1}}": " a ".join(num(v, 4).replace("-", "−") for v in reg["d_seca1"]["ic95"]),
    "{{P_SECA1}}": num(reg["d_seca1"]["p"], 3),
    "{{COEF_LL1}}": num(reg["d_lluvia1"]["coef_por_10pct_lluvia"], 4).replace("-", "−"),
    "{{IC_LL1}}": " a ".join(num(v, 4).replace("-", "−") for v in reg["d_lluvia1"]["ic95"]),
    "{{P_LL1}}": num(reg["d_lluvia1"]["p"], 3),
    "{{RHO_FOCOS}}": num(rec["temporada_siguiente"]["spearman_lluvia_previa_vs_focos"], 2).replace("-", "−"),
    "{{RHO_HA}}": num(rec["temporada_siguiente"]["spearman_lluvia_previa_vs_ha"], 2).replace("-", "−"),
    "{{N_ALTA}}": num(proy["distritos_por_prioridad"].get("Alta", 0)),
    "{{N_MEDIA}}": num(proy["distritos_por_prioridad"].get("Media", 0)),
    "{{N_BAJA}}": num(proy["distritos_por_prioridad"].get("Baja", 0)),
    "{{ALTA_HA}}": num(round(proy["alta"]["ha_est_2026"], -1)),
    "{{ALTA_SIN_REC}}": num(round(proy["alta"]["ha_sin_recuperar_jul2027"], -1)),
    "{{ALTA_POB}}": num(round(proy["alta"]["pob_puna"], -2)),
    "{{POB_PUNA_FUEGO}}": num(round(proy["pob_puna_distritos_con_fuego"], -3)),
    "{{HA_PUNA}}": num(round(malla_r["ha_puna"] / 1e6, 1), 1),
    "{{TABLA_ALTA}}": tabla_alta,
    "{{TABLA_MEDIA}}": tabla_media,
    "{{MAPA}}": mapa_svg,
    "{{G_LLUVIA}}": grafico_lluvia(),
    "{{G_INDICES}}": grafico_indices(),
    "{{G_RECUPERACION}}": grafico_recuperacion(),
    "{{G_FOCOS}}": grafico_focos(),
    "{{DATOS}}": json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
}
ch = proy["chichas"]
for y in ("2002", "2013"):
    h = ch["historia"].get(y, {})
    for k_ in ("ha", "cicatriz", "d_lluvia1", "d_seca1", "d_lluvia2", "anom_lluvia1"):
        v = h.get(k_)
        reemplazos[f"{{{{CH_{y}_{k_.upper()}}}}}"] = "—" if v is None else (
            num(v) if k_ == "ha" else pct(v) if k_ == "anom_lluvia1" else num(v, 2).replace("-", "−"))
    reemplazos[f"{{{{CH_{y}_ENSO}}}}"] = h.get("enso") or "—"
c26 = ch.get("2026", {})
reemplazos["{{CH_2026_FOCOS}}"] = num(c26.get("focos_2026", 0))
reemplazos["{{CH_2026_PRIOR}}"] = c26.get("prioridad", "—")
reemplazos["{{CH_2026_LLUVIA}}"] = pct(c26.get("anom_nino_fuerte", np.nan))
reemplazos["{{CH_2026_SINREC}}"] = num(c26.get("ha_sin_recuperar_jul2027", 0))

pagina = plantilla
for k_, v in reemplazos.items():
    pagina = pagina.replace(k_, v)
faltan = [p for p in set(__import__("re").findall(r"\{\{[A-Z0-9_]+\}\}", pagina))]
assert not faltan, f"marcadores sin reemplazar: {faltan}"
(AQUI / "web.html").write_text(pagina, encoding="utf-8")
print("web.html:", round(len(pagina.encode()) / 1e6, 2), "MB")
