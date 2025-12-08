import streamlit as st
import sys, os

# permitir importar funciones desde el archivo principal
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app import (
    _argentina_now_global, segundos_a_hms, parse_float_or_zero,
    cargar_todo, cargar_resumen_marcas, cargar_semana,
    USERS, TIME_ROW, SHEET_MARCAS, hms_a_minutos, parse_datetime,
    sheets_batch_get
)

# Detectar usuario vía URL: ?u=ivan o ?u=facundo
params = st.query_params
u = params.get("u", "").lower()

if u in ["facu", "facundo", "f"]:
    USUARIO = "Facundo"
elif u in ["ivan", "iván", "i"]:
    USUARIO = "Iván"
else:
    st.set_page_config(page_title="Widget Estudio", page_icon="⏳")
    st.title("Widget de Estudio")
    st.error("Falta especificar el usuario. Usá por ejemplo: `?u=facundo` o `?u=ivan`")
    st.stop()

st.set_page_config(
    page_title=f"Widget Hoy — {USUARIO}",
    page_icon="⏳",
    layout="centered"
)

st.title(f"⏳ Hoy — {USUARIO}")


def calcular_metricas(usuario):
    resumen = cargar_resumen_marcas()
    datos = cargar_todo()
    per_min = parse_float_or_zero(resumen[usuario].get("per_min", ""))
    total_min = 0

    for materia, info in USERS[usuario].items():
        base = hms_a_minutos(datos[usuario]["tiempos"][materia])
        progreso = 0

        est_raw = datos[usuario]["estado"][materia]
        if str(est_raw).strip():
            try:
                inicio = parse_datetime(est_raw)
                progreso = (_argentina_now_global() - inicio).total_seconds() / 60
            except:
                pass

        total_min += base + progreso

    col = "P" if usuario == "Facundo" else "O"
    try:
        res = sheets_batch_get(st.secrets["sheet_id"], [f"'{SHEET_MARCAS}'!{col}{TIME_ROW}"])
        vr = res["valueRanges"][0]
        objetivo = parse_float_or_zero(vr["values"][0][0])
    except:
        objetivo = 0

    return total_min * per_min, per_min, objetivo, total_min


m_tot, m_rate, m_obj, total_min = calcular_metricas(USUARIO)
pago_obj = m_rate * m_obj
progreso_pct = min(m_tot / max(1, pago_obj), 1) * 100
color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

total_hms = segundos_a_hms(int(total_min * 60))
objetivo_hms = segundos_a_hms(int(m_obj * 60))

semana = cargar_semana()
if USUARIO == "Facundo":
    semana = -semana

sem_color = "#00e176" if semana > 0 else "#ff1744" if semana < 0 else "#aaa"
sem_str = f"+${semana:.2f}" if semana > 0 else f"-${abs(semana):.2f}" if semana < 0 else "$0.00"

st.markdown(f"""
<div style="background:#1e1e1e; padding:15px; border-radius:10px;">
    <div style="font-size:1.1rem; color:#aaa;">Hoy</div>

    <div style="font-size:2rem; font-weight:700; color:white;">
        {total_hms} | ${m_tot:.2f}
    </div>

    <div style="width:100%; background:#333; height:12px; border-radius:10px; margin:15px 0;">
        <div style="width:{progreso_pct}%; height:100%; background:{color_bar}; border-radius:10px;"></div>
    </div>

    <div style="display:flex; justify-content:space-between; color:#aaa;">
        <div>Semana: <span style="color:{sem_color};">{sem_str}</span></div>
        <div>{objetivo_hms} | ${pago_obj:.2f}</div>
    </div>
</div>
""", unsafe_allow_html=True)
