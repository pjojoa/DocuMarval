import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
import google.generativeai as genai
from pdf2image import convert_from_bytes
import pandas as pd
import json
import re
from io import BytesIO
import os
import platform
import subprocess
from dotenv import load_dotenv

load_dotenv()

# ==================== FUNCIÓN HELPER PARA SECRETS ====================

def get_secret(key, default=None):
    """Obtiene un secreto de forma segura, manejando cuando no existe secrets.toml"""
    try:
        # Intentar acceder a st.secrets - puede lanzar StreamlitSecretNotFoundError
        # si no existe el archivo secrets.toml
        return st.secrets.get(key, default)
    except (StreamlitSecretNotFoundError, AttributeError, KeyError, FileNotFoundError, Exception):
        # Si no existe secrets.toml o hay cualquier error, retornar el valor por defecto
        return default

# ==================== DETECCIÓN AUTOMÁTICA DE DEPENDENCIAS ====================

def detectar_poppler():
    """Detecta si Poppler está disponible y retorna su ruta"""
    poppler_path = os.getenv('POPPLER_PATH') or get_secret("POPPLER_PATH", None)
    
    if poppler_path and os.path.exists(poppler_path):
        return True, poppler_path
    
    if platform.system() == 'Windows':
        rutas_comunes = [
            r'C:\Program Files\poppler-25.07.0\Library\bin',
                r'C:\Program Files\poppler\Library\bin',
                r'C:\poppler\Library\bin',
            ]
        for ruta in rutas_comunes:
                if os.path.exists(ruta):
                    return True, ruta
        
    try:
        subprocess.run(['pdftoppm', '-v'], capture_output=True, timeout=2, check=False)
        return True, None
    except:
        return False, None

# Realizar detección al inicio
POPPLER_DISPONIBLE, POPPLER_PATH = detectar_poppler()

# ==================== CONFIGURACIÓN ====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or get_secret("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv('GEMINI_MODEL') or get_secret("GEMINI_MODEL", "gemini-2.5-flash")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==================== EXTRACCIÓN CON GEMINI ====================

# Cachear el modelo de Gemini para mejor rendimiento
@st.cache_resource
def get_gemini_model():
    """Obtiene el modelo de Gemini (cacheado)"""
    if not GEMINI_API_KEY:
        return None
    return genai.GenerativeModel(GEMINI_MODEL)

# Prompt optimizado (constante)
PROMPT_GEMINI = """Analiza ÚNICAMENTE esta factura de servicios públicos colombiana (agua, luz, gas, internet, telefonía) y extrae SOLO los datos financieros y de identificación relevantes.

IMPORTANTE - IGNORA COMPLETAMENTE:
- Texto publicitario, información demográfica, estadísticas
- Información sobre "adultos mayores", "familias", "grupos demográficos"
- Números de teléfono (NO los uses como código de referencia o contrato)
- Información que NO sea parte de los datos de la factura

JSON requerido (SOLO estos campos):
{
    "numero_contrato": "número de contrato del servicio (string, vacío si no existe)",
    "direccion": "dirección del inmueble donde se presta el servicio (string, vacío si no existe)",
    "codigo_referencia": "código de referencia para pago electrónico/PSE (string, vacío si no existe)",
    "total_pagar": número decimal sin símbolos de moneda (ejemplo: 125000.50, 0 si no existe),
    "empresa": "nombre de la empresa de servicios públicos (string, vacío si no existe)",
    "periodo_facturado": "periodo de facturación (ejemplo: 'Enero 2024', '01/2024', vacío si no existe)",
    "fecha_vencimiento": "fecha de vencimiento en formato DD/MM/YYYY (string, vacío si no existe)",
    "numero_factura": "número de factura o recibo (string, vacío si no existe)",
    "nit_empresa": "NIT de la empresa (string, vacío si no existe)",
    "consumo": número decimal del consumo en unidades (ejemplo: 150.5, 0 si no aplica o no existe),
    "medidor": "número de medidor si aplica (string, vacío si no existe)"
}

REGLAS ESTRICTAS:
1. numero_contrato: Busca SOLO en "CONTRATO", "No. CONTRATO", "Código Cliente". NO uses números de teléfono, cédulas, o números aleatorios.
2. direccion: SOLO la dirección física del inmueble. NO incluyas direcciones de oficinas, páginas web, o información de contacto.
3. codigo_referencia: SOLO códigos de referencia para pago (PSE, código de barras, referencia de pago). NO uses números de teléfono, cédulas, o números aleatorios.
4. total_pagar: SOLO el monto total a pagar de la factura. Extrae SOLO números, sin símbolos $, puntos de miles, o comas.
5. empresa: SOLO el nombre de la empresa de servicios públicos. NO incluyas información adicional.
6. consumo: SOLO si es un servicio medido (agua, luz, gas). Si no aplica o no existe, usa 0.
7. medidor: SOLO el número de medidor físico. NO uses otros números.

VALIDACIÓN CRÍTICA:
- NO extraigas información demográfica, estadísticas, o texto publicitario
- NO uses números de teléfono como código de referencia o contrato
- NO incluyas información que no esté directamente relacionada con la factura
- Si un campo no está visible o no existe en la factura, usa "" para strings y 0 para números

Devuelve ÚNICAMENTE el JSON válido, sin markdown, sin explicaciones, sin texto adicional."""

