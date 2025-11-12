import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
import google.generativeai as genai
from pdf2image import convert_from_bytes
from PIL import Image
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

def detectar_tesseract():
    """Detecta si Tesseract está disponible en el sistema"""
    try:
        import pytesseract
        
        # Intentar rutas comunes en Windows
        if platform.system() == 'Windows':
            rutas_posibles = [
                r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
                r'C:\Program Files\Tesseract\tesseract.exe',
                r'C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', '')),
            ]
            
            for ruta in rutas_posibles:
                if os.path.exists(ruta):
                    pytesseract.pytesseract.tesseract_cmd = ruta
                    break
                elif os.getenv('TESSERACT_PATH') or get_secret("TESSERACT_PATH", None):
                    ruta_secrets = get_secret("TESSERACT_PATH", None) or os.getenv('TESSERACT_PATH')
                    if ruta_secrets and os.path.exists(ruta_secrets):
                        pytesseract.pytesseract.tesseract_cmd = ruta_secrets
                        break
        
        # Probar si funciona
        version = pytesseract.get_tesseract_version()
        return True, pytesseract, f"v{version}"
    except Exception as e:
        return False, None, str(e)

def detectar_opencv():
    """Detecta si OpenCV está disponible"""
    try:
        import cv2
        import numpy as np
        return True, cv2, np
    except:
        return False, None, None

def detectar_poppler():
    """Detecta si Poppler está disponible"""
    try:
        # Intentar obtener ruta de Poppler desde secrets
        poppler_path = os.getenv('POPPLER_PATH') or get_secret("POPPLER_PATH", None)
        
        # Si no hay ruta en secrets y estamos en Windows, buscar en rutas comunes
        if not poppler_path and platform.system() == 'Windows':
            rutas_posibles = [
                r'C:\Program Files\poppler\Library\bin',
                r'C:\Program Files\poppler-24.02.0\Library\bin',
                r'C:\poppler\Library\bin',
                r'C:\Program Files\poppler-25.07.0\Library\bin',
            ]
            
            for ruta in rutas_posibles:
                if os.path.exists(ruta):
                    return True, ruta
        
        # Si tenemos ruta en secrets, verificar que existe
        if poppler_path and os.path.exists(poppler_path):
            return True, poppler_path
            
        # En Linux/Mac o si no se encontró en rutas Windows, verificar si está en PATH
        result = subprocess.run(['pdftoppm', '-v'], 
                              capture_output=True, 
                              timeout=5)
        return True, None
    except:
        return False, None

# Realizar detección al inicio
TESSERACT_DISPONIBLE, pytesseract, TESSERACT_VERSION = detectar_tesseract()
OPENCV_DISPONIBLE, cv2, np = detectar_opencv()
POPPLER_DISPONIBLE, POPPLER_PATH = detectar_poppler()

