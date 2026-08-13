import streamlit as st
import asyncio
import hashlib
import json
import pandas as pd

import datetime
import libsql_client as libsql
import re

# Intentar importar Plotly para gráficos avanzados (fallback a gráficos nativos de Streamlit si no está instalado)
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Intentar importar Cloudinary para carga directa
try:
    import cloudinary
    import cloudinary.uploader
    HAS_CLOUDINARY = True
except ImportError:
    HAS_CLOUDINARY = False

# Intentar importar streamlit-js-eval para geolocalización GPS
try:
    from streamlit_js_eval import get_geolocation
    HAS_GEOLOCATION = True
except ImportError:
    HAS_GEOLOCATION = False

def draw_bar_chart(df, x_col, y_col, title, color_scale="Reds"):
    if HAS_PLOTLY:
        fig = px.bar(df, x=x_col, y=y_col, title=title, color=y_col, color_continuous_scale=color_scale)
        fig.update_layout(template="plotly_dark", height=380)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown(f"#### {title}")
        chart_df = df.set_index(x_col)[[y_col]]
        st.bar_chart(chart_df)

def draw_pie_chart(df, names_col, values_col, title):
    if HAS_PLOTLY:
        fig = px.pie(df, names=names_col, values=values_col, title=title, hole=0.4)
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown(f"#### {title}")
        chart_df = df.set_index(names_col)[[values_col]]
        st.bar_chart(chart_df)

# ---------------------------------------------------------
# FUNCIONES HELPER PARA FORMATO DE FECHA Y BADGES
# ---------------------------------------------------------
MONTHS_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

def format_date_str(date_val, lang: str = "es") -> str:
    """Convierte cualquier fecha al formato localizado.
    ES: dd/mmm/YYYY  (ej. 24/Jun/2026)
    EN: mmm dd, YYYY (ej. Jun 24, 2026)
    """
    if not date_val or pd.isna(date_val):
        return "N/A"
    
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        d = date_val
    else:
        s = str(date_val).strip()
        try:
            d = datetime.datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            try:
                d = datetime.datetime.strptime(s[:10], "%Y-%m-%d").date()
            except Exception:
                return s

    if lang == "en":
        month_abbr = MONTHS_EN[d.month - 1]
        return f"{month_abbr} {d.day:02d}, {d.year}"
    else:
        month_abbr = MONTHS_ES[d.month - 1]
        return f"{d.day:02d}/{month_abbr}/{d.year}"

def format_date_range(desde_val, hasta_val, lang: str = "es") -> str:
    """Formatea un rango de fechas con localización.
    Si son iguales retorna la fecha formateada.
    ES: 'Del {desde} al {hasta}'
    EN: 'From {desde} to {hasta}'
    """
    if not desde_val or pd.isna(desde_val):
        return format_date_str(hasta_val, lang)
    if not hasta_val or pd.isna(hasta_val):
        return format_date_str(desde_val, lang)
    
    desde_str = format_date_str(desde_val, lang)
    hasta_str = format_date_str(hasta_val, lang)
    
    if desde_str == hasta_str:
        return desde_str
    if lang == "en":
        return f"From {desde_str} to {hasta_str}"
    return f"Del {desde_str} al {hasta_str}"

def parse_delimited_list(text_str: str) -> list:
    """Extrae una lista de elementos reconociendo separadores (, ; .)."""
    if not text_str or pd.isna(text_str) or not str(text_str).strip():
        return []
    raw = str(text_str).strip()
    return [p.strip() for p in re.split(r'[,;.]', raw) if p.strip()]

def parse_pastores_list(pastores_str: str) -> list:
    """Extrae la lista de pastores reconociendo separadores (, ; .) y preservando títulos abreviados."""
    if not pastores_str or pd.isna(pastores_str) or not str(pastores_str).strip():
        return []
    
    raw = str(pastores_str).strip()
    raw_parts = [p.strip() for p in re.split(r'[,;.]', raw) if p.strip()]
    
    titles = {"pr", "ptra", "pastor", "pastora", "dr", "dra", "lic", "rev"}
    items = []
    i = 0
    while i < len(raw_parts):
        part = raw_parts[i]
        if part.lower() in titles and i + 1 < len(raw_parts):
            items.append(f"{part}. {raw_parts[i+1]}")
            i += 2
        else:
            items.append(part)
            i += 1
    return items

def render_pastores_badges(pastores_str: str) -> str:
    """Genera HTML con badges de distintos colores para cada pastor a cargo."""
    pastores = parse_pastores_list(pastores_str)
    if not pastores:
        return "<span style='color:#94A3B8;'>N/A</span>"
    
    colors = [
        ("rgba(99, 102, 241, 0.2)", "#818CF8", "rgba(99, 102, 241, 0.4)"),   # Indigo
        ("rgba(16, 185, 129, 0.2)", "#34D399", "rgba(16, 185, 129, 0.4)"),   # Esmeralda
        ("rgba(245, 158, 11, 0.2)", "#FBBF24", "rgba(245, 158, 11, 0.4)"),   # Ámbar
        ("rgba(236, 72, 153, 0.2)", "#F472B6", "rgba(236, 72, 153, 0.4)"),   # Rosado
        ("rgba(14, 165, 233, 0.2)", "#38BDF8", "rgba(14, 165, 233, 0.4)"),   # Azul Celeste
        ("rgba(168, 85, 247, 0.2)", "#C084FC", "rgba(168, 85, 247, 0.4)"),   # Púrpura
        ("rgba(239, 68, 68, 0.2)",  "#F87171", "rgba(239, 68, 68, 0.4)"),   # Rojo
    ]
    
    badges_html = []
    for idx, pastor in enumerate(pastores):
        bg, text_color, border = colors[idx % len(colors)]
        badge = f'<span style="display:inline-block; background-color: {bg}; color: {text_color}; border: 1px solid {border}; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; margin: 2px 4px 4px 0px;">👤 {pastor}</span>'
        badges_html.append(badge)
        
    return " ".join(badges_html)

def render_ayudas_badges(ayudas_str: str) -> str:
    """Genera HTML con badges de distintos colores para cada ayuda entregada, separando por coma, punto y coma, o punto."""
    items = parse_delimited_list(ayudas_str)
    if not items:
        return "<span style='color:#94A3B8;'>N/A</span>"
    
    colors = [
        ("rgba(16, 185, 129, 0.2)", "#34D399", "rgba(16, 185, 129, 0.4)"),   # Esmeralda
        ("rgba(245, 158, 11, 0.2)", "#FBBF24", "rgba(245, 158, 11, 0.4)"),   # Ámbar
        ("rgba(14, 165, 233, 0.2)", "#38BDF8", "rgba(14, 165, 233, 0.4)"),   # Azul Celeste
        ("rgba(236, 72, 153, 0.2)", "#F472B6", "rgba(236, 72, 153, 0.4)"),   # Rosado
        ("rgba(168, 85, 247, 0.2)", "#C084FC", "rgba(168, 85, 247, 0.4)"),   # Púrpura
        ("rgba(99, 102, 241, 0.2)", "#818CF8", "rgba(99, 102, 241, 0.4)"),   # Índigo
        ("rgba(239, 68, 68, 0.2)",  "#F87171", "rgba(239, 68, 68, 0.4)"),   # Rojo
    ]
    
    badges_html = []
    for idx, item in enumerate(items):
        bg, text_color, border = colors[idx % len(colors)]
        badge = f'<span style="display:inline-block; background-color: {bg}; color: {text_color}; border: 1px solid {border}; padding: 4px 10px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; margin: 2px 4px 4px 0px;">📦 {item}</span>'
        badges_html.append(badge)
        
    return " ".join(badges_html)

def extract_lat_lon(location_str: str):
    """
    Extrae valores numéricos de latitud y longitud desde una cadena de texto.
    Ejemplos de entrada: "10.480612, -66.903581", "Lat: 10.48, Lon: -66.90"
    """
    if not location_str or pd.isna(location_str):
        return None, None
    s = str(location_str).strip()
    match = re.search(r'(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)', s)
    if match:
        try:
            lat = float(match.group(1))
            lon = float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
        except ValueError:
            pass
    return None, None

def render_location_map(location_str: str, title: str = "Ubicación Geográfica"):
    """
    Muestra un mapa interactivo de Streamlit (st.map) y un enlace a Google Maps si existen coordenadas.
    Si solo hay una dirección de texto, muestra un botón directo para buscarla en Google Maps.
    """
    lat, lon = extract_lat_lon(location_str)
    if lat is not None and lon is not None:
        st.markdown(f"**📍 {title} (`{lat:.5f}, {lon:.5f}`):**")
        map_df = pd.DataFrame({'lat': [lat], 'lon': [lon]})
        st.map(map_df, zoom=13)
        gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"
        st.markdown(f'🔗 [🗺️ Abrir ubicación en Google Maps]({gmaps_url})', unsafe_allow_html=True)
    elif location_str and str(location_str).strip():
        encoded_query = str(location_str).strip().replace(" ", "+")
        gmaps_url = f"https://www.google.com/maps/search/?api=1&query={encoded_query}"
        st.markdown(f'🔗 [🗺️ Buscar "{location_str}" en Google Maps]({gmaps_url})', unsafe_allow_html=True)