GENERATION_CONFIG = {
    "temperature": 0.1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048,  # Aumentado para evitar truncamiento
}

def extraer_con_gemini(imagen):
    """Extrae datos usando Gemini Vision optimizado"""
    if not GEMINI_API_KEY:
        st.error("Error: GEMINI_API_KEY no configurada")
        return None
    
    try:
        model = get_gemini_model()
        if not model:
            return None
        
        # Convertir imagen optimizada (calidad balanceada)
        img_buffer = BytesIO()
        imagen.save(img_buffer, format='JPEG', quality=90, optimize=True)
        
        response = model.generate_content(
            [PROMPT_GEMINI, {'mime_type': 'image/jpeg', 'data': img_buffer.getvalue()}],
            generation_config=GENERATION_CONFIG
        )
        
        # Verificar que la respuesta tenga contenido válido
        if not response.candidates:
            st.error("Error: No se recibió respuesta de Gemini")
            return None
        
        candidate = response.candidates[0]
        
        # Obtener el texto de forma segura - intentar múltiples métodos
        texto = ""
        
        # Método 1: Intentar acceder directamente a response.text (más confiable)
        try:
            texto = response.text
        except (AttributeError, ValueError) as e:
            # Método 2: Acceder a través de candidate.content.parts
            if hasattr(candidate, 'content') and candidate.content:
                if hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            texto += part.text
                elif hasattr(candidate.content, 'text'):
                    texto = candidate.content.text
        
        # Verificar finish_reason después de intentar obtener el texto
        finish_reason = getattr(candidate, 'finish_reason', None)
        
        # Si no hay texto pero finish_reason es 2 (MAX_TOKENS), intentar con más tokens
        if not texto and finish_reason == 2:
            st.warning("La respuesta fue detenida por límite de tokens. Reintentando con más tokens...")
            config_extended = GENERATION_CONFIG.copy()
            config_extended["max_output_tokens"] = 2048
            try:
                response = model.generate_content(
                    [PROMPT_GEMINI, {'mime_type': 'image/jpeg', 'data': img_buffer.getvalue()}],
                    generation_config=config_extended
                )
                if response.candidates:
                    candidate = response.candidates[0]
                    try:
                        texto = response.text
                    except (AttributeError, ValueError):
                        if hasattr(candidate, 'content') and candidate.content:
                            if hasattr(candidate.content, 'parts'):
                                for part in candidate.content.parts:
                                    if hasattr(part, 'text') and part.text:
                                        texto += part.text
                # Verificar finish_reason actualizado
                if response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', finish_reason)
            except Exception as e:
                st.warning(f"No se pudo reintentar: {str(e)}")
        
        # Si aún no tenemos texto, verificar si hay bloqueos de seguridad
        if not texto:
            if finish_reason == 3:
                st.error("La respuesta fue bloqueada por filtros de seguridad. Verifica que la imagen no contenga contenido sensible.")
            elif finish_reason == 2:
                st.error("Error: La respuesta fue detenida por límite de tokens y no se pudo recuperar.")
            else:
                st.error(f"Error: No se pudo extraer texto de la respuesta. Finish reason: {finish_reason}")
            return None
        
        texto = texto.strip()
        texto = re.sub(r'```json\s*|```\s*', '', texto).strip()
        
        # Extraer JSON si está envuelto
        json_match = re.search(r'\{.*\}', texto, re.DOTALL)
        if json_match:
            texto = json_match.group(0)
        
        datos = json.loads(texto)
        
        if not isinstance(datos, dict):
            raise ValueError("Respuesta no es un diccionario válido")
        
        # Validar y limpiar datos extraídos
        # Filtrar información irrelevante o incorrecta
        palabras_prohibidas = ['adultos', 'mayores', 'millones', 'dólares', 'familia', 'demográfico', 'grupo', 'estadística']
        
        # Limpiar campos de texto
        for campo in ['numero_contrato', 'direccion', 'codigo_referencia', 'empresa', 'periodo_facturado', 'fecha_vencimiento', 'numero_factura', 'nit_empresa', 'medidor']:
            if campo in datos and isinstance(datos[campo], str):
                texto_campo = datos[campo].lower()
                # Si contiene palabras prohibidas, limpiar o vaciar
                if any(palabra in texto_campo for palabra in palabras_prohibidas):
                    datos[campo] = ""
                # Limpiar espacios y caracteres extraños
                datos[campo] = datos[campo].strip()
                # Si es muy largo y parece contener texto publicitario, truncar o limpiar
                if len(datos[campo]) > 200:
                    datos[campo] = datos[campo][:200].strip()
        
        # Validar código de referencia (no debe ser un número de teléfono típico)
        if "codigo_referencia" in datos and datos["codigo_referencia"]:
            ref = datos["codigo_referencia"].strip()
            # Si parece un número de teléfono (10 dígitos seguidos), limpiar
            if re.match(r'^\d{10}$', ref.replace(' ', '').replace('-', '')):
                datos["codigo_referencia"] = ""
        
        # Normalizar total_pagar
        if "total_pagar" in datos:
            try:
                if isinstance(datos["total_pagar"], str):
                    # Limpiar texto que no sea numérico
                    texto_limpio = re.sub(r'[^\d.]', '', datos["total_pagar"])
                    # Si contiene palabras prohibidas, usar 0
                    if any(palabra in datos["total_pagar"].lower() for palabra in palabras_prohibidas):
                        datos["total_pagar"] = 0.0
                    else:
                        datos["total_pagar"] = float(texto_limpio or 0)
                else:
                    datos["total_pagar"] = float(datos["total_pagar"])
            except:
                datos["total_pagar"] = 0.0
        
        # Validar consumo (debe ser razonable)
        if "consumo" in datos:
            try:
                consumo_val = float(datos["consumo"])
                # Si el consumo es excesivamente alto (probablemente error), usar 0
                if consumo_val > 1000000:  # Límite razonable
                    datos["consumo"] = 0.0
                else:
                    datos["consumo"] = consumo_val
            except:
                datos["consumo"] = 0.0
        
        return datos
        
    except json.JSONDecodeError as e:
        st.error(f"Error al parsear JSON: {str(e)}")
        if 'texto' in locals():
            st.info(f"Respuesta recibida: {texto[:500]}...")
        return None
    except Exception as e:
        st.error(f"Error con Gemini: {str(e)}")
        return None

