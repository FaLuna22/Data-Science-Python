# Puna quemada, año de Niño

**Pregunta:** si El Niño 2026-27 trae sequía al sur andino, ¿se recuperará el pajonal que ardió
en la temporada de fuego 2026? ¿Qué distritos llegarán a la temporada de fuego de 2027 con
menos pasto?

Tarea de la sesión 14 (incendios en el Perú) · proyecto propio que cruza los retos C, D, E y F.
Sigue a mi tarea de Chichas (`tareas/07-raster-incendio-chichas` en la rama
`tarea-07-raster-chichas`): de un incendio y un distrito paso a toda la puna del sur y a 25
años de quemas.

**Web (parte de situación):** https://claude.ai/artifact/TpqwJD9JvX5BeWx9DvsrSQ · local: [`web.html`](web.html)

## Respuesta corta

Casi todo se recupera, pero más lento si el verano es seco. El pajonal quemado suele volver a
su nivel en dos veranos. Con lluvia escasa, **el doble** llega a la siguiente temporada de fuego
con la cicatriz a medias: 13,9 % de lo quemado frente a 6,5 % con lluvia normal. Aplicado a las
≈ 29 100 ha de puna quemadas en 2026 y a la lluvia de los Niños fuertes, son **≈ 3 400 ha con
menos pasto en julio de 2027**, en vez de ≈ 1 900. **44 distritos** (18 en Cusco, 16 en Puno,
5 en Arequipa, 3 en Apurímac y 2 en Ayacucho) cumplen los tres criterios de prioridad.

## Cifras clave

| Indicador | Valor |
|---|---:|
| Puna del sur andino (≥ 3 800 m, pajonal/matorral/bofedal/musgo) | 11,8 millones de ha |
| Focos VIIRS S-NPP en la puna, 1 jul – 23 oct 2026 | **3 032** (media 2012-2025: 1 810; 3.er año más alto) |
| Distritos con récord de focos desde 2012 | 46 de 273 |
| Puna quemada 2026 (MCD64A1 jul–ago + 8,1 ha/foco set–oct) | ≈ 29 100 ha (25 300 – 35 600) |
| Lluvia dic–mar en los 5 Niños fuertes desde 1981 | −24 % (de −54 % en 1982-83 a +2 % en 2023-24) |
| Píxeles quemados seguidos (2002-2025) | 21 138 (≈ 454 000 ha); 13 814 con cicatriz clara |
| Cicatriz NBR 1-2 meses después / placebo del año previo | −0,192 / +0,003 |
| Llegan a jul–set siguiente con ≥ ½ de la cicatriz: verano seco / normal / húmedo | 13,9 % / 6,5 % / 5,6 % |
| … sin 2022 | 12,1 % / 5,4 % / 4,8 % |
| Spearman lluvia del verano vs Δ NBR feb–abr, entre temporadas | 0,46 (p = 0,025, n = 24) |
| Puna que llegaría sin recuperarse a jul 2027: lluvia de Niño fuerte / normal | ≈ 3 400 ha / ≈ 1 900 ha |
| Distritos prioridad alta / media / baja | 44 / 32 / 200 |

## Tres hallazgos

1. **El NDVI no ve el fuego en la puna; el NBR sí.** En la estación seca el pajonal es paja, y
   quemarlo casi no cambia el verdor. El NBR, que usa el infrarrojo de onda corta, cae −0,19.
   En la lluvia siguiente el parche quemado está *más verde* que su vecino (NDVI +0,024): es el
   rebrote tierno que buscan los pastores al quemar, pero con menos biomasa. (También probé
   MOD13A1: su regla de "NDVI máximo de 16 días" esconde el fuego por completo.)
2. **Con poca lluvia, el doble queda sin recuperar**, y al segundo verano la diferencia
   desaparece. La evidencia está entre años: con MODIS solo hay 4 veranos secos (2002-03,
   2004-05, 2015-16 y 2022-23). La regresión por píxel (+0,011 de NBR por cada 10 % más de
   lluvia) depende de 2022: sin ese año baja a +0,002 (p = 0,18), y comparando lugares de una
   misma temporada no hay efecto (p = 0,62).
3. **Importa la lluvia, no la etiqueta ENSO.** 2022 fue año Niña y, donde ardió, el verano fue
   seco (−18,6 %). En 2015-16, Niño fuerte (−17,8 %), el pajonal se recuperó bien. 1997-98 y
   2023-24 fueron Niños fuertes sin sequía en la puna. Hay que seguir la lluvia real de
   diciembre a marzo.

**Validación con mi tarea anterior:** para Chichas, el método por focos estima 154 ha en 2026;
con Sentinel-2 medí ≈ 400 ha. La estimación regional es conservadora.

## Limitaciones

- **No es un pronóstico**: la lluvia "de Niño fuerte" es la de 5 Niños pasados, y en 2 la puna no se secó.
- **El NBR no es pasto en kilos**: mide biomasa y humedad del dosel.
- **MODIS (500 m) no ve fuegos chicos**, y Planetary Computer no tiene MCD64A1 de set 2023,
  jul y nov 2024, may y ago–oct 2025 (se excluyen de la razón ha/foco; en el experimento, un
  píxel que ardió esos meses puede quedar como control).
- **Set–oct 2026 es estimado** con la mediana de ha por foco (2012-2024; rango p25–p75).
- **WorldPop subcuenta a los pastores** (estancias dispersas). No encontré alpacas por distrito en
  formato abierto: CENAGRO 2012 solo publica tablas en PDF o microdatos.
- **WorldCover subestima los bofedales** (12 mil ha); el Mapa Nacional de Ecosistemas del MINAM es mejor.

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