# ---------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA STREAMLIT
# ---------------------------------------------------------
st.set_page_config(
    page_title="Proyecto Misericordia - Venezuela 2026",
    page_icon="🕊️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# ESTILOS CSS PERSONALIZADOS (Aesthetic Premium)
# ---------------------------------------------------------
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght=300;400;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Header Principal */
    .header-box {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 50%, #1E1B4B 100%);
        padding: 2.5rem;
        border-radius: 16px;
        color: #F8FAFC !important;
        box-shadow: 0 10px 25px -5px rgba(0,0,0,0.3);
        margin-bottom: 2rem;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .header-box h1 {
        color: #FFFFFF !important;
        font-weight: 800;
        font-size: 2.4rem;
        margin-bottom: 0.5rem;
    }
    .header-box p {
        color: #CBD5E1 !important;
        font-size: 1.1rem;
        margin-bottom: 0;
    }

    /* Cards KPI */
    .kpi-card {
        background: #1E293B !important;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        margin-bottom: 1rem;
    }
    .kpi-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 20px -5px rgba(0, 0, 0, 0.3);
    }
    .kpi-val {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38BDF8, #818CF8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .kpi-title {
        color: #E2E8F0 !important;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 4px;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        border-radius: 8px;
        font-weight: 600;
        padding: 0 20px;
    }

    /* Cards de Testimonios y Antecedentes */
    .info-card {
        background: #1E293B !important;
        border-left: 4px solid #6366F1;
        padding: 1.5rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        color: #F8FAFC !important;
    }
    .info-card p, .info-card span, .info-card li, .info-card strong, .info-card em {
        color: #F8FAFC !important;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------
# DICCIONARIO DE IDIOMAS (I18N: ESPAÑOL / ENGLISH)
# ---------------------------------------------------------
TEXTS = {
    "es": {
        "title": "🕊️ Proyecto Misericordia - Venezuela",
        "subtitle": "Consolidado de Atención Social, Apoyo Humanitario e Impacto Espiritual tras los Sismos de 2026",
        "nav_muestra": "📊 Resultados y Muestra",
        "nav_cargar": "📝 Cargar Actividad (Reportero)",
        "nav_gestionar": "⚙️ Gestionar Actividades (Editor)",
        "lang_select": "🌐 Idioma / Language",
        "login_header": "🔐 Iniciar Sesión",
        "username": "Usuario",
        "password": "Contraseña",
        "login_btn": "Ingresar",
        "logout_btn": "Cerrar Sesión",
        "logged_as": "Sesión iniciada como",
        "role": "Rol",
        "login_err": "Usuario o contraseña incorrectos",
        
        # Antecedentes y Objetivos
        "tab_antecedentes": "📜 Antecedentes",
        "tab_objetivos": "🎯 Objetivos",
        "tab_resultados": "📈 Resultados y Métricas",
        "antecedentes_title": "Emergencia Sísmica en Venezuela - 24-Jun-2026",
        "antecedentes_desc": """
        El **24-Jun-2026**, la región norte de Venezuela fue impactada por un **evento sísmico de tipo doblete** con magnitudes de **7,2 Mw** y **7,5 Mw** ocurridos con apenas 39 segundos de diferencia, registrados a profundidades entre 10 km y 20 km en las cercanías de San Felipe y Yumare (Estado Yaracuy).

        **Estadísticas e Impacto Humanitario:**
        - **Fallecidos**: Más de 5,390 personas.
        - **Heridos**: 16,740 atendidos en centros médicos.
        - **Damnificados**: Más de 17,900 personas sin hogar, reubicadas en más de 100 campamentos transitorios.
        - **Daños Estructurales**: 856 edificios gravemente afectados, incluyendo 190 colapsos totales.
        - **Zonas de Mayor Impacto**: Estado La Guaira, Caracas (Distrito Capital), Miranda, Aragua, Falcón, Carabobo y Yaracuy.
        - **Réplicas**: Más de 1,460 réplicas registradas.

        El **Proyecto Misericordia** nace como respuesta de fe y acción social coordinada para movilizar ayuda humanitaria, alimentación, vestimenta, insumos médicos y contención espiritual a las familias afectadas.
        """,
        "objetivos_title": "🎯 Objetivos del Proyecto",
        "objetivos_placeholder": "Espacio reservado para los Objetivos Estratégicos del Proyecto Misericordia.",
        
        # Pestañas de Resultados
        "subtab_alcance": "👥 Alcance",
        "subtab_participacion": "🤝 Participación",
        "subtab_testimonios": "💬 Testimonios y Multimedia",
        "subtab_tabla": "📋 Tabla de Actividades",

        # Métricas Alcance
        "kpi_total_personas": "Total Personas Atendidas",
        "kpi_conversiones": "Conversiones",
        "kpi_discipulado": "En Discipulado",
        "kpi_adultos": "Adultos Atendidos",
        "kpi_ninos": "Niños Atendidos",
        "kpi_familias": "Familias Atendidas",
        "kpi_total_actividades": "Jornadas Realizadas",
        "kpi_sectores_num": "Sectores / Municipios",
        "tipos_atencion_chart": "Distribución por Tipo de Atención",
        "ayudas_resumen_title": "📦 Resumen de Ayudas Entregadas y Cobertura",
        
        # Métricas Participación
        "kpi_iglesias": "Iglesias Participantes",
        "kpi_pastores": "Pastores y Líderes",
        "kpi_voluntarios": "Familias Voluntarias",
        "kpi_fuerza_voluntaria": "Fuerza Voluntaria Total",
        "kpi_denominaciones_num": "Denominaciones",
        "kpi_prom_voluntarios_act": "Voluntarios / Jornada",
        "kpi_prom_personas_iglesia": "Atendidos por Iglesia",

        # Formulario Carga
        "form_title": "📝 Registrar Nueva Actividad",
        "field_reportero": "Reportero / Usuario",
        "field_actividad": "Nombre de la Actividad",
        "field_fecha_desde": "Fecha Desde",
        "field_fecha_hasta": "Fecha Hasta",
        "field_lugar": "Lugar / Ciudad",
        "field_ubicacion": "Ubicación / Coordenadas / Dirección",
        "field_pastores": "Pastores a Cargo",
        "field_desc": "Descripción de la Actividad",
        "field_fotos": "Fotos / Imágenes",
        "field_videos": "Videos / Audios",
        "field_atencion": "Tipos de Atención Brindados",
        "field_sectores": "Sectores y Municipios Cubiertos",
        "field_ayudas": "Ayudas Entregadas",
        "field_denominaciones": "Denominaciones de Iglesias",
        "field_testimonios_texto": "Testimonios / Historias de Vida",
        "field_otro": "Otro (Notas o Datos Adicionales)",
        "upload_direct": "Subir Archivo Multimedia Directo",
        "url_external": "O pegar URL Externa (Google Drive, Cloudinary, YouTube...)",
        "save_btn": "💾 Guardar Actividad",
        "save_success": "¡Actividad registrada exitosamente en Turso!",
        "save_error": "Error al guardar la actividad: ",
        "export_csv": "📥 Exportar a CSV",

        # Editor / Edición completa de Testimonios
        "media_approval_title": "📸/🎬 Aprobación Individual de Fotos y Videos",
        "approve_all": "✅ Aprobar Todos",
        "disapprove_all": "❌ Desaprobar Todos",
        "save_media_status": "💾 Guardar Aprobación de Multimedia",
        "media_updated_success": "¡Aprobación de fotos y videos actualizada correctamente!",
        "edit_activity_title": "✏️ Editar Información y Contenido del Testimonio / Actividad",
        "save_edits_btn": "💾 Guardar Todos los Cambios del Testimonio",
        "edit_success": "¡Testimonio / Actividad actualizado con éxito en la base de datos!",

        # Editor / Approval & Full Edit
        "media_approval_title": "📸/🎬 Aprobación Individual de Fotos y Videos",
        "approve_all": "✅ Aprobar Todos",
        "disapprove_all": "❌ Desaprobar Todos",
        "save_media_status": "💾 Guardar Aprobación de Multimedia",
        "media_updated_success": "¡Aprobación de fotos y videos actualizada correctamente!",
        "edit_activity_title": "✏️ Editar Información y Contenido del Testimonio / Actividad",
        "save_edits_btn": "💾 Guardar Todos los Cambios del Testimonio",
        "edit_success": "¡Testimonio / Actividad actualizado con éxito en la base de datos!",
        "upload_new_media_title": "📤 Subir Nuevos Archivos Multimedia",
        "upload_new_media_btn": "📤 Subir y Agregar Multimedia a esta Actividad",
        "upload_new_media_success": "¡Nuevos archivos multimedia subidos y agregados exitosamente!",

    },
    "en": {
        "title": "🕊️ Mercy Project - Venezuela",
        "subtitle": "Consolidated Social Care, Humanitarian Support & Spiritual Impact after 2026 Earthquakes",
        "nav_muestra": "📊 Results & Summary",
        "nav_cargar": "📝 Log Activity (Reporter)",
        "nav_gestionar": "⚙️ Manage Activities (Editor)",
        "lang_select": "🌐 Language / Idioma",
        "login_header": "🔐 Login",
        "username": "Username",
        "password": "Password",
        "login_btn": "Log In",
        "logout_btn": "Log Out",
        "logged_as": "Logged in as",
        "role": "Role",
        "login_err": "Invalid username or password",
        
        # Antecedentes y Objetivos
        "tab_antecedentes": "📜 Background",
        "tab_objetivos": "🎯 Objectives",
        "tab_resultados": "📈 Results & Metrics",
        "antecedentes_title": "Seismic Emergency in Venezuela - 24-Jun-2026",
        "antecedentes_desc": """
        On **24-Jun-2026**, northern Venezuela was hit by a **doublet earthquake event** with magnitudes of **7.2 Mw** and **7.5 Mw** occurring just 39 seconds apart, registered at depths between 10 km and 20 km near San Felipe and Yumare (Yaracuy State).

        **Humanitarian Impact & Statistics:**
        - **Fatalities**: Over 5,390 people.
        - **Injured**: 16,740 treated at medical centers.
        - **Displaced**: Over 17,900 homeless individuals relocated to 100+ temporary shelters.
        - **Structural Damage**: 856 severely damaged buildings, including 190 total collapses.
        - **Most Affected Regions**: La Guaira, Caracas (Capital District), Miranda, Aragua, Falcón, Carabobo, and Yaracuy.
        - **Aftershocks**: Over 1,460 recorded aftershocks.

        The **Mercy Project** was launched as a coordinated faith and social response to provide humanitarian aid, food, clothing, medical supplies, and spiritual care to affected families.
        """,
        "objetivos_title": "🎯 Project Objectives",
        "objetivos_placeholder": "Space reserved for Strategic Objectives of the Mercy Project.",
        
        # Pestañas de Resultados
        "subtab_alcance": "👥 Reach",
        "subtab_participacion": "🤝 Involvement",
        "subtab_testimonios": "💬 Testimonies & Media",
        "subtab_tabla": "📋 Activities Table",

        # Métricas Alcance
        "kpi_total_personas": "Total People Served",
        "kpi_conversiones": "Conversions",
        "kpi_discipulado": "In Discipleship",
        "kpi_adultos": "Adults Served",
        "kpi_ninos": "Children Served",
        "kpi_familias": "Families Served",
        "kpi_total_actividades": "Activities Conducted",
        "kpi_sectores_num": "Sectors / Municipalities",
        "tipos_atencion_chart": "Breakdown by Type of Care",
        "ayudas_resumen_title": "📦 Summary of Aid Delivered & Coverage",

        # Métricas Participación
        "kpi_iglesias": "Participating Churches",
        "kpi_pastores": "Pastors & Leaders",
        "kpi_voluntarios": "Volunteering Families",
        "kpi_fuerza_voluntaria": "Total Volunteer Force",
        "kpi_denominaciones_num": "Denominations",
        "kpi_prom_voluntarios_act": "Volunteers / Activity",
        "kpi_prom_personas_iglesia": "Served per Church",

        # Formulario Carga
        "form_title": "📝 Register New Activity",
        "field_reportero": "Reporter / User",
        "field_actividad": "Activity Name",
        "field_fecha_desde": "Start Date",
        "field_fecha_hasta": "End Date",
        "field_lugar": "Location / City",
        "field_ubicacion": "GPS / Address",
        "field_pastores": "Lead Pastors",
        "field_desc": "Activity Description",
        "field_fotos": "Photos / Images",
        "field_videos": "Videos / Audios",
        "field_atencion": "Types of Care Provided",
        "field_sectores": "Sectors & Municipalities Covered",
        "field_ayudas": "Aid Delivered",
        "field_denominaciones": "Church Denominations",
        "field_testimonios_texto": "Testimonies / Life Stories",
        "field_otro": "Other (Notes or Extra Data)",
        "upload_direct": "Upload Media Directly",
        "url_external": "Or Paste External URL (Google Drive, Cloudinary, YouTube...)",
        "save_btn": "💾 Save Activity",
        "save_success": "Activity registered successfully in Turso!",
        "save_error": "Error saving activity: ",
        "export_csv": "📥 Export to CSV",

        # Editor / Approval & Full Edit
        "media_approval_title": "📸/🎬 Individual Photo and Video Approval",
        "approve_all": "✅ Approve All",
        "disapprove_all": "❌ Reject All",
        "save_media_status": "💾 Save Media Approval Status",
        "media_updated_success": "Photo & video approval status updated successfully!",
        "edit_activity_title": "✏️ Edit Testimony / Activity Information & Content",
        "save_edits_btn": "💾 Save All Testimony Changes",
        "edit_success": "Testimony / Activity updated successfully in database!",

        # Editor / Approval & Full Edit
        "media_approval_title": "📸/🎬 Individual Photo and Video Approval",
        "approve_all": "✅ Approve All",
        "disapprove_all": "❌ Reject All",
        "save_media_status": "💾 Save Media Approval Status",
        "media_updated_success": "Photo & video approval status updated successfully!",
        "edit_activity_title": "✏️ Edit Testimony / Activity Information & Content",
        "save_edits_btn": "💾 Save All Testimony Changes",
        "edit_success": "Testimony / Activity updated successfully in database!",
        "upload_new_media_title": "📤 Upload New Media Files",
        "upload_new_media_btn": "📤 Upload & Add Media to this Activity",
        "upload_new_media_success": "New media files uploaded and added successfully!",
    
    }
}

# ---------------------------------------------------------
# FUNCIONES HELPER BASE DE DATOS TURSO Y CLOUDINARY
# ---------------------------------------------------------
def get_turso_credentials():
    try:
        url = st.secrets["turso"].get("url_pmis") or st.secrets["turso"]["url"]
        token = st.secrets["turso"].get("auth_token_pmis") or st.secrets["turso"]["auth_token"]
        return url, token
    except Exception as e:
        st.error(f"Error cargando secretos de Turso: {e}")
        return None, None

def run_async(coro):
    """Ejecuta una corrutina asíncrona de forma síncrona en Streamlit."""
    return asyncio.run(coro)

async def async_fetch_all(query: str, args: list = None):
    url, token = get_turso_credentials()
    if not url:
        return []
    async with libsql.create_client(url, auth_token=token) as client:
        res = await client.execute(query, args or [])
        return res

async def async_execute(query: str, args: list = None):
    url, token = get_turso_credentials()
    if not url:
        return False
    async with libsql.create_client(url, auth_token=token) as client:
        await client.execute(query, args or [])
        return True

def fetch_data(query: str, args: list = None):
    res = run_async(async_fetch_all(query, args))
    if hasattr(res, 'rows') and hasattr(res, 'columns'):
        df = pd.DataFrame(res.rows, columns=res.columns)
        return df
    return pd.DataFrame()

def execute_query(query: str, args: list = None):
    return run_async(async_execute(query, args))

# Configurar Cloudinary si existen secretos
def init_cloudinary():
    if HAS_CLOUDINARY and "cloudinary" in st.secrets:
        try:
            cloudinary.config(
                cloud_name=st.secrets["cloudinary"]["cloud_name"],
                api_key=st.secrets["cloudinary"]["api_key"],
                api_secret=st.secrets["cloudinary"]["api_secret"],
                secure=True
            )
            return True
        except Exception:
            return False
    return False

IS_CLOUDINARY_READY = init_cloudinary()

def sanitize_folder_name(name: str) -> str:
    """Sanitiza un nombre de actividad para usarlo como carpeta en Cloudinary."""
    name = name.strip().lower()
    for src, dst in [('á','a'),('à','a'),('ä','a'),('â','a'),('é','e'),('è','e'),
                     ('ë','e'),('ê','e'),('í','i'),('ì','i'),('ï','i'),('î','i'),
                     ('ó','o'),('ò','o'),('ö','o'),('ô','o'),('ú','u'),('ù','u'),
                     ('ü','u'),('û','u'),('ñ','n'),('ç','c')]:
        name = name.replace(src, dst)
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[\s]+', '_', name)
    return name[:50]

def parse_media_urls(url_field, only_approved: bool = False) -> list:
    """
    Parsea un campo de URLs multimedia.
    Retorna una lista de dicts: [{'url': str, 'aprobado': bool}, ...]
    Si only_approved=True, retorna sólo una lista con las cadenas de URLs que han sido aprobadas por el Editor.
    """
    if not url_field:
        return []
    
    items = []
    try:
        data = json.loads(str(url_field))
        if isinstance(data, list):
            for elem in data:
                if isinstance(elem, dict):
                    u = elem.get("url", "").strip()
                    app = elem.get("aprobado", False)
                    if u:
                        items.append({"url": u, "aprobado": bool(app)})
                elif isinstance(elem, str) and elem.strip():
                    items.append({"url": elem.strip(), "aprobado": True})
        elif isinstance(data, str) and data.strip():
            items.append({"url": data.strip(), "aprobado": True})
    except Exception:
        s = str(url_field).strip()
        if s:
            items.append({"url": s, "aprobado": True})

    if only_approved:
        return [it["url"] for it in items if it.get("aprobado", False)]
    return items

def upload_media_file(uploaded_file, folder: str = None):
    """Sube un archivo cargado en Streamlit a Cloudinary y retorna la URL pública."""
    if not IS_CLOUDINARY_READY:
        return None
    try:
        file_bytes = uploaded_file.read()
        options = {"resource_type": "auto"}
        if folder:
            options["folder"] = folder
        res = cloudinary.uploader.upload(file_bytes, **options)
        return res.get("secure_url")
    except Exception as e:
        st.error(f"Error al subir a Cloudinary: {e}")
        return None

# Verificar usuario para login
def verify_login(username, password):
    pass_hash = hashlib.sha256(password.encode()).hexdigest()
    df = fetch_data("SELECT username, nombre_completo, rol FROM usuarios WHERE username = ? AND password_hash = ?", [username, pass_hash])
    if not df.empty:
        return df.iloc[0].to_dict()
    return None

# ---------------------------------------------------------
# ESTADO DE SESIÓN (SESSION STATE)
# ---------------------------------------------------------
if "lang" not in st.session_state:
    st.session_state["lang"] = "es"
if "user" not in st.session_state:
    st.session_state["user"] = None
if "gps_coords" not in st.session_state:
    st.session_state["gps_coords"] = ""
if "gps_requested" not in st.session_state:
    st.session_state["gps_requested"] = False

t = TEXTS[st.session_state["lang"]]

# ---------------------------------------------------------
# BARRA LATERAL (SIDEBAR)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🕊️ Misericordia 2026")
    
    # Selector de Idioma
    lang_choice = st.selectbox(
        t["lang_select"],
        options=["Español 🇪🇸", "English 🇬🇧"],
        index=0 if st.session_state["lang"] == "es" else 1
    )
    new_lang = "es" if "Español" in lang_choice else "en"
    if new_lang != st.session_state["lang"]:
        st.session_state["lang"] = new_lang
        st.rerun()

    st.markdown("---")

    # Autenticación / Login
    if st.session_state["user"] is None:
        st.subheader(t["login_header"])
        login_user = st.text_input(t["username"], key="login_user")
        login_pass = st.text_input(t["password"], type="password", key="login_pass")
        if st.button(t["login_btn"], use_container_width=True):
            user_data = verify_login(login_user, login_pass)
            if user_data:
                st.session_state["user"] = user_data
                st.success(f"{t['logged_as']} {user_data['nombre_completo']}")
                st.rerun()
            else:
                st.error(t["login_err"])
    else:
        u = st.session_state["user"]
        st.info(f"👤 **{u['nombre_completo']}**\n\n🔑 {t['role']}: **{u['rol'].capitalize()}**")
        if st.button(t["logout_btn"], use_container_width=True):
            st.session_state["user"] = None
            st.rerun()

    st.markdown("---")

    # Menú de Navegación
    nav_options = [t["nav_muestra"]]
    if st.session_state["user"] is not None:
        nav_options.append(t["nav_cargar"])
        if st.session_state["user"]["rol"] in ["editor", "admin"]:
            nav_options.append(t["nav_gestionar"])

    current_nav = st.radio("Navegación / Navigation", nav_options)

# ---------------------------------------------------------
# HEADER DE LA APLICACIÓN
# ---------------------------------------------------------
st.markdown(f"""
<div class="header-box">
    <h1>{t['title']}</h1>
    <p>{t['subtitle']}</p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# SECCIÓN 1: VISTA PÚBLICA / RESULTADOS Y MUESTRA
# ---------------------------------------------------------
if current_nav == t["nav_muestra"]:
    tab_antecedentes, tab_objetivos, tab_resultados = st.tabs([
        t["tab_antecedentes"],
        t["tab_objetivos"],
        t["tab_resultados"]
    ])

    # TAB ANTECEDENTES
    with tab_antecedentes:
        st.subheader(t["antecedentes_title"])
        st.markdown(f"""
        <div class="info-card">
            {t['antecedentes_desc']}
        </div>
        """, unsafe_allow_html=True)

        # Gráfico rápido de impacto de víctimas por región
        data_sismo = pd.DataFrame({
            "Región": ["La Guaira", "Caracas (Distrito Capital)", "Yaracuy (Epicentro)", "Miranda", "Aragua", "Carabobo", "Falcón"],
            "Gravedad Daño Estructural": [95, 88, 85, 78, 70, 65, 60]
        })
        draw_bar_chart(data_sismo, "Región", "Gravedad Daño Estructural", "Nivel Estimado de Daño Estructural e Impacto por Región (%)", "Reds")

    # TAB OBJETIVOS
    with tab_objetivos:
        st.subheader(t["objetivos_title"])
        st.info(t["objetivos_placeholder"])

    # TAB RESULTADOS CONSOLIDADOS
    with tab_resultados:
        df_act = fetch_data("SELECT * FROM actividades WHERE estado = 'aprobado' ORDER BY fecha_desde DESC")

        subtab1, subtab2, subtab3, subtab4 = st.tabs([
            t["subtab_alcance"],
            t["subtab_participacion"],
            t["subtab_testimonios"],
            t["subtab_tabla"]
        ])

        # SUBTAB 1: ALCANCE (MÉTRICAS EXPANDIDAS)
        with subtab1:
            tot_actividades = len(df_act)
            tot_adultos = int(df_act["adultos_atendidos"].sum()) if not df_act.empty and "adultos_atendidos" in df_act.columns else 0
            tot_ninos = int(df_act["ninos_atendidos"].sum()) if not df_act.empty and "ninos_atendidos" in df_act.columns else 0
            tot_personas = tot_adultos + tot_ninos
            tot_familias = int(df_act["familias_atendidas"].sum()) if not df_act.empty and "familias_atendidas" in df_act.columns else 0
            tot_conversiones = int(df_act["conversiones"].sum()) if not df_act.empty and "conversiones" in df_act.columns else 0
            tot_discipulado = int(df_act["personas_discipulado"].sum()) if not df_act.empty and "personas_discipulado" in df_act.columns else 0

            # Conteo de sectores / municipios únicos
            sectores_set = set()
            if not df_act.empty and "sectores_municipios" in df_act.columns:
                for item in df_act["sectores_municipios"].dropna():
                    parts = [p.strip() for p in str(item).split(",") if p.strip()]
                    sectores_set.update(parts)
            tot_sectores = len(sectores_set)

            # Tarjetas KPI Fila 1: General & Demografía Directa
            col1, col2, col3, col4 = st.columns(4)
            col1.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_personas:,}</div><div class="kpi-title">{t["kpi_total_personas"]}</div></div>', unsafe_allow_html=True)
            col2.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_adultos:,}</div><div class="kpi-title">{t["kpi_adultos"]}</div></div>', unsafe_allow_html=True)
            col3.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_ninos:,}</div><div class="kpi-title">{t["kpi_ninos"]}</div></div>', unsafe_allow_html=True)
            col4.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_familias:,}</div><div class="kpi-title">{t["kpi_familias"]}</div></div>', unsafe_allow_html=True)

            # Tarjetas KPI Fila 2: Impacto Espiritual, Jornadas y Cobertura
            col5, col6, col7, col8 = st.columns(4)
            col5.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_conversiones:,}</div><div class="kpi-title">{t["kpi_conversiones"]}</div></div>', unsafe_allow_html=True)
            col6.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_discipulado:,}</div><div class="kpi-title">{t["kpi_discipulado"]}</div></div>', unsafe_allow_html=True)
            col7.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_actividades}</div><div class="kpi-title">{t["kpi_total_actividades"]}</div></div>', unsafe_allow_html=True)
            col8.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_sectores}</div><div class="kpi-title">{t["kpi_sectores_num"]}</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Mapa Consolidado de Actividades
            map_data = []
            if not df_act.empty and "ubicacion" in df_act.columns:
                for _, r in df_act.iterrows():
                    lat, lon = extract_lat_lon(r.get("ubicacion"))
                    if lat is not None and lon is not None:
                        map_data.append({
                            'lat': lat,
                            'lon': lon,
                            'nombre': r.get('nombre_actividad', 'Actividad'),
                            'lugar': r.get('lugar', '')
                        })
            
            if map_data:
                st.markdown("### 🗺️ Cobertura Geográfica e Intervención en Tiempo Real")
                df_map = pd.DataFrame(map_data)
                st.map(df_map, zoom=6)
                st.markdown("<br>", unsafe_allow_html=True)

            # Gráficos de Alcance
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                df_pob = pd.DataFrame({
                    "Categoría": ["Adultos Atendidos", "Niños Atendidos"],
                    "Total": [tot_adultos, tot_ninos]
                })
                draw_pie_chart(df_pob, "Categoría", "Total", "Proporción Demográfica Atendida (Adultos vs. Niños)")

            with col_chart2:
                # Conteo de tipos de atención
                atencion_counts = {}
                if not df_act.empty and "tipos_atencion" in df_act.columns:
                    for item in df_act["tipos_atencion"].dropna():
                        types = [x.strip() for x in str(item).split(",") if x.strip()]
                        for tp in types:
                            atencion_counts[tp] = atencion_counts.get(tp, 0) + 1

                df_at = pd.DataFrame(list(atencion_counts.items()), columns=["Tipo de Atención", "Frecuencia"])
                if not df_at.empty:
                    draw_bar_chart(df_at, "Tipo de Atención", "Frecuencia", t["tipos_atencion_chart"], "Purples")
                else:
                    st.info("No hay datos registrados aún sobre tipos de atención.")

            # Resumen de Ayudas Entregadas y Cobertura Geográfica
            st.markdown("---")
            st.markdown(f"### {t['ayudas_resumen_title']}")
            if not df_act.empty and "ayudas_entregadas" in df_act.columns:
                ayudas_list = [str(a).strip() for a in df_act["ayudas_entregadas"].dropna() if str(a).strip()]
                if ayudas_list:
                    combined_ayudas = "; ".join(ayudas_list)
                    st.markdown(render_ayudas_badges(combined_ayudas), unsafe_allow_html=True)
                else:
                    st.caption("No se han detallado descripciones específicas de ayudas entregadas.")
            
            if sectores_set:
                st.markdown("<br>**Sectores y Municipios Cubiertos:**", unsafe_allow_html=True)
                st.write(", ".join(sorted(list(sectores_set))))

        # SUBTAB 2: PARTICIPACIÓN (MÉTRICAS EXPANDIDAS)
        with subtab2:
            tot_iglesias = int(df_act["iglesias_participantes"].sum()) if not df_act.empty and "iglesias_participantes" in df_act.columns else 0
            tot_pastores = int(df_act["pastores_lideres_involucrados"].sum()) if not df_act.empty and "pastores_lideres_involucrados" in df_act.columns else 0
            tot_voluntarios = int(df_act["familias_creyentes_preparacion"].sum()) if not df_act.empty and "familias_creyentes_preparacion" in df_act.columns else 0
            tot_fuerza = tot_pastores + tot_voluntarios

            # Denominaciones únicas
            denoms_set = set()
            if not df_act.empty and "denominaciones" in df_act.columns:
                for item in df_act["denominaciones"].dropna():
                    parts = [d.strip() for d in str(item).split(",") if d.strip()]
                    denoms_set.update(parts)
            tot_denominaciones = len(denoms_set)

            # Promedios
            prom_vol_act = round(tot_fuerza / len(df_act), 1) if not df_act.empty and len(df_act) > 0 else 0.0
            tot_personas_gen = (int(df_act["adultos_atendidos"].sum()) if not df_act.empty and "adultos_atendidos" in df_act.columns else 0) + \
                               (int(df_act["ninos_atendidos"].sum()) if not df_act.empty and "ninos_atendidos" in df_act.columns else 0)
            prom_pers_iglesia = round(tot_personas_gen / tot_iglesias, 1) if tot_iglesias > 0 else 0.0

            # Tarjetas KPI Fila 1: Convocatoria e Iglesias
            pcol1, pcol2, pcol3, pcol4 = st.columns(4)
            pcol1.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_iglesias:,}</div><div class="kpi-title">{t["kpi_iglesias"]}</div></div>', unsafe_allow_html=True)
            pcol2.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_pastores:,}</div><div class="kpi-title">{t["kpi_pastores"]}</div></div>', unsafe_allow_html=True)
            pcol3.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_voluntarios:,}</div><div class="kpi-title">{t["kpi_voluntarios"]}</div></div>', unsafe_allow_html=True)
            pcol4.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_fuerza:,}</div><div class="kpi-title">{t["kpi_fuerza_voluntaria"]}</div></div>', unsafe_allow_html=True)

            # Tarjetas KPI Fila 2: Denominaciones y Promedios de Desempeño
            pcol5, pcol6, pcol7 = st.columns(3)
            pcol5.markdown(f'<div class="kpi-card"><div class="kpi-val">{tot_denominaciones}</div><div class="kpi-title">{t["kpi_denominaciones_num"]}</div></div>', unsafe_allow_html=True)
            pcol6.markdown(f'<div class="kpi-card"><div class="kpi-val">{prom_vol_act}</div><div class="kpi-title">{t["kpi_prom_voluntarios_act"]}</div></div>', unsafe_allow_html=True)
            pcol7.markdown(f'<div class="kpi-card"><div class="kpi-val">{prom_pers_iglesia}</div><div class="kpi-title">{t["kpi_prom_personas_iglesia"]}</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # Gráficos de Participación
            col_part_g1, col_part_g2 = st.columns(2)
            with col_part_g1:
                df_fuerza = pd.DataFrame({
                    "Categoría": ["Pastores y Líderes", "Familias Creyentes / Voluntarios"],
                    "Cantidad": [tot_pastores, tot_voluntarios]
                })
                draw_pie_chart(df_fuerza, "Categoría", "Cantidad", "Composición de la Fuerza Voluntaria")

            with col_part_g2:
                if not df_act.empty and "lugar" in df_act.columns and "iglesias_participantes" in df_act.columns:
                    df_ig_lugar = df_act.groupby("lugar")["iglesias_participantes"].sum().reset_index()
                    draw_bar_chart(df_ig_lugar, "lugar", "iglesias_participantes", "Iglesias Participantes por Ubicación", "Blues")
                else:
                    st.info("No hay datos de participación por ubicación.")

            st.markdown("---")
            st.markdown("### Denominaciones Unificadas en el Proyecto")
            if denoms_set:
                st.write(", ".join(sorted(list(denoms_set))))
            else:
                st.caption("Aún no hay denominaciones específicas registradas.")

        # SUBTAB 3: TESTIMONIOS Y MULTIMEDIA (SÓLO MUESTRA ARCHIVOS APROBADOS POR EL EDITOR)
        with subtab3:
            st.subheader("💬 Testimonios e Historias de Vida")
            if not df_act.empty:
                for idx, row in df_act.iterrows():
                    # Filtrar sólo fotos y videos aprobados por el Editor
                    foto_urls = parse_media_urls(row.get("fotos_url"), only_approved=True)
                    media_urls = parse_media_urls(row.get("videos_audios_url"), only_approved=True)

                    if row.get("testimonios_texto") or row.get("descripcion") or foto_urls or media_urls:
                        _lang = st.session_state.get("lang", "es")
                        formatted_fecha = format_date_range(row.get('fecha_desde'), row.get('fecha_hasta'), _lang)
                        with st.expander(f"📌 {row.get('nombre_actividad', 'Actividad')} - {row.get('lugar', '')} ({formatted_fecha})", expanded=True):
                            # Información básica de la Actividad
                            st.markdown(f"**Actividad :** {row.get('nombre_actividad', 'N/A')}")
                            # Mostrar fechas: si son iguales -> una sola Fecha, si difieren -> Fecha Desde y Fecha Hasta
                            fd = format_date_str(row.get('fecha_desde'), _lang)
                            fh = format_date_str(row.get('fecha_hasta'), _lang)
                            if fd == fh:
                                st.markdown(f"**Fecha :** `{fd}`")
                            else:
                                st.markdown(f"**Fecha Desde :** `{fd}` &nbsp;&nbsp; **Fecha Hasta :** `{fh}`")
                            st.markdown(f"**Lugar :** {row.get('lugar', 'N/A')}")
                            
                            # Renderizado de Badges para Pastores a Cargo
                            st.markdown("**Pastores a cargo :**")
                            st.markdown(render_pastores_badges(row.get('pastores_cargo')), unsafe_allow_html=True)
                            
                            st.markdown(f"**Descripción :** {row.get('descripcion', 'Sin descripción')}")
                            
                            # Renderizado de Badges para Ayudas Entregadas con colores alternados
                            st.markdown("**Ayudas Entregadas :**")
                            st.markdown(render_ayudas_badges(row.get('ayudas_entregadas')), unsafe_allow_html=True)
                            
                            cobertura_part = row.get('sectores_municipios')
                            st.markdown(f"**Cobertura (Sectores/Municipios) :** {cobertura_part if pd.notna(cobertura_part) and str(cobertura_part).strip() else 'N/A'}")

                            if row.get("testimonios_texto") and str(row.get("testimonios_texto")).strip():
                                st.markdown(f"**Testimonio / Historia de Vida :** *{row['testimonios_texto']}*")

                            # Renderizado del mapa de ubicación para cada actividad
                            if row.get('ubicacion'):
                                render_location_map(row.get('ubicacion'), title="Ubicación de la Jornada")

                            # Métricas Particulares de la Actividad con st.metric
                            st.markdown("<br>", unsafe_allow_html=True)
                            st.markdown("##### 📊 Métricas de Alcance e Impacto")
                            
                            adultos_val = int(row.get('adultos_atendidos', 0)) if pd.notna(row.get('adultos_atendidos')) else 0
                            ninos_val = int(row.get('ninos_atendidos', 0)) if pd.notna(row.get('ninos_atendidos')) else 0
                            familias_val = int(row.get('familias_atendidas', 0)) if pd.notna(row.get('familias_atendidas')) else 0
                            conv_val = int(row.get('conversiones', 0)) if pd.notna(row.get('conversiones')) else 0
                            disc_val = int(row.get('personas_discipulado', 0)) if pd.notna(row.get('personas_discipulado')) else 0

                            # Primer grupo de métricas (Total Personas, Adultos / Niños, Familias)
                            m_alc1_c1, m_alc1_c2, m_alc1_c3 = st.columns(3)
                            m_alc1_c1.metric("👥 Total Personas", f"{adultos_val + ninos_val:,}")
                            m_alc1_c2.metric("🧑‍🤝‍🧑 Adultos / Niños", f"{adultos_val} / {ninos_val}")
                            m_alc1_c3.metric("🏠 Familias", f"{familias_val:,}")

                            st.markdown("<br>", unsafe_allow_html=True)

                            # Segundo grupo de métricas (Conversiones, En Discipulado)
                            m_alc2_c1, m_alc2_c2 = st.columns(2)
                            m_alc2_c1.metric("🙏 Conversiones", f"{conv_val:,}")
                            m_alc2_c2.metric("📖 En Discipulado", f"{disc_val:,}")

                            # Métricas de Participación
                            st.markdown("##### 🤝 Métricas de Participación")
                            iglesias_val = int(row.get('iglesias_participantes', 0)) if pd.notna(row.get('iglesias_participantes')) else 0
                            pastores_val = int(row.get('pastores_lideres_involucrados', 0)) if pd.notna(row.get('pastores_lideres_involucrados')) else 0
                            voluntarios_val = int(row.get('familias_creyentes_preparacion', 0)) if pd.notna(row.get('familias_creyentes_preparacion')) else 0
                            
                            m_part_c1, m_part_c2, m_part_c3 = st.columns(3)
                            m_part_c1.metric("⛪ Iglesias", f"{iglesias_val}")
                            m_part_c2.metric("👤 Pastores/Líderes", f"{pastores_val}")
                            m_part_c3.metric("🙌 Voluntarios", f"{voluntarios_val}")

                            # Tipos de Atención mostrados como etiquetas (badges)
                            st.markdown("**Tipos de Atención:**")
                            tp_atencion_raw = str(row.get('tipos_atencion', '')) if pd.notna(row.get('tipos_atencion')) else ''
                            if tp_atencion_raw.strip():
                                tags_list = [t.strip() for t in tp_atencion_raw.split(",") if t.strip()]
                                tags_html = " ".join([f'<span style="display:inline-block; background-color: rgba(99, 102, 241, 0.2); color: #818CF8; border: 1px solid rgba(99, 102, 241, 0.4); padding: 5px 12px; border-radius: 16px; font-size: 0.85rem; font-weight: 600; margin: 2px 4px 6px 0px;">🏷️ {tag}</span>' for tag in tags_list])
                                st.markdown(tags_html, unsafe_allow_html=True)
                            else:
                                st.caption("N/A")

                            if pd.notna(row.get('denominaciones')) and str(row.get('denominaciones')).strip():
                                st.caption(f"🤝 **Denominaciones participantes:** {row.get('denominaciones')}")

                            st.markdown("---")
                            m_col1, m_col2 = st.columns(2)
                            
                            # Sección Fotos
                            with m_col1:
                                st.markdown("### 📷 Fotos")
                                if foto_urls:
                                    for fi, f_url in enumerate(foto_urls):
                                        if f_url.startswith("http"):
                                            st.image(f_url, caption=f"Foto {fi+1}", use_container_width=True)
                                        else:
                                            st.write(f"📁 [Ver Foto {fi+1}]({f_url})")
                                else:
                                    st.caption("No hay fotos aprobadas para esta actividad.")

                            # Sección Videos
                            with m_col2:
                                st.markdown("### 🎬 Videos")
                                if media_urls:
                                    for v_url in media_urls:
                                        if v_url.endswith((".mp4", ".mov", ".webm")):
                                            st.video(v_url)
                                        elif v_url.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                                            st.audio(v_url)
                                        else:
                                            st.write(f"🎥 [Ver Archivo]({v_url})")
                                else:
                                    st.caption("No hay videos o audios aprobados para esta actividad.")
            else:
                st.info("Aún no hay testimonios multimedia registrados.")

        # SUBTAB 4: TABLA COMPLETA DE ACTIVIDADES
        with subtab4:
            st.subheader("📋 Consolidado de Actividades Registradas (Turso DB)")
            if not df_act.empty:
                df_display = df_act.copy()
                _lang = st.session_state.get("lang", "es")
                if "fecha_desde" in df_display.columns:
                    df_display["fecha_desde"] = df_display["fecha_desde"].apply(lambda v: format_date_str(v, _lang))
                if "fecha_hasta" in df_display.columns:
                    df_display["fecha_hasta"] = df_display["fecha_hasta"].apply(lambda v: format_date_str(v, _lang))

                st.dataframe(df_display, use_container_width=True)

                csv = df_act.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=t["export_csv"],
                    data=csv,
                    file_name=f"actividades_misericordia_{datetime.date.today()}.csv",
                    mime="text/csv"
                )
            else:
                st.info("La tabla de actividades no contiene registros actualmente.")

# ---------------------------------------------------------
# SECCIÓN 2: FORMULARIO DE CARGA DE ACTIVIDAD (REPORTERO)
# ---------------------------------------------------------
elif current_nav == t["nav_cargar"] and st.session_state["user"] is not None:
    st.subheader(t["form_title"])
    u = st.session_state["user"]

    # ---- 📍 GPS Helper ----
    with st.expander("📍 Obtener Coordenadas GPS Automáticamente", expanded=not bool(st.session_state.get('gps_coords'))):
        gps_col1, gps_col2, gps_col3 = st.columns([4, 1, 1])
        with gps_col1:
            if st.session_state.get('gps_coords'):
                st.success(f"✅ **Coordenadas GPS capturadas:** `{st.session_state['gps_coords']}`")
            else:
                st.info("Presiona **📍 Obtener GPS** para capturar automáticamente tus coordenadas actuales desde el navegador.")
        with gps_col2:
            if st.button("📍 Obtener GPS", key="btn_gps_obtener", use_container_width=True):
                st.session_state['gps_requested'] = True
                st.rerun()
        with gps_col3:
            if st.button("🗑️ Limpiar", key="btn_gps_limpiar", use_container_width=True):
                st.session_state['gps_coords'] = ''
                st.session_state['gps_requested'] = False
                st.rerun()

        if st.session_state.get('gps_requested', False):
            if HAS_GEOLOCATION:
                with st.spinner("⏳ Solicitando permiso de ubicación al navegador... (haz clic en Permitir si aparece el mensaje)"):
                    loc = get_geolocation(component_key='gps_eval_component')
                    if loc and isinstance(loc, dict) and 'coords' in loc:
                        coords = loc['coords']
                        lat = coords.get('latitude')
                        lon = coords.get('longitude')
                        if lat is not None and lon is not None:
                            st.session_state['gps_coords'] = f"{lat:.6f}, {lon:.6f}"
                            st.session_state['gps_requested'] = False
                            st.success(f"📍 ¡Ubicación capturada con éxito!: `{st.session_state['gps_coords']}`")
                            st.rerun()
                    else:
                        st.caption("💡 *Si el navegador solicita permisos de geolocalización, acepta. De lo contrario, puedes escribir las coordenadas manualmente en la casilla de ubicación abajo.*")
            else:
                st.error("Librería `streamlit-js-eval` no instalada. Ingresa las coordenadas manualmente o instala `pip install streamlit-js-eval`.")
                st.session_state['gps_requested'] = False

        if st.session_state.get('gps_coords'):
            render_location_map(st.session_state['gps_coords'], title="Vista previa de coordenadas GPS capturadas")

    st.markdown("---")

    with st.form("form_actividad", clear_on_submit=True):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            reportero_input = st.text_input(t["field_reportero"], value=u["nombre_completo"], disabled=(u["rol"] == "reportero"))
            nombre_actividad = st.text_input(t["field_actividad"], placeholder="Ej: Jornada de Alimentación y Consejería")
            fecha_desde = st.date_input(t["field_fecha_desde"], value=datetime.date.today())
            fecha_hasta = st.date_input(t["field_fecha_hasta"], value=fecha_desde)
            lugar_actividad = st.text_input(t["field_lugar"], placeholder="Ej: La Guaira, Sector Naiguatá")
            ubicacion_actividad = st.text_input(
                t["field_ubicacion"],
                value=st.session_state.get('gps_coords', ''),
                placeholder="Coordenadas GPS (ej: 10.4806, -66.9036) o Dirección detallada"
            )

        with col_f2:
            pastores_cargo = st.text_input(t["field_pastores"], placeholder="Ej: Pr. Carlos Mendoza, Pr. Maria Silva")
            descripcion = st.text_area(t["field_desc"], placeholder="Detalles de la jornada realizada...")

        st.markdown("### 📸 Archivos Multimedia (Imágenes, Audios y Videos)")
        st.caption("💡 Puedes seleccionar **múltiples archivos** a la vez. Se subirán a Cloudinary y requerirán aprobación del Editor para mostrarse públicamente.")
        col_m1, col_m2 = st.columns(2)

        with col_m1:
            st.write("**🖼️ Imágenes / Fotos** (múltiples)")
            files_fotos = st.file_uploader(
                t["upload_direct"] + " (Fotos)",
                type=["png", "jpg", "jpeg", "webp"],
                accept_multiple_files=True,
                key="uploader_fotos"
            )
            url_fotos_ext = st.text_input(t["url_external"] + " (Fotos)")

        with col_m2:
            st.write("**🎬 Videos / Audios** (múltiples)")
            files_media = st.file_uploader(
                t["upload_direct"] + " (Video/Audio)",
                type=["mp4", "mp3", "wav", "mov", "m4a", "ogg", "webm"],
                accept_multiple_files=True,
                key="uploader_media"
            )
            url_media_ext = st.text_input(t["url_external"] + " (Videos/Audios)")

        st.markdown("### 📊 Métricas de Alcance")
        c_alc1, c_alc2, c_alc3, c_alc4, c_alc5 = st.columns(5)
        num_conversiones = c_alc1.number_input(t["kpi_conversiones"], min_value=0, value=0)
        num_discipulado = c_alc2.number_input(t["kpi_discipulado"], min_value=0, value=0)
        num_adultos = c_alc3.number_input(t["kpi_adultos"], min_value=0, value=0)
        num_ninos = c_alc4.number_input(t["kpi_ninos"], min_value=0, value=0)
        num_familias = c_alc5.number_input(t["kpi_familias"], min_value=0, value=0)

        tipos_atencion_sel = st.multiselect(
            t["field_atencion"],
            options=["Consejería", "Acompañamiento Emocional", "Ropa / Calzado", "Comida / Alimentos", "Apoyo Médico", "Kits de Aseo", "Discipulado Biblico"]
        )
        sectores = st.text_input(t["field_sectores"], placeholder="Ej: Municipio Vargas, Parroquia Catia La Mar")
        ayudas = st.text_area(t["field_ayudas"], placeholder="Ej: 200 bolsas de alimentos; 50 kits de aseo personal. Ropa y calzado")

        st.markdown("### 🤝 Métricas de Participación")
        c_part1, c_part2, c_part3 = st.columns(3)
        num_iglesias = c_part1.number_input(t["kpi_iglesias"], min_value=0, value=0)
        num_pastores = c_part2.number_input(t["kpi_pastores"], min_value=0, value=0)
        num_voluntarios = c_part3.number_input(t["kpi_voluntarios"], min_value=0, value=0)
        denominaciones_input = st.text_input(t["field_denominaciones"], placeholder="Ej: Bautista, Pentecostal, Asambleas de Dios")

        st.markdown("### 💬 Testimonios y Notas Adicionales")
        testimonios_texto = st.text_area(t["field_testimonios_texto"], placeholder="Escribe aquí un testimonio o historia impactante...")
        campo_otro = st.text_area(t["field_otro"], placeholder="Campo flexible para observaciones o datos extra...")

        submitted = st.form_submit_button(t["save_btn"], use_container_width=True)

        if submitted:
            folder_name = f"pmis2026/{sanitize_folder_name(nombre_actividad)}_{fecha_desde}"
            is_auto_approved = (u["rol"] in ["editor", "admin"])

            # Subida de fotos
            fotos_dicts = []
            if IS_CLOUDINARY_READY and files_fotos:
                prog_fotos = st.progress(0, text="Subiendo fotos...")
                for i, f in enumerate(files_fotos):
                    url = upload_media_file(f, folder=folder_name)
                    if url:
                        fotos_dicts.append({"url": url, "aprobado": is_auto_approved})
                    prog_fotos.progress((i + 1) / len(files_fotos), text=f"Foto {i+1}/{len(files_fotos)} subida...")
                prog_fotos.empty()
            elif files_fotos and not IS_CLOUDINARY_READY:
                st.warning("⚠️ Cloudinary no está configurado. Las fotos no se subieron.")
            
            if url_fotos_ext.strip():
                fotos_dicts.append({"url": url_fotos_ext.strip(), "aprobado": is_auto_approved})
            
            final_fotos_json = json.dumps(fotos_dicts) if fotos_dicts else ""

            # Subida de videos / audios
            media_dicts = []
            if IS_CLOUDINARY_READY and files_media:
                prog_media = st.progress(0, text="Subiendo videos/audios...")
                for i, f in enumerate(files_media):
                    url = upload_media_file(f, folder=folder_name)
                    if url:
                        media_dicts.append({"url": url, "aprobado": is_auto_approved})
                    prog_media.progress((i + 1) / len(files_media), text=f"Archivo {i+1}/{len(files_media)} subido...")
                prog_media.empty()
            elif files_media and not IS_CLOUDINARY_READY:
                st.warning("⚠️ Cloudinary no está configurado. Los videos/audios no se subieron.")
            
            if url_media_ext.strip():
                media_dicts.append({"url": url_media_ext.strip(), "aprobado": is_auto_approved})
            
            final_media_json = json.dumps(media_dicts) if media_dicts else ""
            tipos_atencion_str = ", ".join(tipos_atencion_sel)

            query_insert = """
            INSERT INTO actividades (
                reportero, nombre_actividad, fecha_desde, fecha_hasta, lugar, ubicacion, pastores_cargo, descripcion,
                fotos_url, videos_audios_url, conversiones, personas_discipulado, adultos_atendidos,
                ninos_atendidos, familias_atendidas, tipos_atencion, sectores_municipios, ayudas_entregadas,
                iglesias_participantes, denominaciones, pastores_lideres_involucrados, familias_creyentes_preparacion,
                testimonios_texto, otro, estado
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aprobado');
            """
            params = [
                reportero_input, nombre_actividad, str(fecha_desde), str(fecha_hasta), lugar_actividad, ubicacion_actividad, pastores_cargo, descripcion,
                final_fotos_json, final_media_json, int(num_conversiones), int(num_discipulado), int(num_adultos),
                int(num_ninos), int(num_familias), tipos_atencion_str, sectores, ayudas,
                int(num_iglesias), denominaciones_input, int(num_pastores), int(num_voluntarios),
                testimonios_texto, campo_otro
            ]

            success = execute_query(query_insert, params)
            if success:
                total_media = len(fotos_dicts) + len(media_dicts)
                st.success(f"{t['save_success']} ({total_media} archivo(s) multimedia registrado(s))")
                st.session_state['gps_coords'] = ''
            else:
                st.error(t["save_error"])

# ---------------------------------------------------------
# SECCIÓN 3: GESTIÓN DE ACTIVIDADES Y EDICIÓN DE TESTIMONIOS (EDITOR / ADMIN)
# ---------------------------------------------------------
elif current_nav == t["nav_gestionar"] and st.session_state["user"] is not None and st.session_state["user"]["rol"] in ["editor", "admin"]:
    st.subheader(t["nav_gestionar"])
    df_all = fetch_data("SELECT * FROM actividades ORDER BY id DESC")

    if not df_all.empty:
        df_all_disp = df_all.copy()
        _lang = st.session_state.get("lang", "es")
        if "fecha_desde" in df_all_disp.columns:
            df_all_disp["fecha_desde"] = df_all_disp["fecha_desde"].apply(lambda v: format_date_str(v, _lang))
        if "fecha_hasta" in df_all_disp.columns:
            df_all_disp["fecha_hasta"] = df_all_disp["fecha_hasta"].apply(lambda v: format_date_str(v, _lang))
        st.dataframe(df_all_disp, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### ⚙️ Modificación Completa y Edición de Testimonios / Actividades")
        
        act_options = [f"ID #{row['id']} - {row['nombre_actividad']} ({format_date_range(row.get('fecha_desde'), row.get('fecha_hasta'), st.session_state.get('lang', 'es'))} | {row['lugar']})" for _, row in df_all.iterrows()]
        act_ids = df_all["id"].tolist()
        
        sel_idx = st.selectbox(
            "Seleccionar Testimonio / Actividad para Modificar",
            range(len(act_ids)),
            format_func=lambda idx: act_options[idx]
        )
        sel_id = act_ids[sel_idx]
        row_sel = df_all[df_all["id"] == sel_id].iloc[0]

        # Pestañas para organizar la edición del testimonio
        tab_edit_info, tab_edit_media, tab_danger = st.tabs([
            "✏️ Editar Campos del Testimonio",
            "📸/🎬 Aprobar / Editar Multimedia",
            "🗑️ Estado General y Eliminar"
        ])

        # TAB 1: FORMULARIO DE EDICIÓN DE CADA ELEMENTO DEL TESTIMONIO
        with tab_edit_info:
            st.markdown(f"#### {t['edit_activity_title']} (ID #{sel_id})")
            
            with st.form(f"form_edit_act_{sel_id}"):
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    e_reportero = st.text_input(t["field_reportero"], value=str(row_sel.get("reportero", "")))
                    e_nombre = st.text_input(t["field_actividad"], value=str(row_sel.get("nombre_actividad", "")))
                    
                    # Formatear fecha
                    raw_fecha_desde = str(row_sel.get("fecha_desde", ""))
                    raw_fecha_hasta = str(row_sel.get("fecha_hasta", ""))
                    try:
                        parsed_date_desde = datetime.datetime.strptime(raw_fecha_desde, "%Y-%m-%d").date()
                    except Exception:
                        parsed_date_desde = datetime.date.today()
                    try:
                        parsed_date_hasta = datetime.datetime.strptime(raw_fecha_hasta, "%Y-%m-%d").date()
                    except Exception:
                        parsed_date_hasta = parsed_date_desde
                    
                    e_fecha_desde = st.date_input(t["field_fecha_desde"], value=parsed_date_desde)
                    e_fecha_hasta = st.date_input(t["field_fecha_hasta"], value=parsed_date_hasta)
                    e_lugar = st.text_input(t["field_lugar"], value=str(row_sel.get("lugar", "")))
                    e_ubicacion = st.text_input(t["field_ubicacion"], value=str(row_sel.get("ubicacion", "")))

                    if e_ubicacion:
                        render_location_map(e_ubicacion, title="Vista Previa de Ubicación en Editor")

                with col_e2:
                    e_pastores = st.text_input(t["field_pastores"], value=str(row_sel.get("pastores_cargo", "")))
                    e_desc = st.text_area(t["field_desc"], value=str(row_sel.get("descripcion", "")), height=140)

                st.markdown("##### 📊 Métricas de Alcance")
                c_ea1, c_ea2, c_ea3, c_ea4, c_ea5 = st.columns(5)
                e_conversiones = c_ea1.number_input(t["kpi_conversiones"], min_value=0, value=int(row_sel.get("conversiones", 0) or 0))
                e_discipulado = c_ea2.number_input(t["kpi_discipulado"], min_value=0, value=int(row_sel.get("personas_discipulado", 0) or 0))
                e_adultos = c_ea3.number_input(t["kpi_adultos"], min_value=0, value=int(row_sel.get("adultos_atendidos", 0) or 0))
                e_ninos = c_ea4.number_input(t["kpi_ninos"], min_value=0, value=int(row_sel.get("ninos_atendidos", 0) or 0))
                e_familias = c_ea5.number_input(t["kpi_familias"], min_value=0, value=int(row_sel.get("familias_atendidas", 0) or 0))

                # Multiselect de tipos de atención
                opts_atencion = ["Consejería", "Acompañamiento Emocional", "Ropa / Calzado", "Comida / Alimentos", "Apoyo Médico", "Kits de Aseo", "Discipulado Biblico"]
                curr_at = [x.strip() for x in str(row_sel.get("tipos_atencion", "")).split(",") if x.strip()]
                default_at = [x for x in curr_at if x in opts_atencion]

                e_atencion_sel = st.multiselect(
                    t["field_atencion"],
                    options=opts_atencion,
                    default=default_at
                )
                e_sectores = st.text_input(t["field_sectores"], value=str(row_sel.get("sectores_municipios", "")))
                e_ayudas = st.text_area(t["field_ayudas"], value=str(row_sel.get("ayudas_entregadas", "")), height=100)

                st.markdown("##### 🤝 Métricas de Participación")
                c_ep1, c_ep2, c_ep3 = st.columns(3)
                e_iglesias = c_ep1.number_input(t["kpi_iglesias"], min_value=0, value=int(row_sel.get("iglesias_participantes", 0) or 0))
                e_pastores_num = c_ep2.number_input(t["kpi_pastores"], min_value=0, value=int(row_sel.get("pastores_lideres_involucrados", 0) or 0))
                e_voluntarios = c_ep3.number_input(t["kpi_voluntarios"], min_value=0, value=int(row_sel.get("familias_creyentes_preparacion", 0) or 0))
                e_denominaciones = st.text_input(t["field_denominaciones"], value=str(row_sel.get("denominaciones", "")))

                st.markdown("##### 💬 Testimonio e Historias de Vida")
                e_testimonios_texto = st.text_area(t["field_testimonios_texto"], value=str(row_sel.get("testimonios_texto", "")), height=120)
                e_otro = st.text_area(t["field_otro"], value=str(row_sel.get("otro", "")), height=80)

                # Estado
                curr_estado = str(row_sel.get("estado", "aprobado")).lower()
                idx_est = 0
                if curr_estado == "pendiente": idx_est = 1
                elif curr_estado == "borrador": idx_est = 2

                e_estado = st.selectbox("Estado General de la Actividad", ["aprobado", "pendiente", "borrador"], index=idx_est)

                btn_save_edits = st.form_submit_button(t["save_edits_btn"], use_container_width=True)

                if btn_save_edits:
                    atencion_str = ", ".join(e_atencion_sel)
                    query_update = """
                    UPDATE actividades SET
                        reportero = ?,
                        nombre_actividad = ?,
                        fecha_desde = ?,
                        fecha_hasta = ?,
                        lugar = ?,
                        ubicacion = ?,
                        pastores_cargo = ?,
                        descripcion = ?,
                        conversiones = ?,
                        personas_discipulado = ?,
                        adultos_atendidos = ?,
                        ninos_atendidos = ?,
                        familias_atendidas = ?,
                        tipos_atencion = ?,
                        sectores_municipios = ?,
                        ayudas_entregadas = ?,
                        iglesias_participantes = ?,
                        denominaciones = ?,
                        pastores_lideres_involucrados = ?,
                        familias_creyentes_preparacion = ?,
                        testimonios_texto = ?,
                        otro = ?,
                        estado = ?
                    WHERE id = ?;
                    """
                    params_update = [
                        e_reportero, e_nombre, str(e_fecha_desde), str(e_fecha_hasta), e_lugar, e_ubicacion, e_pastores, e_desc,
                        int(e_conversiones), int(e_discipulado), int(e_adultos), int(e_ninos), int(e_familias),
                        atencion_str, e_sectores, e_ayudas,
                        int(e_iglesias), e_denominaciones, int(e_pastores_num), int(e_voluntarios),
                        e_testimonios_texto, e_otro, e_estado,
                        sel_id
                    ]
                    if execute_query(query_update, params_update):
                        st.success(t["edit_success"])
                        st.rerun()
                    else:
                        st.error("Error al guardar las modificaciones en la base de datos.")

        # TAB 2: APROBACIÓN / EDICIÓN MULTIMEDIA
        #
        with tab_edit_media:
            st.subheader(t["media_approval_title"])
            st.caption(f"Gestión de visibilidad pública de archivos multimedia para la Actividad #{sel_id}: **{row_sel['nombre_actividad']}**")

            list_fotos = parse_media_urls(row_sel.get("fotos_url"), only_approved=False)
            list_media = parse_media_urls(row_sel.get("videos_audios_url"), only_approved=False)

            if not list_fotos and not list_media:
                st.info("Esta actividad no posee archivos multimedia registrados.")
            else:
                btn_col1, btn_col2, _ = st.columns([1, 1, 2])
                if btn_col1.button(t["approve_all"], key="btn_app_all"):
                    for f in list_fotos: f["aprobado"] = True
                    for m in list_media: m["aprobado"] = True
                    execute_query("UPDATE actividades SET fotos_url = ?, videos_audios_url = ? WHERE id = ?", [json.dumps(list_fotos), json.dumps(list_media), sel_id])
                    st.success("¡Todos los archivos multimedia han sido APROBADOS!")
                    st.rerun()

                if btn_col2.button(t["disapprove_all"], key="btn_dis_all"):
                    for f in list_fotos: f["aprobado"] = False
                    for m in list_media: m["aprobado"] = False
                    execute_query("UPDATE actividades SET fotos_url = ?, videos_audios_url = ? WHERE id = ?", [json.dumps(list_fotos), json.dumps(list_media), sel_id])
                    st.warning("¡Todos los archivos multimedia han sido DESAPROBADOS!")
                    st.rerun()

                st.markdown("<br>", unsafe_allow_html=True)

                updated_fotos = []
                updated_media = []

                if list_fotos:
                    st.markdown("#### 🖼️ Fotos e Imágenes")
                    cols_f = st.columns(min(len(list_fotos), 3))
                    for i, item in enumerate(list_fotos):
                        with cols_f[i % 3]:
                            u_url = item["url"]
                            st.image(u_url, use_container_width=True)
                            is_app = st.checkbox(
                                f"Aprobar Foto #{i+1}",
                                value=item["aprobado"],
                                key=f"chk_foto_{sel_id}_{i}"
                            )
                            updated_fotos.append({"url": u_url, "aprobado": is_app})

                st.markdown("<br>", unsafe_allow_html=True)

                if list_media:
                    st.markdown("#### 🎬 Videos y Audios")
                    cols_m = st.columns(min(len(list_media), 2))
                    for j, item in enumerate(list_media):
                        with cols_m[j % 2]:
                            u_url = item["url"]
                            if u_url.endswith((".mp4", ".mov", ".webm")):
                                st.video(u_url)
                            elif u_url.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                                st.audio(u_url)
                            else:
                                st.write(f"📁 [Ver Archivo]({u_url})")

                            is_app = st.checkbox(
                                f"Aprobar Multimedia #{j+1}",
                                value=item["aprobado"],
                                key=f"chk_media_{sel_id}_{j}"
                            )
                            updated_media.append({"url": u_url, "aprobado": is_app})

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(t["save_media_status"], type="primary", use_container_width=True):
                    str_fotos = json.dumps(updated_fotos)
                    str_media = json.dumps(updated_media)
                    execute_query("UPDATE actividades SET fotos_url = ?, videos_audios_url = ? WHERE id = ?", [str_fotos, str_media, sel_id])
                    st.success(t["media_updated_success"])
                    st.rerun()

            st.markdown("---")
            st.markdown(f"### {t['upload_new_media_title']}")
            st.caption("💡 Carga nuevos archivos directos o enlaces externos (fotos, videos, audios) para añadirlos a esta actividad.")

            with st.form(key=f"form_upload_extra_media_{sel_id}"):
                col_m1_edit, col_m2_edit = st.columns(2)
                with col_m1_edit:
                    st.write("**🖼️ Agregar Fotos** (múltiples)")
                    new_files_fotos = st.file_uploader(
                        t["upload_direct"] + " (Fotos)",
                        type=["png", "jpg", "jpeg", "webp"],
                        accept_multiple_files=True,
                        key=f"edit_uploader_fotos_{sel_id}"
                    )
                    new_url_fotos_ext = st.text_input(t["url_external"] + " (Fotos)", key=f"edit_url_fotos_{sel_id}")

                with col_m2_edit:
                    st.write("**🎬 Agregar Videos / Audios** (múltiples)")
                    new_files_media = st.file_uploader(
                        t["upload_direct"] + " (Video/Audio)",
                        type=["mp4", "mp3", "wav", "mov", "m4a", "ogg", "webm"],
                        accept_multiple_files=True,
                        key=f"edit_uploader_media_{sel_id}"
                    )
                    new_url_media_ext = st.text_input(t["url_external"] + " (Videos/Audios)", key=f"edit_url_media_{sel_id}")

                auto_approve_new = st.checkbox("✅ Aprobar automáticamente los nuevos archivos subidos", value=True, key=f"chk_auto_app_{sel_id}")

                btn_upload_extra = st.form_submit_button(t["upload_new_media_btn"], use_container_width=True)

                if btn_upload_extra:
                    act_fecha = row_sel.get('fecha_desde') or row_sel.get('fecha') or ''
                    folder_name = f"pmis2026/{sanitize_folder_name(str(row_sel['nombre_actividad']))}_{act_fecha}"
                    added_count = 0

                    # Cargar fotos adicionales a Cloudinary
                    if IS_CLOUDINARY_READY and new_files_fotos:
                        prog_f = st.progress(0, text="Subiendo nuevas fotos...")
                        for i, f in enumerate(new_files_fotos):
                            url = upload_media_file(f, folder=folder_name)
                            if url:
                                list_fotos.append({"url": url, "aprobado": auto_approve_new})
                                added_count += 1
                            prog_f.progress((i + 1) / len(new_files_fotos), text=f"Foto {i+1}/{len(new_files_fotos)} subida...")
                        prog_f.empty()
                    elif new_files_fotos and not IS_CLOUDINARY_READY:
                        st.warning("⚠️ Cloudinary no está configurado. Las fotos no se subieron.")

                    if new_url_fotos_ext.strip():
                        list_fotos.append({"url": new_url_fotos_ext.strip(), "aprobado": auto_approve_new})
                        added_count += 1

                    # Cargar videos/audios adicionales a Cloudinary
                    if IS_CLOUDINARY_READY and new_files_media:
                        prog_m = st.progress(0, text="Subiendo nuevos videos/audios...")
                        for i, f in enumerate(new_files_media):
                            url = upload_media_file(f, folder=folder_name)
                            if url:
                                list_media.append({"url": url, "aprobado": auto_approve_new})
                                added_count += 1
                            prog_m.progress((i + 1) / len(new_files_media), text=f"Archivo {i+1}/{len(new_files_media)} subido...")
                        prog_m.empty()
                    elif new_files_media and not IS_CLOUDINARY_READY:
                        st.warning("⚠️ Cloudinary no está configurado. Los videos/audios no se subieron.")

                    if new_url_media_ext.strip():
                        list_media.append({"url": new_url_media_ext.strip(), "aprobado": auto_approve_new})
                        added_count += 1

                    if added_count > 0:
                        execute_query(
                            "UPDATE actividades SET fotos_url = ?, videos_audios_url = ? WHERE id = ?",
                            [json.dumps(list_fotos), json.dumps(list_media), sel_id]
                        )
                        st.success(f"{t['upload_new_media_success']} ({added_count} elemento(s) agregado(s))")
                        st.rerun()
                    else:
                        st.warning("No se seleccionó ningún archivo ni se ingresó ninguna URL.")

        

        # TAB 3: ESTADO RÁPIDO Y ELIMINACIÓN
        with tab_danger:
            st.markdown("### Acciones Rápidas")
            col_ed1, col_ed2 = st.columns(2)
            with col_ed1:
                idx_est = 0
                if row_sel["estado"] == "pendiente": idx_est = 1
                elif row_sel["estado"] == "borrador": idx_est = 2

                nuevo_estado = st.selectbox("Cambiar Estado General Rápidamente", ["aprobado", "pendiente", "borrador"], index=idx_est, key="quick_estado_sel")
                if st.button("Actualizar Estado"):
                    execute_query("UPDATE actividades SET estado = ? WHERE id = ?", [nuevo_estado, sel_id])
                    st.success(f"Estado de la actividad #{sel_id} actualizado a '{nuevo_estado}'.")
                    st.rerun()

            with col_ed2:
                st.write("<br>", unsafe_allow_html=True)
                if st.button("🗑️ Eliminar Actividad Completa", type="primary"):
                    execute_query("DELETE FROM actividades WHERE id = ?", [sel_id])
                    st.warning(f"Actividad #{sel_id} eliminada permanentemente.")
                    st.rerun()
    else:
        st.info("No hay actividades registradas en la base de datos.")