# ==================== EXTRACCIÓN DE DATOS CON GEMINI ====================

def extraer_datos_factura(imagen):
    """
    Extrae datos de factura usando exclusivamente Gemini AI
    """
    with st.spinner("Extrayendo datos con Gemini AI..."):
        datos = extraer_con_gemini(imagen)
        
        if datos:
            st.success("✓ Datos extraídos exitosamente")
            return datos, "Gemini"
        else:
            st.error("✗ Error al extraer datos")
            return {}, "Gemini"

# ==================== PROCESAMIENTO DE PDF ====================

def procesar_pdf(pdf_bytes):
    """Procesa un PDF y extrae datos de facturas"""
    try:
        with st.spinner("Convirtiendo PDF a imágenes..."):
            kwargs = {'dpi': 200}  # DPI reducido para mayor velocidad
            if POPPLER_PATH and platform.system() == 'Windows':
                kwargs['poppler_path'] = POPPLER_PATH
            imagenes = convert_from_bytes(pdf_bytes, **kwargs)
        
        st.success(f"{len(imagenes)} página(s) convertida(s)")
        
    except Exception as e:
        st.error(f"Error al convertir PDF: {str(e)}")
        if not POPPLER_DISPONIBLE:
            st.warning("Poppler no está instalado.")
        return [], {}
    
    resultados = []
    estadisticas = {"gemini": 0, "total": len(imagenes)}
    progress_bar = st.progress(0)
    
    for i, imagen in enumerate(imagenes):
        st.divider()
        st.markdown(f"### Factura {i+1} de {len(imagenes)}")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(imagen, caption=f"Página {i+1}", use_container_width=True)
        
        with col2:
            datos, metodo = extraer_datos_factura(imagen)
            estadisticas[metodo.lower()] += 1
            
            if datos:
                datos["pagina"] = i + 1
                datos["metodo_extraccion"] = metodo
                resultados.append(datos)
                
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Contrato", datos.get("numero_contrato") or "N/A")
                    st.metric("Total", f"${datos.get('total_pagar', 0):,.0f}")
                    if datos.get("empresa"):
                        st.metric("Empresa", datos.get("empresa"))
                
                with col_b:
                    ref = datos.get("codigo_referencia") or "N/A"
                    st.metric("Referencia", ref[:20] + "..." if len(ref) > 20 and ref != "N/A" else ref)
                    dir_val = datos.get("direccion") or "N/A"
                    st.metric("Dirección", dir_val[:25] + "..." if len(dir_val) > 25 and dir_val != "N/A" else dir_val)
                    if datos.get("periodo_facturado"):
                        st.metric("Periodo", datos.get("periodo_facturado"))
                
                with st.expander("Ver todos los datos", expanded=False):
                    st.json(datos)
        
        progress_bar.progress((i + 1) / len(imagenes))
    
    return resultados, estadisticas

