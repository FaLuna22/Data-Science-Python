# Puna quemada, año de Niño

**Pregunta:** si El Niño 2026-27 trae sequía al sur andino, ¿se recuperará el pajonal que ardió
en la temporada de fuego 2026? ¿Qué distritos llegarán a la temporada de fuego de 2027 con
menos pasto?

Tarea de la sesión 14 (incendios en el Perú) · proyecto propio que cruza los retos C, D, E y F.
Sigue a mi tarea de Chichas (`tareas/07-raster-incendio-chichas` en la rama
`tarea-07-raster-chichas`): de un incendio y un distrito paso a toda la puna del sur y a 25
años de quemas.

<!-- RESULTADOS -->

## Datos

| Dato | Fuente | Periodo | Uso |
|---|---|---|---|
| Área quemada | **MCD64A1** v061 (MODIS, 500 m, mensual) · Planetary Computer | nov 2000 – ago 2026 | qué píxel ardió y cuándo |
| Reflectancia | **MOD09A1** v061 (MODIS Terra, 500 m, 8 días) · Planetary Computer | feb 2000 – oct 2026 | NBR (biomasa) y NDVI (verdor) mensuales |
| Lluvia | **CHIRPS v3** (0,05°, mensual) · CHC UCSB | dic 1981 – mar 2026 | lluvia de diciembre a marzo y su anomalía |
| El Niño | **ONI** · NOAA CPC | 1950 – JAS 2026 | clasificar cada temporada |
| Focos 2012-2025 | **NASA FIRMS**, VIIRS S-NPP, archivo anual de Perú | 2012 – 2025 | serie histórica |
| Focos 2026 | **INPE Queimadas**, archivos mensuales de Sudamérica (NPP-375 y NPP-375D) | jul – 23 oct 2026 | temporada actual |
| Cobertura | **ESA WorldCover** 2021 (10 m) | 2021 | definir la puna |
| Altitud | **Copernicus DEM** GLO-90 | — | puna ≥ 3 800 m |
| Población | **WorldPop** 2026, 100 m (R2024B, *constrained*) | 2026 | personas en la puna |
| Límites | INEI, `peru_distrital_simple.geojson` (sesión 06) | — | 563 distritos de 7 departamentos |
| Contexto | ENFEN, Comunicado Oficial N.º 18-2026; SENAMHI, pronóstico estacional | oct 2026 | escenario de lluvias |

Todo se lee por HTTP sin claves. Los COG de Planetary Computer se firman con el token SAS
público de su contenedor (`comun.firmar`).

## Método

1. **`01_malla.py`** — malla MODIS sinusoidal de 500 m (21,5 ha por píxel) sobre los tiles
   h10v10 y h11v10. **Puna** = altitud media ≥ 3 800 m y al menos la mitad del píxel con
   pajonal, matorral, humedal (bofedal) o musgo según WorldCover.
2. **`02_quemas.py`** — todas las quemas MCD64A1 del sur andino, píxel por píxel.
3. **`03_nbr.py`** — NBR = (b2 − b7)/(b2 + b7) y NDVI = (b2 − b1)/(b2 + b1) de MOD09A1, sin
   nubes, sombra ni nieve (`sur_refl_state_500m`), mediana mensual.
4. **`04_clima.py`** — lluvia de diciembre a marzo con CHIRPS en cada píxel de puna, anomalía
   frente a 1991-2020, y clase ENSO de cada temporada (ONI de DEF: Niño fuerte ≥ 1,5).
5. **`05_focos.py`** — focos VIIRS S-NPP en la puna, 1 jul – 23 oct de cada año. Comparo FIRMS e
   INPE en 2025. Hectáreas 2026 = MCD64A1 jul–ago + mediana histórica de ha por foco × focos set–oct.
6. **`06_recuperacion.py`** — el experimento natural (ver abajo).
7. **`07_proyeccion.py`** — probabilidad de no recuperarse según la lluvia, aplicada a lo que
   ardió en 2026 con la lluvia de los 5 Niños fuertes; población WorldPop; prioridad por distrito.
8. **`08_web.py`** — la web (`web.html`), con mapa y gráficos en SVG, sin librerías.

### El experimento natural

Cada **evento** es un píxel de puna que ardió entre julio y diciembre del año Y (2002-2025),
sin quemas en los 3 años previos. Su **control** es la mediana de los píxeles de puna que no
ardieron entre Y−3 e Y+3, en la misma celda de 0,25° y la misma franja de 200 m de altitud.

    Δ(t) = [NBR quemado − NBR control](t) − [lo mismo, mismo mes del año, en los 2 años previos]

Es una diferencia en diferencias: la sequía que golpea a todo el pajonal y la estacionalidad
de cada sitio se restan, y lo que queda es lo que agrega el fuego. Δ = 0 es "recuperado".
Con el año Y−2 como base, el año Y−1 (sin fuego) sirve de **placebo** y debe dar Δ ≈ 0.

Mido Δ en cinco momentos: la cicatriz (1-2 meses después), febrero-abril del año siguiente
(primer rebrote), julio-setiembre (arranque de la siguiente temporada de fuego) y los mismos
dos tramos un año después. Luego cruzo Δ con la lluvia de diciembre a marzo que siguió al fuego
en ese mismo píxel, con una regresión que controla la profundidad de la cicatriz, la altitud y
el departamento, y errores agrupados por temporada.

## Reproducir

Con el entorno del curso (`uv sync --group raster --group geo`):

```bash
cd tareas/14-puna-quemada-nino
uv run python 01_malla.py && uv run python 02_quemas.py
uv run python 03_nbr.py          # ~1 h: 1 192 compuestos MOD09A1
uv run python 04_clima.py && uv run python 05_focos.py
uv run python 06_recuperacion.py && uv run python 07_proyeccion.py && uv run python 08_web.py
```

Las descargas pesadas quedan en `datos/` (no va al repo); los resultados livianos en `salidas/`.