# ==================== CONFIGURACIÓN ====================
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or get_secret("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==================== FUNCIONES DE PREPROCESAMIENTO (Solo si OpenCV disponible) ====================

def preprocesar_imagen(imagen):
    """Mejora la imagen para mejor OCR - Solo si OpenCV está disponible"""
    if not OPENCV_DISPONIBLE:
        return imagen
    
    try:
        # Convertir PIL a numpy array
        img_array = np.array(imagen)
        
        # Convertir a escala de grises
        gris = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        
        # Aplicar threshold adaptativo
        thresh = cv2.adaptiveThreshold(
            gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # Reducir ruido
        denoised = cv2.fastNlMeansDenoising(thresh)
        
        return Image.fromarray(denoised)
    except:
        return imagen

def calcular_confianza_ocr(texto_ocr, data_ocr=None):
    """Calcula la confianza del OCR para facturas de servicios públicos"""
    if not texto_ocr or len(texto_ocr.strip()) < 50:
        return 0
    
    # Factor 1: Longitud del texto
    factor_longitud = min(len(texto_ocr) / 500, 1.0)
    
    # Factor 2: Palabras clave de servicios públicos
    palabras_clave = ['contrato', 'total', 'pagar', 'direccion', 'referencia', 'periodo', 'factura']
    texto_lower = texto_ocr.lower()
    palabras_encontradas = sum(1 for palabra in palabras_clave if palabra in texto_lower)
    factor_palabras = palabras_encontradas / len(palabras_clave)
    
    # Factor 3: Números
    numeros = re.findall(r'\d+', texto_ocr)
    factor_numeros = min(len(numeros) / 10, 1.0)
    
    # Factor 4: Confianza de Tesseract
    factor_tesseract = 0.5
    if data_ocr:
        try:
            confidencias = [int(conf) for conf in data_ocr.get('conf', []) if int(conf) > 0]
            if confidencias:
                factor_tesseract = sum(confidencias) / len(confidencias) / 100
        except:
            pass
    
    # Factor 5: Detectar "basura" (caracteres extraños que indican OCR malo)
    caracteres_raros = len(re.findall(r'[¿¡°•★◆■□▪▫]', texto_ocr))
    factor_basura = max(0, 1 - (caracteres_raros / 50))  # Penalizar caracteres raros
    
    # Factor 6: Ratio de palabras vs caracteres extraños
    palabras = len(re.findall(r'\b[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', texto_ocr))
    factor_palabras_validas = min(palabras / 20, 1.0)
    
    confianza = (
        factor_longitud * 0.15 +
        factor_palabras * 0.25 +
        factor_numeros * 0.15 +
        factor_tesseract * 0.20 +
        factor_basura * 0.15 +
        factor_palabras_validas * 0.10
    )
    
    return confianza

# ==================== EXTRACCIÓN CON TESSERACT ====================

def extraer_con_tesseract(imagen):
    """Extrae texto usando Tesseract OCR - Solo si está disponible"""
    if not TESSERACT_DISPONIBLE:
        return "", {}
    
    try:
        # Preprocesar imagen
        img_procesada = preprocesar_imagen(imagen)
        
        # Extraer texto
        config = '--oem 3 --psm 6'
        texto = pytesseract.image_to_string(img_procesada, lang='spa', config=config)
        
        # Obtener datos detallados
        data = pytesseract.image_to_data(img_procesada, lang='spa', 
                                         output_type=pytesseract.Output.DICT)
        
        return texto, data
    except Exception as e:
        return "", {}

def parsear_factura_tesseract(texto):
    """Extrae datos estructurados del texto de Tesseract - Facturas de servicios públicos"""
    datos = {
        "numero_contrato": "",
        "direccion": "",
        "codigo_referencia": "",
        "total_pagar": 0
    }
    
    if not texto:
        return datos
    
    try:
        # Número de contrato
        match_contrato = re.search(r'(?:CONTRATO|contrato|No\.?\s*CONTRATO)\s*:?\s*([A-Z0-9-]+)', 
                                   texto, re.IGNORECASE)
        if match_contrato:
            datos["numero_contrato"] = match_contrato.group(1).strip()
        
        # Dirección - buscar después de palabras clave
        match_direccion = re.search(r'(?:DIRECCI[OÓ]N|direcci[oó]n|Dirección)\s*:?\s*([^\n]+)', 
                                    texto, re.IGNORECASE)
        if match_direccion:
            datos["direccion"] = match_direccion.group(1).strip()
        
        # Código de referencia
        match_referencia = re.search(r'(?:C[OÓ]DIGO.*?REFERENCIA|REFERENCIA.*?PAGO|REF.*?ELECTR[OÓ]NICO)\s*:?\s*([A-Z0-9-]+)', 
                                     texto, re.IGNORECASE | re.DOTALL)
        if match_referencia:
            datos["codigo_referencia"] = match_referencia.group(1).strip()
        
        # Total a pagar - buscar cerca de "TOTAL A PAGAR"
        match_total = re.search(r'(?:TOTAL\s*A\s*PAGAR|TOTAL\s*FACTURA)\s*:?\s*\$?\s*([\d,\.]+)', 
                               texto, re.IGNORECASE)
        if match_total:
            valor = match_total.group(1).replace(',', '').replace('.', '')
            try:
                # Ajustar si hay decimales (asumir últimos 2 dígitos)
                if len(valor) > 2:
                    datos["total_pagar"] = float(valor) / 100 if len(valor) <= 6 else float(valor)
                else:
                    datos["total_pagar"] = float(valor)
            except:
                pass
        
        return datos
    except:
        return datos

# ==================== EXTRACCIÓN CON GEMINI ====================

def extraer_con_gemini(imagen):
    """Extrae datos usando Gemini Vision"""
    try:
        model = genai.GenerativeModel(os.getenv('GEMINI_MODEL') or get_secret("GEMINI_MODEL", "gemini-2.5-flash"))
        
        # Convertir imagen a bytes
        img_byte_arr = BytesIO()
        imagen.save(img_byte_arr, format='JPEG', quality=95)
        img_bytes = img_byte_arr.getvalue()
        
        imagen_gemini = {
            'mime_type': 'image/jpeg',
            'data': img_bytes
        }
        
        prompt = """
        Analiza esta factura de servicios públicos y extrae la información en formato JSON.
        
        IMPORTANTE: Esta es una factura de servicios públicos (agua, luz, gas, etc.)
        
        Formato JSON requerido:
        {
            "numero_contrato": "número de contrato del cliente",
            "direccion": "dirección completa del inmueble",
            "codigo_referencia": "código de referencia para pago electrónico o PSE",
            "total_pagar": número sin símbolos de moneda (solo el valor numérico),
            "empresa": "nombre de la empresa de servicios públicos",
            "periodo_facturado": "mes y año del periodo facturado",
            "fecha_vencimiento": "fecha límite de pago"
        }
        
        INSTRUCCIONES:
        - El número de contrato puede aparecer como "No CONTRATO", "CONTRATO", "No. CONTRATO"
        - La dirección suele estar después de "DIRECCIÓN" o "Dirección"
        - El código de referencia puede aparecer como "Código de referencia", "Ref. pago electrónico", "PSE"
        - El TOTAL A PAGAR es el monto final que debe pagar el cliente
        - Si un campo no existe, usa "" para strings y 0 para números
        - Para números, NO incluyas símbolos de moneda ($), puntos o comas
        
        Devuelve SOLO el JSON, sin texto adicional ni explicaciones.
        """
        
        response = model.generate_content([prompt, imagen_gemini])
        texto_respuesta = response.text.strip()
        texto_respuesta = texto_respuesta.replace('```json', '').replace('```', '').strip()
        
        datos = json.loads(texto_respuesta)
        return datos
        
    except Exception as e:
        st.error(f"Error con Gemini: {str(e)}")
        return None

# ==================== LÓGICA HÍBRIDA ADAPTATIVA ====================

def extraer_datos_adaptativo(imagen, forzar_gemini=False, umbral_confianza=0.6):
    """
    Estrategia adaptativa:
    - Si Tesseract disponible: intenta primero con Tesseract
    - Si no disponible o confianza baja: usa Gemini
    """
    metodo_usado = ""
    texto_ocr = ""
    
    # Si NO hay Tesseract o se fuerza Gemini, usar Gemini directamente
    if not TESSERACT_DISPONIBLE or forzar_gemini:
        if not TESSERACT_DISPONIBLE:
            st.info("Tesseract no disponible, usando Gemini")
        
        with st.spinner("Extrayendo con Gemini AI..."):
            datos = extraer_con_gemini(imagen)
            metodo_usado = "Gemini"
            
            if datos:
                st.success("Extraído exitosamente con Gemini")
            else:
                st.error("Error al extraer con Gemini")
                datos = {}
            
            return datos, metodo_usado, ""
    
    # Intentar con Tesseract primero
    with st.spinner("Extrayendo con Tesseract OCR..."):
        texto_ocr, data_ocr = extraer_con_tesseract(imagen)
        confianza = calcular_confianza_ocr(texto_ocr, data_ocr)
        
        st.info(f"Confianza Tesseract: {confianza:.1%}")
        
        if confianza >= umbral_confianza:
            st.success("Calidad suficiente, usando Tesseract")
            datos = parsear_factura_tesseract(texto_ocr)
            metodo_usado = "Tesseract"
            return datos, metodo_usado, texto_ocr
        else:
            st.warning("Confianza baja, usando Gemini como respaldo...")
    
    # Usar Gemini como fallback
    with st.spinner("Extrayendo con Gemini AI..."):
        datos = extraer_con_gemini(imagen)
        metodo_usado = "Gemini"
        
        if datos:
            st.success("Extraído exitosamente con Gemini")
        else:
            st.error("Usando datos de Tesseract como fallback")
            datos = parsear_factura_tesseract(texto_ocr)
        
        return datos, metodo_usado, texto_ocr

# ==================== PROCESAMIENTO DE PDF ====================

def procesar_pdf(pdf_bytes, umbral_confianza=0.8, forzar_gemini=False):
    """Procesa un PDF con detección automática de herramientas disponibles"""
    
    try:
        with st.spinner("Convirtiendo PDF a imágenes..."):
            if POPPLER_PATH and platform.system() == 'Windows':
                imagenes = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH)
            else:
                imagenes = convert_from_bytes(pdf_bytes, dpi=300)
        
        st.success(f"{len(imagenes)} página(s) convertida(s) exitosamente")
        
    except Exception as e:
        st.error(f"Error al convertir PDF: {str(e)}")
        if not POPPLER_DISPONIBLE:
            st.warning("Poppler no está instalado. Instálalo para procesar PDFs.")
        return [], {}
    
    resultados = []
    estadisticas = {"tesseract": 0, "gemini": 0, "total": len(imagenes)}
    
    progress_bar = st.progress(0)
    
    for i, imagen in enumerate(imagenes):
        st.divider()
        st.markdown(f"### Factura {i+1} de {len(imagenes)}")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(imagen, caption=f"Página {i+1}", use_container_width=True)
        
        with col2:
            datos, metodo, texto_ocr = extraer_datos_adaptativo(
                imagen, forzar_gemini, umbral_confianza
            )
            
            estadisticas[metodo.lower()] += 1
            
            if datos:
                datos["pagina"] = i + 1
                datos["metodo_extraccion"] = metodo
                resultados.append(datos)
                
                # Mostrar resumen visual
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Contrato", datos.get("numero_contrato", "N/A"))
                    st.metric("Total", f"${datos.get('total_pagar', 0):,.0f}")
                
                with col_b:
                    st.metric("Referencia", datos.get("codigo_referencia", "N/A")[:15] + "..." if len(datos.get("codigo_referencia", "")) > 15 else datos.get("codigo_referencia", "N/A"))
                    st.metric("Dirección", datos.get("direccion", "N/A")[:20] + "..." if len(datos.get("direccion", "")) > 20 else datos.get("direccion", "N/A"))
                
                # Expandible con datos completos
                with st.expander("Ver todos los datos extraídos"):
                    st.json(datos)
                
                if texto_ocr and metodo == "Tesseract":
                    with st.expander("Ver texto OCR (Tesseract)"):
                        st.warning("Este texto puede contener errores de OCR")
                        st.text(texto_ocr[:1000] + "..." if len(texto_ocr) > 1000 else texto_ocr)
        
        progress_bar.progress((i + 1) / len(imagenes))
    
    return resultados, estadisticas

# ==================== FUNCIONES DE UI Y ESTILOS ====================

def load_custom_css():
    """Carga el CSS personalizado estilo Platzi"""
    css = """
    <style>
    :root {
        --platzi-green: #98CA3F;
        --platzi-dark: #121212;
        --platzi-darker: #0A0A0A;
        --platzi-gray: #1E1E1E;
        --platzi-light-gray: #2D2D2D;
        --platzi-text: #FFFFFF;
        --platzi-text-secondary: #B0B0B0;
        --platzi-accent: #7AB800;
        --platzi-gradient: linear-gradient(135deg, #98CA3F 0%, #7AB800 100%);
    }
    
    .stApp {
        background: var(--platzi-dark);
        color: var(--platzi-text);
    }
    
    .main-header {
        background: var(--platzi-gradient);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(152, 202, 63, 0.3);
    }
    
    .main-header h1 {
        color: var(--platzi-dark);
        font-weight: 700;
        font-size: 2.5rem;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .status-card {
        background: var(--platzi-gray);
        border: 1px solid var(--platzi-light-gray);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        transition: all 0.3s ease;
        box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    }
    
    .status-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 24px rgba(152, 202, 63, 0.2);
        border-color: var(--platzi-green);
    }
    
    .status-card.success {
        border-left: 4px solid var(--platzi-green);
    }
    
    .status-card.warning {
        border-left: 4px solid #FFA500;
    }
    
    .status-card.error {
        border-left: 4px solid #FF4444;
    }
    
    .metric-card {
        background: var(--platzi-gray);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid var(--platzi-light-gray);
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: var(--platzi-green);
        margin: 0.5rem 0;
    }
    
    .stButton > button {
        background: var(--platzi-gradient);
        color: var(--platzi-dark);
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 12px rgba(152, 202, 63, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(152, 202, 63, 0.4);
    }
    
    .stFileUploader > div {
        background: var(--platzi-gray);
        border: 2px dashed var(--platzi-light-gray);
        border-radius: 12px;
        padding: 2rem;
        transition: all 0.3s ease;
    }
    
    .stFileUploader > div:hover {
        border-color: var(--platzi-green);
        background: var(--platzi-light-gray);
    }
    
    .stProgress > div > div {
        background: var(--platzi-gradient);
    }
    
    [data-testid="stSidebar"] {
        background: var(--platzi-darker);
    }
    
    ::-webkit-scrollbar {
        width: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: var(--platzi-darker);
    }
    
    ::-webkit-scrollbar-thumb {
        background: var(--platzi-green);
        border-radius: 5px;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def get_icon_svg(icon_name):
    """Retorna SVG de iconos profesionales"""
    icons = {
        "document": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M14 2V8H20" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "upload": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M7 10L12 5L17 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 5V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "check": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "warning": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 9V13M12 17H12.01M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "error": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 8V12M12 16H12.01M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 8V12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "robot": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9V7L18.5 6.5C18.2 5.9 17.8 5.4 17.3 5.1L18 2.5L16 1.5L15.2 4.1C14.7 4 14.1 4 13.5 4H10.5C9.9 4 9.3 4 8.8 4.1L8 1.5L6 2.5L6.7 5.1C6.2 5.4 5.8 5.9 5.5 6.5L3 7V9L5.5 9.5C5.8 10.1 6.2 10.6 6.7 10.9L6 13.5L8 14.5L8.8 11.9C9.3 12 9.9 12 10.5 12H13.5C14.1 12 14.7 12 15.2 11.9L16 14.5L18 13.5L17.3 10.9C17.8 10.6 18.2 10.1 18.5 9.5L21 9ZM12 8C9.2 8 7 10.2 7 13C7 15.8 9.2 18 12 18C14.8 18 17 15.8 17 13C17 10.2 14.8 8 12 8Z" fill="currentColor"/>
        </svg>""",
        "eye": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1 12C1 12 5 4 12 4C19 4 23 12 23 12C23 12 19 20 12 20C5 20 1 12 1 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
        </svg>""",
        "settings": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M19.4 15C19.2669 15.3016 19.2272 15.6362 19.286 15.9606C19.3448 16.285 19.4995 16.5843 19.73 16.82L19.79 16.88C19.976 17.0657 20.1235 17.2863 20.2241 17.5291C20.3248 17.7719 20.3766 18.0322 20.3766 18.295C20.3766 18.5578 20.3248 18.8181 20.2241 19.0609C20.1235 19.3037 19.976 19.5243 19.79 19.71C19.6043 19.896 19.3837 20.0435 19.1409 20.1441C18.8981 20.2448 18.6378 20.2966 18.375 20.2966C18.1122 20.2966 17.8519 20.2448 17.6091 20.1441C17.3663 20.0435 17.1457 19.896 16.96 19.71L16.9 19.65C16.6643 19.4195 16.365 19.2648 16.0406 19.206C15.7162 19.1472 15.3816 19.1869 15.08 19.32C14.7842 19.4468 14.532 19.6572 14.3543 19.9255C14.1766 20.1938 14.0813 20.5082 14.08 20.83V21C14.08 21.5304 13.8693 22.0391 13.4942 22.4142C13.1191 22.7893 12.6104 23 12.08 23C11.5496 23 11.0409 22.7893 10.6658 22.4142C10.2907 22.0391 10.08 21.5304 10.08 21V20.91C10.0723 20.579 9.96512 20.258 9.77251 19.9887C9.5799 19.7194 9.31074 19.5143 9 19.4C8.69838 19.2669 8.36381 19.2272 8.03941 19.286C7.71502 19.3448 7.41568 19.4995 7.18 19.73L7.12 19.79C6.93425 19.976 6.71368 20.1235 6.47088 20.2241C6.22808 20.3248 5.96783 20.3766 5.705 20.3766C5.44217 20.3766 5.18192 20.3248 4.93912 20.2241C4.69632 20.1235 4.47575 19.976 4.29 19.79C4.10405 19.6043 3.95653 19.3837 3.85588 19.1409C3.75523 18.8981 3.70343 18.6378 3.70343 18.375C3.70343 18.1122 3.75523 17.8519 3.85588 17.6091C3.95653 17.3663 4.10405 17.1457 4.29 16.96L4.35 16.9C4.58054 16.6643 4.73519 16.365 4.794 16.0406C4.85282 15.7162 4.81312 15.3816 4.68 15.08C4.55324 14.7842 4.34276 14.532 4.07447 14.3543C3.80618 14.1766 3.49179 14.0813 3.17 14.08H3C2.46957 14.08 1.96086 13.8693 1.58579 13.4942C1.21071 13.1191 1 12.6104 1 12.08C1 11.5496 1.21071 11.0409 1.58579 10.6658C1.96086 10.2907 2.46957 10.08 3 10.08H3.09C3.42099 10.0723 3.742 9.96512 4.01131 9.77251C4.28062 9.5799 4.48571 9.31074 4.6 9C4.73312 8.69838 4.77282 8.36381 4.714 8.03941C4.65519 7.71502 4.50054 7.41568 4.27 7.18L4.21 7.12C4.02405 6.93425 3.87653 6.71368 3.77588 6.47088C3.67523 6.22808 3.62343 5.96783 3.62343 5.705C3.62343 5.44217 3.67523 5.18192 3.77588 4.93912C3.87653 4.69632 4.02405 4.47575 4.21 4.29C4.39575 4.10405 4.61632 3.95653 4.85912 3.85588C5.10192 3.75523 5.36217 3.70343 5.625 3.70343C5.88783 3.70343 6.14808 3.75523 6.39088 3.85588C6.63368 3.95653 6.85425 4.10405 7.04 4.29L7.1 4.35C7.33568 4.58054 7.63502 4.73519 7.95941 4.794C8.28381 4.85282 8.61838 4.81312 8.92 4.68H9C9.29577 4.55324 9.54802 4.34276 9.72569 4.07447C9.90337 3.80618 9.99872 3.49179 10 3.17V3C10 2.46957 10.2107 1.96086 10.5858 1.58579C10.9609 1.21071 11.4696 1 12 1C12.5304 1 13.0391 1.21071 13.4142 1.58579C13.7893 1.96086 14 2.46957 14 3V3.09C14.0013 3.41179 14.0966 3.72618 14.2743 3.99447C14.452 4.26276 14.7022 4.47324 14.998 4.6C15.2996 4.73312 15.6342 4.77282 15.9586 4.714C16.283 4.65519 16.5823 4.50054 16.818 4.27L16.878 4.21C17.064 4.02405 17.2846 3.87653 17.5274 3.77588C17.7702 3.67523 18.0305 3.62343 18.2933 3.62343C18.5562 3.62343 18.8164 3.67523 19.0592 3.77588C19.302 3.87653 19.5226 4.02405 19.7086 4.21C19.8946 4.39575 20.0421 4.61632 20.1427 4.85912C20.2434 5.10192 20.2952 5.36217 20.2952 5.625C20.2952 5.88783 20.2434 6.14808 20.1427 6.39088C20.0421 6.63368 19.8946 6.85425 19.7086 7.04L19.6486 7.1C19.418 7.33568 19.2634 7.63502 19.2046 7.95941C19.1458 8.28381 19.1855 8.61838 19.3186 8.92V9C19.4454 9.29577 19.6559 9.54802 19.9242 9.72569C20.1925 9.90337 20.5069 9.99872 20.8286 10H21C21.5304 10 22.0391 10.2107 22.4142 10.5858C22.7893 10.9609 23 11.4696 23 12C23 12.5304 22.7893 13.0391 22.4142 13.4142C22.0391 13.7893 21.5304 14 21 14H20.91C20.5882 14.0013 20.2738 14.0966 20.0055 14.2743C19.7372 14.452 19.5268 14.7022 19.4 15Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "download": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 15V19C21 19.5304 20.7893 20.0391 20.4142 20.4142C20.0391 20.7893 19.5304 21 19 21H5C4.46957 21 3.96086 20.7893 3.58579 20.4142C3.21071 20.0391 3 19.5304 3 19V15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M7 14L12 19L17 14" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 19V9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>""",
        "info": """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
            <path d="M12 16V12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            <path d="M12 8H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>"""
    }
    return icons.get(icon_name, "")

