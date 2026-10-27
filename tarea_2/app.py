"""Dashboard de la Tarea 2: voces y documentos peruanos, del archivo escaneado al texto buscable.

    streamlit run app.py

Solo lee los CSV que generan los notebooks: no corre OCR, ASR ni LLM en el servidor.
"""
import json
import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).resolve().parent
DATOS = RAIZ / "datos"

st.set_page_config(page_title="Voces y documentos peruanos", page_icon="🎙️", layout="wide")


@st.cache_data
def _leer(nombre: str, version: float) -> pd.DataFrame:
    ruta = DATOS / nombre
    return pd.read_csv(ruta) if ruta.exists() else pd.DataFrame()


def leer(nombre: str) -> pd.DataFrame:
    """La fecha de modificación entra en la clave de la caché: si el CSV cambia o aparece, se vuelve a leer."""
    ruta = DATOS / nombre
    return _leer(nombre, ruta.stat().st_mtime if ruta.exists() else 0.0)


docs = leer("documentos.csv")
auds = leer("transcripciones.csv")
ext = leer("extraccion_llm.csv")
metricas = leer("metricas_modelos.csv")
detalle = leer("metricas_detalle.csv")
auditoria = leer("auditoria_llm.csv")
fuentes = leer("fuentes.csv")
campos = {r.id: json.loads(r.campos_json) for r in ext.itertuples()} if len(ext) else {}

# ───────────────────────────────────────────────────────── encabezado
st.title("¿Podemos convertir documentos escaneados y entrevistas en audio en texto estructurado y buscable?")
st.markdown(
    "Un pipeline de IA con modelos abiertos sobre **25 documentos peruanos** (impresos, fotos de celular y manuscritos, "
    "de 1821 a 2020) y **entrevistas en español peruano**: OCR con **PaddleOCR**, transcripción con **faster-whisper** "
    "(VAD + diarización), seudonimización, extracción de campos con un **LLM local (Qwen2.5-3B)** y evaluación contra "
    "transcripciones hechas a mano. Todo el cómputo se hizo en los notebooks; esta app explora los resultados."
)

# ───────────────────────────────────────────────────────── indicadores
def metrica(modelo_contiene: str, modalidad: str):
    if metricas.empty:
        return None
    f = metricas[(metricas["modalidad"] == modalidad) & metricas["modelo"].str.contains(modelo_contiene, regex=False)]
    return None if f.empty else float(f["valor"].iloc[0])


c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Documentos procesados", len(docs))
c2.metric("Minutos de audio transcritos", f"{auds['duracion_seg'].sum() / 60:.1f}" if len(auds) else "—",
          help=f"{len(auds)} clips")
cer_e, cer_p = metrica("EasyOCR", "documentos"), metrica("PaddleOCR", "documentos")
wer_s, wer_t, wer_q = metrica("small", "audio"), metrica("turbo", "audio"), metrica("Qwen3", "audio")
if cer_e is not None:
    c3.metric("CER EasyOCR (10 docs)", f"{cer_e:.2f}", delta=f"PaddleOCR {cer_p:.2f}", delta_color="off",
              help="Tasa de error por carácter frente a transcripciones manuales. Menos es mejor.")
    c4.metric("WER faster-whisper small (10 clips)", f"{wer_s:.2f}", delta=f"turbo {wer_t:.2f} · Qwen3 {wer_q:.2f}",
              delta_color="off", help="Tasa de error por palabra frente a transcripciones manuales. Menos es mejor.")
else:
    c3.metric("CER (10 docs)", "pendiente")
    c4.metric("WER (10 clips)", "pendiente")
if len(auditoria):
    ok = int(auditoria["completamente_correcta"].sum())
    c5.metric("Acuerdo LLM vs. auditoría humana", f"{ok / len(auditoria):.0%}", help=f"{ok}/{len(auditoria)} extracciones completamente correctas")
else:
    c5.metric("Acuerdo LLM vs. auditoría humana", "pendiente")

