"""DocuMarval - Aplicación principal con arquitectura modular"""
import streamlit as st
import pandas as pd
import os
import urllib.parse
from io import BytesIO
import logging
from dotenv import load_dotenv

# Cargar variables de entorno ANTES de importar config
load_dotenv()

# Importar módulos modulares
from config.settings import config
from services.pdf_service import procesar_pdf
from utils.validators import validar_pdf
from utils.image_utils import sanitize_html
from PyPDF2 import PdfReader

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('documarval.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Importar CSS personalizado
def load_custom_css():
    """Carga el CSS personalizado completo"""
    try:
        from ui.styles import load_custom_css as load_ui_css
        load_ui_css()
    except Exception as e:
        logger.warning(f"No se pudo cargar CSS desde ui.styles: {e}")
        # Intentar desde lectorFacturas como fallback
        try:
            import lectorFacturas
            lectorFacturas.load_custom_css()
        except Exception as e2:
            logger.warning(f"No se pudo cargar CSS desde lectorFacturas: {e2}")
            # CSS completo de fallback con todas las clases necesarias
            css_completo = """
            <style>
            :root {
                --brand-900: #0B1220;
                --brand-800: #0F172A;
                --brand-700: #13223A;
                --brand-600: #173B5F;
                --brand-500: #1E5AA5;
                --brand-400: #2F7DEB;
                --brand-300: #72A8FF;
                --brand-200: #CFE1FF;
                --brand-100: #EAF1FF;
                --gray-900: #0F172A;
                --gray-700: #334155;
                --gray-500: #64748B;
                --gray-300: #CBD5E1;
                --gray-100: #F1F5F9;
                --white: #FFFFFF;
                --radius-md: 14px;
                --radius-lg: 16px;
                --elevation-1: 0 8px 24px rgba(0, 0, 0, 0.12);
                --elevation-2: 0 16px 36px rgba(0, 0, 0, 0.16);
                --glass-bg: rgba(255, 255, 255, 0.1);
                --glass-border: rgba(207, 225, 255, 0.3);
            }
            .stApp {
                background: linear-gradient(135deg, var(--brand-900) 0%, var(--brand-800) 50%, var(--brand-700) 100%);
                background-attachment: fixed;
                color: var(--white);
                min-height: 100vh;
            }
            .main-header {
                background: linear-gradient(135deg, rgba(20, 184, 166, 0.15) 0%, rgba(0, 209, 255, 0.1) 100%);
                backdrop-filter: blur(20px);
                border: 2px solid rgba(20, 184, 166, 0.3);
                border-radius: 24px;
                padding: 4rem 3rem;
                margin: 2rem auto;
                max-width: 1400px;
                box-shadow: 0 8px 32px rgba(20, 184, 166, 0.2);
            }
            .header-content {
                display: flex;
                flex-direction: column;
                gap: 1.25rem;
                align-items: center;
                text-align: center;
            }
            .header-title-container {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 2rem;
                flex-wrap: wrap;
                width: 100%;
            }
            .header-logo {
                height: 238px;
                width: auto;
                flex-shrink: 0;
                display: flex;
                align-items: center;
            }
            .header-logo img {
                height: 238px;
                width: auto;
                object-fit: contain;
                display: block;
            }
            .main-header h1 {
                color: var(--white);
                font-weight: 800;
                font-size: 3.5rem;
                margin: 0;
                line-height: 1.1;
            }
            .main-header .subtitle {
                color: var(--gray-300);
                font-size: 1.35rem;
                margin: 0;
                font-weight: 400;
            }
            .status-card {
                background: var(--glass-bg);
                backdrop-filter: blur(10px);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius-md);
                padding: 1.5rem;
                margin: 0.5rem 0;
                box-shadow: var(--elevation-1);
            }
            .status-card.success {
                border-left: 4px solid var(--brand-400);
            }
            .status-card.error {
                border-left: 4px solid #EF4444;
            }
            .info-box {
                background: var(--glass-bg);
                backdrop-filter: blur(10px);
                border: 1px solid var(--glass-border);
                border-left: 4px solid var(--brand-400);
                border-radius: var(--radius-md);
                padding: 1.5rem;
                margin: 2rem 0;
            }
            .metric-card {
                background: var(--glass-bg);
                backdrop-filter: blur(10px);
                border: 1px solid var(--glass-border);
                border-radius: var(--radius-md);
                padding: 1.5rem;
                text-align: center;
            }
            .metric-value {
                font-size: 2rem;
                font-weight: 700;
                color: var(--brand-300);
                margin: 0.5rem 0;
            }
            .metric-label {
                color: var(--gray-300);
                font-size: 0.875rem;
                text-transform: uppercase;
            }
            h1, h2, h3 {
                color: var(--white);
            }
            h3 {
                color: var(--brand-300);
            }
            </style>
            """
            st.markdown(css_completo, unsafe_allow_html=True)

def load_logo(height="80px"):
    """Carga el logo de DocuMarval"""
    logo_path = os.path.join(os.path.dirname(__file__), "Logo.svg")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(__file__), "Logo_DocuMarval.svg")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, "r", encoding="utf-8") as f:
                logo_svg = f.read().strip()
                logo_encoded = urllib.parse.quote(logo_svg)
                return f'<img src="data:image/svg+xml;charset=utf-8,{logo_encoded}" alt="DocuMarval" style="display: block; width: auto; height: {height}; object-fit: contain; margin: 0; padding: 0;" />'
        except Exception as e:
            logger.warning(f"Error cargando logo: {e}")
            return '<h2 style="color: var(--white); margin: 0; font-size: 2rem; font-weight: 700;">DocuMarval</h2>'
    else:
        return '<h2 style="color: var(--white); margin: 0; font-size: 2rem; font-weight: 700;">DocuMarval</h2>'