def render_icon(icon_name, color="#98CA3F", size=24):
    """Renderiza un icono SVG"""
    svg = get_icon_svg(icon_name)
    if svg:
        return f'<span style="display: inline-flex; align-items: center; color: {color};">{svg}</span>'
    return ""

# ==================== INTERFAZ STREAMLIT ====================

def main():
    st.set_page_config(
        page_title="Extractor Inteligente de Facturas",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Cargar CSS personalizado
    load_custom_css()
    
    # Header moderno estilo Platzi
    st.markdown("""
    <div class="main-header">
        <h1>Extractor Inteligente de Facturas</h1>
        <p style="color: var(--platzi-dark); margin-top: 0.5rem; font-size: 1.1rem;">
            Sistema híbrido de extracción de datos con IA
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Banner de estado del sistema
    st.markdown("### Estado del Sistema")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status_class = "success" if TESSERACT_DISPONIBLE else "warning"
        status_text = f"Tesseract {TESSERACT_VERSION}" if TESSERACT_DISPONIBLE else "Tesseract no disponible"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <strong>{status_text}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        status_class = "success" if OPENCV_DISPONIBLE else "warning"
        status_text = "OpenCV disponible" if OPENCV_DISPONIBLE else "OpenCV no disponible (opcional)"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <strong>{status_text}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        status_class = "success" if POPPLER_DISPONIBLE else "error"
        status_text = "Poppler disponible" if POPPLER_DISPONIBLE else "Poppler requerido"
        st.markdown(f"""
        <div class="status-card {status_class}">
            <strong>{status_text}</strong>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background: var(--platzi-gray); padding: 1.5rem; border-radius: 12px; margin: 2rem 0; border-left: 4px solid var(--platzi-green);">
        <h3 style="color: var(--platzi-green); margin-bottom: 1rem;">Sistema Híbrido Inteligente</h3>
        <ul style="color: var(--platzi-text-secondary); line-height: 2;">
            <li><strong>Extracción automática:</strong> No. Contrato, Dirección, Código de Referencia, Total a Pagar</li>
            <li><strong>Estrategia adaptativa:</strong> Usa Tesseract primero (gratis), Gemini como respaldo inteligente</li>
            <li><strong>Optimizado:</strong> Especializado para facturas de servicios públicos colombianos</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    # Mostrar ejemplo de campos
    with st.expander("Campos que se extraen", expanded=False):
        st.markdown("""
        <div style="color: var(--platzi-text-secondary);">
        <ol style="line-height: 2;">
            <li><strong>No. CONTRATO:</strong> Número de contrato del cliente</li>
            <li><strong>Dirección:</strong> Dirección completa del inmueble</li>
            <li><strong>Código de Referencia:</strong> Para pago electrónico/PSE</li>
            <li><strong>TOTAL A PAGAR:</strong> Monto final a pagar</li>
            <li><strong>Adicionales:</strong> Empresa, periodo, fecha de vencimiento</li>
        </ol>
        </div>
        """, unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("""
        <h2 style="color: var(--platzi-green); margin-bottom: 1.5rem;">Opciones de Configuración</h2>
        """, unsafe_allow_html=True)
        
        forzar_gemini = st.checkbox(
            "Forzar uso de Gemini",
            value=not TESSERACT_DISPONIBLE,
            disabled=not TESSERACT_DISPONIBLE,
            help="Usar solo Gemini sin intentar Tesseract"
        )
        
        umbral = st.slider(
            "Umbral de confianza",
            min_value=0.3,
            max_value=0.9,
            value=0.8,
            step=0.1,
            disabled=not TESSERACT_DISPONIBLE,
            help="Para facturas de servicios públicos, se recomienda 0.7-0.8 (usa más Gemini)"
        )
        
        st.divider()
        
        with st.expander("Instalación de dependencias", expanded=False):
            st.markdown("""
            <div style="color: var(--platzi-text-secondary);">
            <h4>Para Windows (desarrollo local):</h4>
            <ul>
                <li>Tesseract: <a href="https://github.com/UB-Mannheim/tesseract/wiki" target="_blank">Descargar</a></li>
                <li>Poppler: <a href="https://github.com/oschwartz10612/poppler-windows/releases" target="_blank">Descargar</a></li>
            </ul>
            
            <h4>Para Streamlit Cloud (deployment):</h4>
            <p>Crea <code>packages.txt</code>:</p>
            <pre style="background: var(--platzi-gray); padding: 1rem; border-radius: 4px;">
tesseract-ocr
tesseract-ocr-spa
poppler-utils
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
                <strong>Error: No se puede procesar PDF sin Poppler instalado</strong>
                <p style="margin-top: 0.5rem; color: var(--platzi-text-secondary);">
                    Instala Poppler siguiendo las instrucciones en el sidebar
                </p>
            </div>
            """, unsafe_allow_html=True)
            return
        
        if st.button("Procesar Facturas", type="primary", use_container_width=True):
            
            if not GEMINI_API_KEY:
                st.markdown("""
                <div class="status-card error">
                    <strong>Error: No se encontró la API key de Gemini</strong>
                    <p style="margin-top: 0.5rem; color: var(--platzi-text-secondary);">
                        Configúrala en el archivo .env de la aplicación
                    </p>
                </div>
                """, unsafe_allow_html=True)
                return
            
            pdf_bytes = uploaded_file.read()
            facturas, stats = procesar_pdf(pdf_bytes, umbral, forzar_gemini)
            
            if facturas:
                st.divider()
                st.balloons()
                
                st.markdown(f"""
                <div class="status-card success" style="text-align: center; padding: 2rem;">
                    <h2 style="color: var(--platzi-green); margin: 0;">Procesamiento Completado</h2>
                    <p style="font-size: 1.2rem; margin-top: 0.5rem; color: var(--platzi-text-secondary);">
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
                        <div class="metric-value">{stats['tesseract']}</div>
                        <div class="metric-label">Tesseract</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{stats['gemini']}</div>
                        <div class="metric-label">Gemini</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col4:
                    ahorro = (stats['tesseract'] / stats['total'] * 100) if stats['total'] > 0 else 0
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-value">{ahorro:.0f}%</div>
                        <div class="metric-label">Ahorro</div>
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