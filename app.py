import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Panel de Transporte CABA",
    page_icon="🚌",
    layout="wide",
)

st.title("Panel de Visualización de Transporte")
st.subheader("Ciudad Autónoma de Buenos Aires - Monitoreo en tiempo real")

m = folium.Map(
    location=[-34.6037, -58.3816],
    zoom_start=12,
    tiles="OpenStreetMap",
)

st_folium(m, width="100%", height=600)