def main():
    """Función principal de la aplicación"""
    st.set_page_config(
        page_title="DocuMarval - Extractor Inteligente de Facturas",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Cargar CSS personalizado
    load_custom_css()
    
    # Header principal
    header_logo_html = load_logo("238px")
    st.markdown(f"""
    <div class="main-header">
        <div class="header-content">
            <div class="header-title-container">
                <div class="header-logo">
                    {header_logo_html}
                </div>
                <h1>Extractor Inteligente de Facturas</h1>
            </div>
            <p class="subtitle">Extrae <strong>datos de facturas escaneadas</strong> en segundos con IA</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Banner de estado del sistema
    st.markdown("### Estado del Sistema")
    col1, col2 = st.columns(2)
    
    with col1:
        status_class = "success" if config.gemini_api_key else "error"
        status_text = f"Gemini AI ({config.gemini_model})" if config.gemini_api_key else "Gemini API no configurada"
        status_icon = "✓" if config.gemini_api_key else "✗"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">{status_icon}</span>
                <strong style="color: var(--white);">{status_text}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        status_class = "success" if config.poppler_disponible else "error"
        status_text = "Poppler disponible" if config.poppler_disponible else "Poppler requerido"
        status_icon = "✓" if config.poppler_disponible else "✗"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">{status_icon}</span>
                <strong style="color: var(--white);">{status_text}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
        <h3 style="color: var(--brand-300); margin-bottom: 1rem; font-size: 1.25rem;">Sistema de Extracción con IA</h3>
        <ul style="color: var(--gray-300); line-height: 2; margin: 0; padding-left: 1.5rem;">
            <li><strong style="color: var(--white);">Powered by Gemini AI:</strong> Extracción precisa usando Google Gemini</li>
            <li><strong style="color: var(--white);">Procesamiento Paralelo:</strong> Análisis simultáneo de múltiples páginas</li>
            <li><strong style="color: var(--white);">Optimizado:</strong> Especializado para facturas de servicios públicos colombianos</li>
            <li><strong style="color: var(--white);">Alta precisión:</strong> Análisis inteligente de imágenes con reconocimiento avanzado</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("""
        <h2 style="color: var(--brand-300); margin-bottom: 1.5rem;">Información del Sistema</h2>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="status-card success">
            <div style="color: var(--white);">
                <strong style="color: var(--brand-300);">Modelo:</strong> {config.gemini_model}<br>
                <strong style="color: var(--brand-300);">API Key:</strong> {'<span style="color: var(--brand-400);">✓ Configurada</span>' if config.gemini_api_key else '<span style="color: #EF4444;">✗ No configurada</span>'}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # Upload
    st.markdown("### Cargar Documento")
    uploaded_file = st.file_uploader(
        "Selecciona tu archivo PDF con facturas",
        type=['pdf'],
        help="Sube un archivo PDF que contenga facturas de servicios públicos"
    )
    
    if uploaded_file:
        if not config.poppler_disponible:
            st.markdown("""
            <div class="status-card error">
                <strong style="color: var(--white);">Error: No se puede procesar PDF sin Poppler instalado</strong>
                <p style="margin-top: 0.5rem; color: var(--gray-300);">
                    Instala Poppler siguiendo las instrucciones en el sidebar
                </p>
            </div>
            """, unsafe_allow_html=True)
            return
        
        # Validar archivo
        uploaded_file.seek(0, 2)
        file_size = uploaded_file.tell()
        uploaded_file.seek(0)
        
        if file_size > config.max_pdf_size:
            size_mb = file_size / (1024 * 1024)
            max_mb = config.max_pdf_size / (1024 * 1024)
            logger.warning(f"Archivo demasiado grande: {size_mb:.1f} MB (máximo: {max_mb} MB)")
            st.error(f"El archivo es demasiado grande ({size_mb:.1f} MB). Máximo permitido: {max_mb} MB")
            return
        
        if uploaded_file.type != 'application/pdf':
            logger.warning(f"Tipo de archivo inválido: {uploaded_file.type}")
            st.error("El archivo debe ser un PDF válido")
            return
        
        if st.button("Procesar Facturas", type="primary", use_container_width=True):
            if not config.gemini_api_key:
                st.markdown("""
                <div class="status-card error">
                    <strong style="color: var(--white);">Error: No se encontró la API key de Gemini</strong>
                    <p style="margin-top: 0.5rem; color: var(--gray-300);">
                        Configúrala en el archivo .env de la aplicación
                    </p>
                </div>
                """, unsafe_allow_html=True)
                return
            
            pdf_bytes = uploaded_file.read()
            
            # Validar PDF usando módulo de validación
            es_valido, resultado = validar_pdf(pdf_bytes, config.max_pdf_size, config.max_pages)
            if not es_valido:
                st.error(resultado)
                return
            
            # Procesar PDF usando servicio modular
            facturas, stats = procesar_pdf(pdf_bytes)
            
            if facturas:
                st.divider()
                st.balloons()
                
                st.markdown(f"""
                <div class="status-card success" style="text-align: center; padding: 2rem;">
                    <h2 style="color: var(--brand-300); margin: 0;">Procesamiento Completado</h2>
                    <p style="font-size: 1.2rem; margin-top: 0.5rem; color: var(--gray-300);">
                        {len(facturas)} factura(s) procesada(s) exitosamente
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                # Estadísticas
                st.markdown("### Estadísticas de Procesamiento")
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{stats['total']}</div>
                        <div class="metric-label">Total</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{stats['gemini']}</div>
                        <div class="metric-label">Procesadas</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col3:
                    precision = "100%" if stats['gemini'] == stats['total'] else "N/A"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{precision}</div>
                        <div class="metric-label">Precisión</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{config.gemini_model.split('-')[1] if '-' in config.gemini_model else 'AI'}</div>
                        <div class="metric-label">Modelo</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                # DataFrame
                df = pd.DataFrame(facturas)
                columnas_orden = ['pagina', 'numero_contrato', 'direccion', 'codigo_referencia',
                                 'total_pagar', 'empresa', 'periodo_facturado', 
                                 'fecha_vencimiento', 'metodo_extraccion']
                columnas_existentes = [col for col in columnas_orden if col in df.columns]
                df = df[columnas_existentes]
                
                st.markdown("### Resultados Extraídos")
                st.dataframe(df, use_container_width=True)
                
                # Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Facturas')
                    pd.DataFrame([stats]).to_excel(writer, index=False, sheet_name='Estadísticas')
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="Descargar Excel",
                    data=excel_data,
                    file_name=f"facturas_{sanitize_html(uploaded_file.name.replace('.pdf', ''))}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()

