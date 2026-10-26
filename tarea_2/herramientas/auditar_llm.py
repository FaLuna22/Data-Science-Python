"""Auditoría humana de 20 extracciones del LLM (10 documentos y 10 audios elegidos al azar).

    .venv/Scripts/streamlit run tarea_2/herramientas/auditar_llm.py

Para cada extracción se muestra el texto fuente (OCR o ASR, ya seudonimizado) y los campos que devolvió el LLM.
Marca cada campo como correcto o incorrecto según estos criterios:

- Correcto: el valor está sustentado en el texto, o es null y el dato de verdad no aparece en el texto.
- Incorrecto: el valor no aparece en el texto (inventado o deducido), contradice el texto, o es null cuando el
  dato sí aparece claramente.
- tema / resumen: correctos si describen fielmente el texto, sin agregar hechos que no están.
- citas_clave: correctas solo si son frases copiadas del texto (se aceptan diferencias de puntuación).

Una extracción es "completamente correcta" cuando todos sus campos lo son. Se guarda en datos/auditoria_llm.csv.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"
SALIDA = DATOS / "auditoria_llm.csv"

st.set_page_config(page_title="Auditoría LLM", layout="wide")
st.title("Auditoría humana de la extracción con LLM")
st.caption("Compara cada campo con el texto. Ante la duda, un dato que no está escrito en el texto es incorrecto.")

muestra = pd.read_csv(DATOS / "muestra_auditoria.csv")
ext = pd.read_csv(DATOS / "extraccion_llm.csv").set_index("id")
textos = pd.concat([pd.read_csv(DATOS / "documentos.csv").set_index("id")["texto_ocr"],
                    pd.read_csv(DATOS / "transcripciones.csv").set_index("id")["texto_asr"]])
hechas = pd.read_csv(SALIDA) if SALIDA.exists() else pd.DataFrame(columns=["id"])
listas = set(hechas["id"])

st.progress(len(listas) / len(muestra), text=f"{len(listas)} de {len(muestra)} auditadas")
id_ = st.sidebar.radio("Extracción", muestra["id"], format_func=lambda i: ("✅ " if i in listas else "⬜ ") + i)
campos = json.loads(ext.loc[id_, "campos_json"])

izq, der = st.columns(2)
with izq:
    st.subheader(f"Texto fuente · {id_}")
    st.text_area("texto", textos.get(id_, ""), height=600, disabled=True, label_visibility="collapsed")
with der:
    st.subheader("Campos del LLM")
    previas = hechas.set_index("id").loc[id_] if id_ in listas else None
    juicios = {}
    for k, v in campos.items():
        if k == "modalidad":
            continue
        st.markdown(f"**{k}**: `{json.dumps(v, ensure_ascii=False)}`")
        anterior = previas.get(f"ok_{k}") if previas is not None else None
        juicios[k] = st.radio(k, ["correcto", "incorrecto"], horizontal=True, key=f"{id_}_{k}",
                              index=0 if anterior in (None, True, "True") else 1, label_visibility="collapsed")
    error = st.text_input("Si hay errores, descríbelos brevemente", key=f"{id_}_err",
                          value=(previas.get("errores") if previas is not None and isinstance(previas.get("errores"), str) else ""))
    if st.button("Guardar", type="primary"):
        fila = {"id": id_, "modalidad": ext.loc[id_, "modalidad"], "fecha": date.today().isoformat(),
                **{f"ok_{k}": j == "correcto" for k, j in juicios.items()},
                "completamente_correcta": all(j == "correcto" for j in juicios.values()), "errores": error}
        nuevas = pd.concat([hechas[hechas["id"] != id_], pd.DataFrame([fila])])
        nuevas.to_csv(SALIDA, index=False)
        st.success("Guardado")
        st.rerun()
