"""Herramienta para escribir A MANO las transcripciones de referencia de la muestra de evaluación.

    .venv/Scripts/streamlit run tarea_2/herramientas/anotar_referencias.py

Muestra cada recorte de documento o clip de audio de datos/muestra_evaluacion.csv y guarda lo que
escribes en datos/referencias_manuales.csv. A propósito NO muestra la salida del OCR ni del ASR:
la referencia tiene que salir de mirar la imagen o escuchar el audio, no de corregir al modelo
(si no, el CER/WER saldría inflado a favor del modelo).

Criterio de transcripción (el mismo para todo):
- Escribe exactamente lo que se ve o se oye, con tildes y ortografía del original (también la antigua).
- Documentos: una línea del recorte por línea; palabras cortadas por el borde del recorte no se escriben.
- Audio: solo palabras habladas, sin marcas de hablante ni muletillas ("eh", "mmm").
- Lo ilegible o inaudible se marca [?] (se borra al normalizar y cuenta como error del modelo si lo inventa).
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
MUESTRA = RAIZ / "datos" / "muestra_evaluacion.csv"
SALIDA = RAIZ / "datos" / "referencias_manuales.csv"

st.set_page_config(page_title="Referencias manuales", layout="wide")
st.title("Transcripción manual de la muestra de evaluación")
st.caption("Escribe lo que ves o escuchas. La salida de los modelos se oculta a propósito.")

muestra = pd.read_csv(MUESTRA)
hechas = pd.read_csv(SALIDA) if SALIDA.exists() else pd.DataFrame(columns=["id", "modalidad", "texto_referencia", "fecha", "nota"])
listas = set(hechas.loc[hechas["texto_referencia"].fillna("").str.strip() != "", "id"])

st.progress(len(listas) / len(muestra), text=f"{len(listas)} de {len(muestra)} listas")
etiqueta = lambda i: ("✅ " if i in listas else "⬜ ") + i
id_ = st.sidebar.radio("Elemento", muestra["id"], format_func=etiqueta)
fila = muestra.set_index("id").loc[id_]
previa = hechas.set_index("id")["texto_referencia"].get(id_, "") if id_ in set(hechas["id"]) else ""

izq, der = st.columns([3, 2])
with izq:
    if fila["modalidad"] == "documento":
        st.image(str(RAIZ / fila["archivo_eval"]), use_container_width=True)
    else:
        inicio = int(fila.get("inicio", 0) or 0)
        st.audio(str(RAIZ / fila["archivo_eval"]))
        st.caption(f"Duración del clip: {fila['duracion_seg']:.0f} s. Puedes repetirlo las veces que necesites.")
        if isinstance(fila.get("texto_oficial"), str) and fila["texto_oficial"]:
            st.info("Frase de OpenSLR 73: el corpus trae una transcripción humana. Escúchala y corrígela si no "
                    "coincide con lo que se oye.\n\n" + fila["texto_oficial"])
            previa = previa or fila["texto_oficial"]
with der:
    st.subheader(id_)
    st.write(f"**Tipo:** {fila.get('tipo', '')} · **Fuente:** {fila.get('fuente', '')}")
    texto = st.text_area("Transcripción manual", value=previa, height=420, key=f"t_{id_}")
    nota = st.text_input("Nota (opcional): dudas, partes ilegibles…", key=f"n_{id_}")
    if st.button("Guardar", type="primary"):
        nuevas = hechas[hechas["id"] != id_]
        nuevas = pd.concat([nuevas, pd.DataFrame([{"id": id_, "modalidad": fila["modalidad"],
                                                    "texto_referencia": texto.strip(),
                                                    "fecha": date.today().isoformat(), "nota": nota}])])
        nuevas.sort_values("id").to_csv(SALIDA, index=False)
        st.success("Guardado")
        st.rerun()
