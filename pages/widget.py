import streamlit as st
from datetime import datetime
from estudio_streamlit_app import (
    _argentina_now_global,
    hms_a_segundos, segundos_a_hms, parse_float_or_zero,
    cargar_todo, cargar_resumen_marcas, cargar_semana, calcular_metricas,
    USERS, SHEET_MARCAS, TIME_ROW
)

st.set_page_config(page_title="Hoy", page_icon="⏳", layout="centered")

st.title("⏳ Hoy")

# cargar datos
datos = cargar_todo()
resumen_marcas = cargar_resumen_marcas()
USUARIO = "Facundo"   # o autodetectar si querés

# métricas
m_tot, m_rate, m_obj, total_min = calcular_metricas(USUARIO)
pago_objetivo = m_rate * m_obj
progreso_pct = min(m_tot / max(1, pago_objetivo), 1.0) * 100
color_bar = "#00e676" if progreso_pct >= 90 else "#ffeb3b" if progreso_pct >= 50 else "#ff1744"

objetivo_hms = segundos_a_hms(int(m_obj * 60))
total_hms = segundos_a_hms(int(total_min * 60))

semana_val = cargar_semana()
if USUARIO == "Facundo":
    semana_val = -semana_val

semana_color = "#00e676" if semana_val > 0 else "#ff1744" if semana_val < 0 else "#aaa"
semana_str = f"{'+' if semana_val>0 else ''}${semana_val:.2f}"

# render
st.markdown(f"""
    <div style="background-color: #1e1e1e; padding: 15px; border-radius: 10px;">
        <div style="font-size: 1.2rem; color: #aaa; margin-bottom: 5px;">Hoy</div>
        <div style="font-size: 2.2rem; font-weight: bold; color: #fff;">{total_hms} | ${m_tot:.2f}</div>
        <div style="width:100%; background-color:#333; border-radius:10px; height:12px; margin: 15px 0;">
            <div style="width:{progreso_pct}%; background-color:{color_bar}; height:100%; border-radius:10px;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; color:#888;">
            <div>Semana: <span style="color:{semana_color};">{semana_str}</span></div>
            <div>{objetivo_hms} | ${pago_objetivo:.2f}</div>
        </div>
    </div>
""", unsafe_allow_html=True)