tab_res, tab_docs, tab_aud, tab_mod, tab_fue = st.tabs(
    ["📊 Resumen", "📄 Documentos", "🎧 Audios", "⚖️ Comparar modelos", "📚 Fuentes y método"])


def resaltar(texto: str, consulta: str) -> str:
    if not consulta or not isinstance(texto, str):
        return texto if isinstance(texto, str) else ""
    return re.sub(f"({re.escape(consulta)})", r"**:orange[\1]**", texto, flags=re.I)


# ───────────────────────────────────────────────────────── resumen
with tab_res:
    a, b = st.columns(2)
    with a:
        orden = ["impreso", "foto", "manuscrito"]
        resumen = docs.groupby("tipo").agg(documentos=("id", "size"), caracteres=("n_caracteres", "median")).reindex(orden).reset_index()
        fig = px.bar(resumen, x="tipo", y="caracteres", text="documentos", color="tipo",
                     color_discrete_sequence=["#2a6f97", "#f4a261", "#8d5a97"],
                     title="Caracteres OCR por documento (mediana) · etiqueta = nº de documentos")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="caracteres (mediana)")
        st.plotly_chart(fig, use_container_width=True)
    with b:
        dur = auds.assign(fuente_corta=auds["origen"].str.replace(r"^openslr_.*", "openslr73", regex=True)
                          .str.replace(r"_\d+$", "", regex=True))
        fig = px.histogram(dur, x="duracion_seg", color="fuente_corta", nbins=15,
                           title="Duración de los clips de audio (segundos), por fuente")
        fig.update_layout(xaxis_title="segundos", yaxis_title="clips", legend_title="fuente")
        st.plotly_chart(fig, use_container_width=True)
    if len(detalle):
        err = detalle.groupby(["modalidad", "modelo", "condicion"])["error"].mean().reset_index()
        fig = px.bar(err, x="error", y="condicion", color="modelo", facet_col="modalidad", orientation="h", barmode="group",
                     title="Error por tipo de documento (CER) y por condición de grabación (WER), muestra de evaluación")
        fig.update_yaxes(matches=None, showticklabels=True)
        fig.update_xaxes(matches=None)
        fig.update_layout(height=520, yaxis_title="", legend_title="modelo")
        st.plotly_chart(fig, use_container_width=True)

# ───────────────────────────────────────────────────────── documentos
with tab_docs:
    f1, f2, f3 = st.columns([2, 2, 3])
    tipos = f1.multiselect("Tipo de documento", ["impreso", "foto", "manuscrito"], default=["impreso", "foto", "manuscrito"])
    modelos_ocr = sorted(detalle.loc[detalle["modalidad"] == "documento", "modelo"].unique()) if len(detalle) else []
    modelo_doc = f2.selectbox("Modelo (para el CER de la muestra)", modelos_ocr or ["PaddleOCR (base)"])
    consulta = f3.text_input("Buscar en los textos OCR", placeholder="p. ej. Lima, independencia, cerveza")
    vista = docs[docs["tipo"].isin(tipos)]
    if consulta:
        vista = vista[vista["texto_ocr"].fillna("").str.contains(consulta, case=False, regex=False)]
    if len(detalle):
        cer_doc = detalle[(detalle["modalidad"] == "documento") & (detalle["modelo"] == modelo_doc)].set_index("id")["error"]
        vista = vista.assign(cer_muestra=vista["id"].map(cer_doc).round(3))
    st.caption(f"{len(vista)} documentos")
    columnas = [c for c in ["id", "tipo", "fuente", "n_caracteres", "confianza_ocr", "cer_muestra", "texto_ocr"] if c in vista]
    st.dataframe(vista[columnas], use_container_width=True, hide_index=True)
    st.download_button("Descargar CSV (texto seudonimizado)", vista[columnas].to_csv(index=False).encode("utf-8"),
                       "documentos_filtrados.csv", "text/csv")

    st.divider()
    st.subheader("Explorador de documentos")
    if len(vista):
        id_doc = st.selectbox("Documento", vista["id"], format_func=lambda i: f"{i} · {docs.set_index('id').loc[i, 'tipo']} · "
                              f"{str(docs.set_index('id').loc[i, 'titulo_original'])[:70] if docs.set_index('id').loc[i, 'publicable'] else '(sin título: contiene datos personales)'}")
        d = docs.set_index("id").loc[id_doc]
        izq, der = st.columns([2, 3])
        with izq:
            if bool(d["publicable"]):
                st.image(d["imagen_url"], use_container_width=True)
                st.caption(f"[Ver en Wikimedia Commons]({d['fuente_url']}) · {d['fuente']}")
                recorte = DATOS / "ejemplos" / "recortes" / f"{id_doc}.png"
                if recorte.exists():
                    st.image(str(recorte), caption="Recorte usado en la evaluación", use_container_width=True)
            else:
                st.info("La imagen no se muestra: el documento nombra a personas particulares. "
                        "Su texto está disponible seudonimizado.")
                st.caption(d["fuente"])
        with der:
            st.markdown(f"**Modelo:** {d['modelo_ocr']} · confianza media {d['confianza_ocr']:.2f} · {d['n_lineas']} líneas")
            st.text_area("Texto OCR (seudonimizado)", d["texto_ocr"], height=260)
            if isinstance(d.get("texto_referencia"), str) and d["texto_referencia"].strip():
                st.text_area("Transcripción manual del recorte (referencia)", d["texto_referencia"], height=140)
                if len(detalle):
                    cer_id = detalle[(detalle["id"] == id_doc)][["modelo", "error", "hipotesis"]].rename(columns={"error": "CER"})
                    st.dataframe(cer_id.round(3), use_container_width=True, hide_index=True)
            if id_doc in campos:
                st.markdown("**Campos extraídos por el LLM**")
                st.json(campos[id_doc])