# ==================== FUNCIONES DE UI Y ESTILOS ====================

def load_custom_css():
    """Carga el CSS personalizado con identidad visual DocuMarval"""
    css = """
    <style>
    :root {
        /* Paleta corporativa DocuMarval */
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
        
        /* Tokens de diseño */
        --radius-md: 14px;
        --radius-lg: 16px;
        --elevation-1: 0 8px 24px rgba(0, 0, 0, 0.12);
        --elevation-2: 0 16px 36px rgba(0, 0, 0, 0.16);
        --glass-bg: rgba(255, 255, 255, 0.1);
        --glass-border: rgba(207, 225, 255, 0.3);
    }
    
    /* Fondo principal con gradiente futurista */
    .stApp {
        background: linear-gradient(135deg, var(--brand-900) 0%, var(--brand-800) 50%, var(--brand-700) 100%);
        background-attachment: fixed;
        color: var(--white);
        min-height: 100vh;
    }
    
    /* Grid pattern sutil de fondo */
    .stApp::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background-image: 
            linear-gradient(rgba(47, 125, 235, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(47, 125, 235, 0.03) 1px, transparent 1px);
        background-size: 50px 50px;
        pointer-events: none;
        z-index: 0;
    }
    
    /* Navbar estilo DocuMarval */
    .navbar-container {
        position: sticky;
        top: 0;
        z-index: 100;
        background: linear-gradient(135deg, var(--brand-800) 0%, var(--brand-700) 100%);
        border-bottom: 1px solid var(--brand-600);
        backdrop-filter: blur(10px);
        box-shadow: var(--elevation-1);
        padding: 1.5rem 0;
    }
    
    .navbar-content {
        max-width: 100%;
        margin: 0 auto;
        padding: 0 2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 120px;
        min-height: 120px;
    }
    
    .logo-container {
        flex: 0 1 auto;
        display: flex;
        align-items: center;
        min-width: 0;
        position: relative;
    }
    
    .logo-container img {
        height: 80px;
        width: auto;
        min-width: 300px;
        max-width: 100%;
        filter: brightness(1.1);
        object-fit: contain;
        display: block;
        position: relative;
        z-index: 1;
    }
    
    @media (max-width: 768px) {
        .logo-container img {
            height: 60px;
            min-width: 250px;
        }
    }
    
    .logo-container h2 {
        font-size: 2rem;
        font-weight: 700;
    }
    
    /* Header principal mejorado - Diseño innovador y llamativo */
    .main-header {
        background: linear-gradient(135deg, rgba(20, 184, 166, 0.15) 0%, rgba(0, 209, 255, 0.1) 100%);
        backdrop-filter: blur(20px);
        border: 2px solid rgba(20, 184, 166, 0.3);
        border-radius: 24px;
        padding: 4rem 3rem;
        margin: 2rem auto;
        max-width: 1400px;
        box-shadow: 0 8px 32px rgba(20, 184, 166, 0.2), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
        position: relative;
        z-index: 1;
        overflow: hidden;
    }
    
    .main-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--brand-400), transparent);
        animation: shimmer 3s infinite;
    }
    
    @keyframes shimmer {
        0%, 100% { opacity: 0.5; }
        50% { opacity: 1; }
    }
    
    .header-content {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
        align-items: center;
        text-align: center;
        position: relative;
        z-index: 2;
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
        filter: drop-shadow(0 4px 12px rgba(20, 184, 166, 0.4));
        transition: transform 0.3s ease, filter 0.3s ease;
    }
    
    .header-logo img {
        height: 238px;
        width: auto;
        object-fit: contain;
        display: block;
    }
    
    .header-logo:hover {
        transform: scale(1.05);
        filter: drop-shadow(0 6px 16px rgba(20, 184, 166, 0.6));
    }
    
    .main-header h1 {
        color: var(--white);
        font-weight: 800;
        font-size: 3.5rem;
        margin: 0;
        line-height: 1.1;
        letter-spacing: -0.02em;
        background: linear-gradient(135deg, #FFFFFF 0%, var(--brand-200) 50%, var(--brand-400) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-shadow: 0 0 30px rgba(20, 184, 166, 0.3);
        position: relative;
        text-align: center;
    }
    
    .main-header h1::after {
        content: '';
        position: absolute;
        bottom: -8px;
        left: 50%;
        transform: translateX(-50%);
        width: 60%;
        height: 3px;
        background: linear-gradient(90deg, transparent, var(--brand-400), transparent);
        border-radius: 2px;
        opacity: 0.6;
    }
    
    .main-header .subtitle {
        color: var(--gray-200);
        font-size: 1.35rem;
        margin: 0;
        font-weight: 400;
        line-height: 1.7;
        max-width: 900px;
        text-align: center;
    }
    
    .main-header .subtitle strong {
        color: var(--brand-300);
        font-weight: 600;
        background: linear-gradient(135deg, var(--brand-300), var(--brand-400));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    @media (max-width: 768px) {
        .main-header {
            padding: 2.5rem 1.5rem;
        }
        
        .main-header h1 {
            font-size: 2.5rem;
        }
        
        .header-logo {
            height: 170px;
        }
        
        .header-logo img {
            height: 170px;
        }
        
        .header-title-container {
            gap: 1.25rem;
        }
        
        .main-header .subtitle {
            font-size: 1.15rem;
        }
    }
    
    .navbar-content {
        gap: 2rem;
    }
    
    /* Cards con efecto glass */
    .status-card {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border: 1px solid var(--glass-border);
        border-radius: var(--radius-md);
        padding: 1.5rem;
        margin: 0.5rem 0;
        transition: all 0.2s ease;
        box-shadow: var(--elevation-1);
    }
    
    .status-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--elevation-2);
        border-color: var(--brand-300);
    }
    
    .status-card.success {
        border-left: 4px solid var(--brand-400);
    }
    
    .status-card.warning {
        border-left: 4px solid var(--brand-300);
    }
    
    .status-card.error {
        border-left: 4px solid #EF4444;
    }
    
    /* Metric cards */
    .metric-card {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border: 1px solid var(--glass-border);
        border-radius: var(--radius-md);
        padding: 1.5rem;
        text-align: center;
        transition: all 0.2s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: var(--brand-300);
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
        letter-spacing: 0.05em;
    }
    
    /* Botones primarios */
    .stButton > button {
        background: linear-gradient(135deg, var(--brand-500) 0%, var(--brand-400) 100%);
        color: var(--white);
        border: none;
        border-radius: var(--radius-md);
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.2s ease;
        box-shadow: var(--elevation-1);
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, var(--brand-400) 0%, var(--brand-300) 100%);
        transform: translateY(-2px);
        box-shadow: var(--elevation-2);
    }
    
    .stButton > button:focus {
        outline: 2px solid var(--brand-300);
        outline-offset: 2px;
    }
    
    /* File uploader */
    .stFileUploader > div {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border: 2px dashed var(--glass-border);
        border-radius: var(--radius-md);
        padding: 2rem;
        transition: all 0.2s ease;
    }
    
    .stFileUploader > div:hover {
        border-color: var(--brand-300);
        background: rgba(255, 255, 255, 0.15);
    }
    
    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, var(--brand-500) 0%, var(--brand-400) 100%);
        border-radius: var(--radius-md);
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: var(--brand-900);
        border-right: 1px solid var(--brand-600);
    }
    
    /* Inputs y selects */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select {
        border: 1px solid var(--gray-300);
        border-radius: var(--radius-md);
        transition: all 0.2s ease;
    }
    
    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div > select:focus {
        border-color: var(--brand-300);
        outline: 2px solid var(--brand-300);
        outline-offset: 2px;
    }
    
    /* Tablas */
    .dataframe {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border-radius: var(--radius-md);
        border: 1px solid var(--glass-border);
    }
    
    .dataframe thead {
        background: var(--brand-100);
        color: var(--brand-900);
    }
    
    .dataframe tbody tr:nth-child(even) {
        background: rgba(255, 255, 255, 0.05);
    }
    
    .dataframe tbody tr:hover {
        background: rgba(47, 125, 235, 0.1);
    }
    
    /* Scrollbar personalizado */
    ::-webkit-scrollbar {
        width: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--brand-900);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--brand-500);
        border-radius: 5px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: var(--brand-400);
    }
    
    /* Contenedor principal */
    .main-container {
        max-width: 1280px;
        margin: 0 auto;
        padding: 0 1.5rem;
        position: relative;
        z-index: 1;
    }
    
    /* Info box */
    .info-box {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border: 1px solid var(--glass-border);
        border-left: 4px solid var(--brand-400);
        border-radius: var(--radius-md);
        padding: 1.5rem;
        margin: 2rem 0;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background: var(--glass-bg);
        backdrop-filter: blur(10px);
        border-radius: var(--radius-md);
        padding: 1rem;
        border: 1px solid var(--glass-border);
    }
    
    /* Métricas de Streamlit */
    [data-testid="stMetricValue"] {
        color: var(--brand-300);
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--gray-300);
    }
    
    /* Títulos y subtítulos */
    h1, h2, h3 {
        color: var(--white);
    }
    
    h3 {
        color: var(--brand-300);
    }
    
    /* Links */
    a {
        color: var(--brand-300);
        text-decoration: none;
        transition: color 0.2s ease;
    }
    
    a:hover {
        color: var(--brand-400);
    }
    
    /* Dividers */
    hr {
        border-color: var(--brand-600);
        margin: 1.5rem 0;
    }
    
    /* Success/Error/Warning messages */
    .stSuccess {
        background: rgba(47, 125, 235, 0.1);
        border-left: 4px solid var(--brand-400);
        border-radius: var(--radius-md);
    }
    
    .stError {
        background: rgba(239, 68, 68, 0.1);
        border-left: 4px solid #EF4444;
        border-radius: var(--radius-md);
    }
    
    .stWarning {
        background: rgba(114, 168, 255, 0.1);
        border-left: 4px solid var(--brand-300);
        border-radius: var(--radius-md);
    }
    
    .stInfo {
        background: rgba(47, 125, 235, 0.1);
        border-left: 4px solid var(--brand-400);
        border-radius: var(--radius-md);
    }
    
    /* Spinner */
    .stSpinner > div {
        border-color: var(--brand-400) transparent transparent transparent;
    }
    
    /* Mejoras de accesibilidad - Focus states */
    button:focus-visible,
    input:focus-visible,
    select:focus-visible {
        outline: 2px solid var(--brand-300);
        outline-offset: 2px;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ==================== INTERFAZ STREAMLIT ====================

def main():
    st.set_page_config(
        page_title="DocuMarval - Extractor Inteligente de Facturas",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Cargar CSS personalizado
    load_custom_css()
    
    # Función para cargar el logo
    def load_logo(height="80px"):
        logo_path = os.path.join(os.path.dirname(__file__), "Logo.svg")
        
        # Si no existe Logo.svg, intentar con Logo_DocuMarval.svg
        if not os.path.exists(logo_path):
            logo_path = os.path.join(os.path.dirname(__file__), "Logo_DocuMarval.svg")
        
        if os.path.exists(logo_path):
            import urllib.parse
            try:
                with open(logo_path, "r", encoding="utf-8") as f:
                    logo_svg = f.read()
                    # Limpiar el SVG de posibles duplicados
                    logo_svg = logo_svg.strip()
                    # Codificar SVG para uso en data URI
                    logo_encoded = urllib.parse.quote(logo_svg)
                    return f'<img src="data:image/svg+xml;charset=utf-8,{logo_encoded}" alt="DocuMarval" style="display: block; width: auto; height: {height}; object-fit: contain; margin: 0; padding: 0;" />'
            except Exception as e:
                return '<h2 style="color: var(--white); margin: 0; font-size: 2rem; font-weight: 700;">DocuMarval</h2>'
        else:
            return '<h2 style="color: var(--white); margin: 0; font-size: 2rem; font-weight: 700;">DocuMarval</h2>'
    
    # Header principal mejorado con logo - Diseño innovador
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
        status_class = "success" if GEMINI_API_KEY else "error"
        status_text = f"Gemini AI ({GEMINI_MODEL})" if GEMINI_API_KEY else "Gemini API no configurada"
        status_icon = "✓" if GEMINI_API_KEY else "✗"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">{status_icon}</span>
                <strong style="color: var(--white);">{status_text}</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        status_class = "success" if POPPLER_DISPONIBLE else "error"
        status_text = "Poppler disponible" if POPPLER_DISPONIBLE else "Poppler requerido"
        status_icon = "✓" if POPPLER_DISPONIBLE else "✗"
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
            <li><strong style="color: var(--white);">Powered by Gemini AI:</strong> Extracción precisa usando Google Gemini 2.5 Flash</li>
            <li><strong style="color: var(--white);">Extracción automática:</strong> No. Contrato, Dirección, Código de Referencia, Total a Pagar y más</li>
            <li><strong style="color: var(--white);">Optimizado:</strong> Especializado para facturas de servicios públicos colombianos</li>
            <li><strong style="color: var(--white);">Alta precisión:</strong> Análisis inteligente de imágenes con reconocimiento avanzado</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Mostrar ejemplo de campos
    with st.expander("Campos que se extraen", expanded=False):
        st.markdown("""
        <div style="color: var(--gray-300);">
        <ol style="line-height: 2;">
            <li><strong style="color: var(--white);">No. CONTRATO:</strong> Número de contrato del cliente</li>
            <li><strong style="color: var(--white);">Dirección:</strong> Dirección completa del inmueble</li>
            <li><strong style="color: var(--white);">Código de Referencia:</strong> Para pago electrónico/PSE</li>
            <li><strong style="color: var(--white);">TOTAL A PAGAR:</strong> Monto final a pagar</li>
            <li><strong style="color: var(--white);">Adicionales:</strong> Empresa, periodo, fecha de vencimiento</li>
        </ol>
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
                <strong style="color: var(--brand-300);">Modelo:</strong> {GEMINI_MODEL}<br>
                <strong style="color: var(--brand-300);">API Key:</strong> {'<span style="color: var(--brand-400);">✓ Configurada</span>' if GEMINI_API_KEY else '<span style="color: #EF4444;">✗ No configurada</span>'}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        
        with st.expander("Instalación de dependencias", expanded=False):
            st.markdown("""
            <div style="color: var(--gray-300);">
            <h4 style="color: var(--brand-300);">Para Windows (desarrollo local):</h4>
            <ul>
                <li>Poppler: <a href="https://github.com/oschwartz10612/poppler-windows/releases" target="_blank" style="color: var(--brand-300);">Descargar</a></li>
            </ul>
            
            <h4 style="color: var(--brand-300);">Para Streamlit Cloud (deployment):</h4>
            <p>Crea <code style="background: var(--brand-800); padding: 0.25rem 0.5rem; border-radius: 4px; color: var(--brand-300);">packages.txt</code>:</p>
            <pre style="background: var(--brand-800); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--brand-600); color: var(--gray-300);">
            poppler-utils
            </pre>
            
            <h4 style="color: var(--brand-300);">Variables de entorno requeridas:</h4>
            <pre style="background: var(--brand-800); padding: 1rem; border-radius: var(--radius-md); border: 1px solid var(--brand-600); color: var(--gray-300);">
GEMINI_API_KEY=tu_api_key_aqui
GEMINI_MODEL=gemini-2.5-flash
            </pre>
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
        if not POPPLER_DISPONIBLE:
            st.markdown("""
            <div class="status-card error">
                <strong style="color: var(--white);">Error: No se puede procesar PDF sin Poppler instalado</strong>
                <p style="margin-top: 0.5rem; color: var(--gray-300);">
                    Instala Poppler siguiendo las instrucciones en el sidebar
                </p>
            </div>
            """, unsafe_allow_html=True)
            return
        
        if st.button("Procesar Facturas", type="primary", use_container_width=True):
            
            if not GEMINI_API_KEY:
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
                        <div class="metric-value">{GEMINI_MODEL.split('-')[1] if '-' in GEMINI_MODEL else 'AI'}</div>
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
                    file_name=f"facturas_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

if __name__ == "__main__":
    main()