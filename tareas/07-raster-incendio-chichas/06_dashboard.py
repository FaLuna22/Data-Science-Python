"""Paso 6: arma dashboard.html autocontenido (datos, imágenes, Leaflet y Chart.js incrustados)."""
import json

d = json.load(open("salidas/dashboard_data.json"))
d["resumen"] = json.load(open("salidas/resultados.json"))
html = open("dashboard_plantilla.html", encoding="utf-8").read()
for marca, archivo in [("/*__LEAFLET_CSS__*/", "vendor/leaflet.css"), ("/*__LEAFLET_JS__*/", "vendor/leaflet.js"),
                       ("/*__CHART_JS__*/", "vendor/chart.umd.js")]:
    html = html.replace(marca, open(archivo, encoding="utf-8").read())
html = html.replace("/*__DATA__*/", json.dumps(d, ensure_ascii=False).replace("</", "<\\/"))
open("dashboard.html", "w", encoding="utf-8").write(html)
print(f"dashboard.html: {len(html) / 1e6:.1f} MB")