# ───────────────────────────────────────────────────────── audios
with tab_aud:
    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    fuentes_audio = sorted(auds["fuente"].unique())
    fuente_sel = f1.multiselect("Fuente", fuentes_audio, default=fuentes_audio)
    rango = f2.slider("Duración (s)", 0, int(auds["duracion_seg"].max()) + 1, (0, int(auds["duracion_seg"].max()) + 1))
    solo_multi = f3.checkbox("Solo clips con 2+ hablantes")
    consulta_a = f4.text_input("Buscar en las transcripciones", placeholder="p. ej. cine, Perú, fiestas")
    vista_a = auds[auds["fuente"].isin(fuente_sel) & auds["duracion_seg"].between(*rango)]
    if solo_multi:
        vista_a = vista_a[vista_a["n_hablantes"] >= 2]
    if consulta_a:
        vista_a = vista_a[vista_a["texto_asr"].fillna("").str.contains(consulta_a, case=False, regex=False)]
    st.caption(f"{len(vista_a)} clips · {vista_a['duracion_seg'].sum() / 60:.1f} min")
    cols_a = ["id", "origen", "fuente", "duracion_seg", "n_hablantes", "n_palabras", "texto_asr"]
    st.dataframe(vista_a[cols_a], use_container_width=True, hide_index=True)
    st.download_button("Descargar CSV (texto seudonimizado)", vista_a[cols_a].to_csv(index=False).encode("utf-8"),
                       "transcripciones_filtradas.csv", "text/csv")

    st.divider()
    st.subheader("Explorador de audios")
    if len(vista_a):
        id_a = st.selectbox("Clip", vista_a["id"], format_func=lambda i: f"{i} · {auds.set_index('id').loc[i, 'origen']} · "
                            f"{auds.set_index('id').loc[i, 'duracion_seg']:.0f} s")
        a = auds.set_index("id").loc[id_a]
        izq, der = st.columns([2, 3])
        with izq:
            local = DATOS / "ejemplos" / "audio" / f"{id_a}.wav"
            if local.exists():
                st.audio(str(local))
            else:  # audio publicado en Wikimedia Commons: se reproduce desde su URL pública, desde el inicio del clip
                st.audio(a["audio_url"], start_time=int(a["inicio"]), end_time=int(a["fin"]) + 1)
            st.caption(f"Del segundo {a['inicio']:.0f} al {a['fin']:.0f} de **{a['origen']}** · {a['fuente']} · "
                       f"[fuente]({a['fuente_url']})")
            st.metric("Hablantes detectados (diarización)", int(a["n_hablantes"]))
            st.caption(f"Modelo: {a['modelo_asr']} · RTF {a['rtf_asr']:.2f}")
        with der:
            texto = a["texto_asr"]
            if int(a["n_hablantes"]) >= 2:
                st.markdown("**Transcripción por turnos**")
                for turno in re.split(r"(?=\[HABLANTE_\d+\])", texto):
                    if turno.strip():
                        st.markdown(resaltar(turno.strip(), consulta_a))
            else:
                st.markdown("**Transcripción**")
                st.markdown(resaltar(texto, consulta_a))
            if isinstance(a.get("texto_referencia"), str) and a["texto_referencia"].strip():
                st.markdown("**Transcripción manual (referencia)**")
                st.markdown(f"> {a['texto_referencia']}")
                if len(detalle):
                    comp = detalle[detalle["id"] == id_a][["modelo", "error", "segundos", "hipotesis"]].rename(columns={"error": "WER"})
                    st.markdown("**Comparación de modelos en este clip**")
                    st.dataframe(comp.round(3), use_container_width=True, hide_index=True)
            if id_a in campos:
                st.markdown("**Campos extraídos por el LLM**")
                st.json(campos[id_a])

# ───────────────────────────────────────────────────────── comparar modelos
with tab_mod:
    if metricas.empty:
        st.info("Las métricas aparecen cuando se ejecuta 02_evaluacion.ipynb.")
    else:
        st.markdown("Todos los modelos se evaluaron sobre **los mismos 10 recortes de documentos y 10 clips**, con "
                    "referencias transcritas a mano y la misma normalización.")
        st.dataframe(metricas, use_container_width=True, hide_index=True)
        mod = st.radio("Modalidad", ["documento", "audio"], horizontal=True)
        d = detalle[detalle["modalidad"] == mod]
        fig = px.strip(d, x="error", y="modelo", color="condicion", hover_data=["id"],
                       title=("CER por documento de la muestra" if mod == "documento" else "WER por clip de la muestra"))
        fig.update_traces(marker_size=11)
        fig.update_layout(xaxis_title="error (menos es mejor)", yaxis_title="", legend_title="tipo / condición")
        st.plotly_chart(fig, use_container_width=True)
    if len(auditoria):
        st.subheader("Auditoría humana de la extracción con LLM")
        campos_ok = auditoria.filter(like="ok_").mean().rename(lambda c: c[3:]).sort_values().reset_index()
        campos_ok.columns = ["campo", "proporción correcta"]
        fig = px.bar(campos_ok, x="proporción correcta", y="campo", orientation="h", range_x=[0, 1],
                     title="Qué campos acierta el LLM (20 extracciones auditadas a mano)")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(auditoria.loc[~auditoria["completamente_correcta"].astype(bool), ["id", "modalidad", "errores"]],
                     use_container_width=True, hide_index=True)

# ───────────────────────────────────────────────────────── fuentes
with tab_fue:
    st.markdown("""
**Método.** Documentos: PaddleOCR 3.7 (PP-OCRv6, `lang="es"`, CPU). Audio: VAD Silero → faster-whisper `small` (CPU, int8)
→ diarización con huellas de voz WeSpeaker y clustering → exportación a CSV/SRT/TXT. Seudonimización: lista revisada a mano
de personas particulares + reemplazo difuso y borrado de DNI, teléfonos y correos. Extracción: Qwen2.5-3B-Instruct local con
prompt JSON estricto (`null` si el dato no aparece). Evaluación: CER/WER contra transcripciones manuales de 10 documentos y
10 clips; auditoría humana de 20 extracciones.

**Datos personales.** Las imágenes de documentos que nombran a personas particulares no se muestran; su texto se publica
seudonimizado. Los audios se reproducen desde Wikimedia Commons, donde fueron publicados por sus autores con licencia libre.
""")
    st.dataframe(fuentes, use_container_width=True, hide_index=True)
