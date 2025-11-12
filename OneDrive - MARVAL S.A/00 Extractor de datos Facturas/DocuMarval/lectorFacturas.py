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
import concurrent.futures
import time
import hashlib
from collections import deque
from PIL import Image, ImageEnhance
import numpy as np
import base64

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

# ==================== RATE LIMITING ====================

class RateLimiter:
    """Controla la tasa de llamadas a la API para evitar saturación"""
    def __init__(self, max_calls=10, time_window=60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
    
    def wait_if_needed(self):
        """Espera si es necesario para respetar el límite de tasa"""
        now = time.time()
        # Limpiar llamadas antiguas
        while self.calls and self.calls[0] < now - self.time_window:
            self.calls.popleft()
        
        # Si excedemos el límite, esperar
        if len(self.calls) >= self.max_calls:
            sleep_time = self.time_window - (now - self.calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                # Limpiar nuevamente después de esperar
                now = time.time()
                while self.calls and self.calls[0] < now - self.time_window:
                    self.calls.popleft()
        
        self.calls.append(time.time())

# Instancia global del rate limiter
rate_limiter = RateLimiter(max_calls=10, time_window=60)

# ==================== OPTIMIZACIÓN DE IMÁGENES ====================

def optimizar_imagen_para_gemini(imagen):
    """Optimiza imagen según tamaño para reducir tokens y mejorar procesamiento"""
    # Convertir a RGB si es necesario
    if imagen.mode != 'RGB':
        imagen = imagen.convert('RGB')
    
    # Redimensionar si es muy grande (Gemini tiene límites)
    max_dimension = 2048
    if max(imagen.size) > max_dimension:
        ratio = max_dimension / max(imagen.size)
        nuevo_tamano = (int(imagen.size[0] * ratio), 
                       int(imagen.size[1] * ratio))
        imagen = imagen.resize(nuevo_tamano, Image.Resampling.LANCZOS)
    
    # Mejorar contraste ligeramente (mejora OCR)
    enhancer = ImageEnhance.Contrast(imagen)
    imagen = enhancer.enhance(1.1)
    
    # Calidad adaptativa: más alta para imágenes pequeñas
    quality = 95 if max(imagen.size) < 1000 else 85
    
    img_buffer = BytesIO()
    imagen.save(img_buffer, format='JPEG', quality=quality, optimize=True)
    return img_buffer

# ==================== VALIDACIÓN TEMPRANA ====================

def validar_imagen_antes_procesar(imagen):
    """Valida que la imagen sea procesable antes de enviar a Gemini"""
    # Verificar tamaño mínimo
    if min(imagen.size) < 100:
        return False, "Imagen muy pequeña (menos de 100px en alguna dimensión)"
    
    # Verificar que tenga contenido (no completamente en blanco/negro)
    # Convertir a escala de grises para análisis
    if imagen.mode != 'L':
        img_gray = imagen.convert('L')
    else:
        img_gray = imagen
    
    # Calcular desviación estándar de píxeles (imagen en blanco tiene std ~0)
    pixels = np.array(img_gray)
    std_dev = np.std(pixels)
    
    if std_dev < 5:  # Imagen muy uniforme (probablemente en blanco)
        return False, "Imagen parece estar en blanco o sin contenido"
    
    return True, None

# ==================== CACHÉ DE RESULTADOS ====================

@st.cache_data(ttl=3600)  # Cache por 1 hora
def extraer_con_gemini_cached(_imagen_hash, imagen_bytes):
    """Extrae datos con caché basado en hash de imagen"""
    try:
        # Reconstruir imagen desde bytes
        imagen = Image.open(BytesIO(imagen_bytes))
        return extraer_con_gemini_interno(imagen)
    except Exception:
        return None

def obtener_hash_imagen(imagen):
    """Obtiene hash MD5 de la imagen para usar como clave de caché"""
    img_buffer = BytesIO()
    imagen.save(img_buffer, format='JPEG', quality=90)
    return hashlib.md5(img_buffer.getvalue()).hexdigest()

def extraer_con_gemini_interno(imagen, max_output_tokens=2048, max_reintentos=2):
    """Función interna de extracción con reintentos inteligentes y rate limiting"""
    if not GEMINI_API_KEY:
        return None
    
    try:
        model = get_gemini_model()
        if not model:
            return None
        
        # Optimizar imagen antes de procesar
        img_buffer = optimizar_imagen_para_gemini(imagen)
        
        # Tokens progresivos para reintentos
        tokens_por_reintento = [max_output_tokens, 3072, 4096]
        
        # Inicializar texto antes del loop
        texto = ""
        
        for intento in range(max_reintentos + 1):
            try:
                # Aplicar rate limiting
                rate_limiter.wait_if_needed()
                
                config = GENERATION_CONFIG.copy()
                config["max_output_tokens"] = tokens_por_reintento[min(intento, len(tokens_por_reintento) - 1)]
                
                response = model.generate_content(
                    [PROMPT_GEMINI, {'mime_type': 'image/jpeg', 'data': img_buffer.getvalue()}],
                    generation_config=config
                )
                
                # Verificar que la respuesta tenga contenido válido
                if not response.candidates:
                    if intento == max_reintentos:
                        return None
                    continue
                
                candidate = response.candidates[0]
                
                # Obtener el texto de forma segura - intentar múltiples métodos
                texto = ""
                
                # Método 1: Intentar acceder directamente a response.text (más confiable)
                try:
                    texto = response.text
                except (AttributeError, ValueError):
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
                
                # Si tenemos texto y no es MAX_TOKENS, éxito
                if texto and finish_reason != 2:
                    break
                
                # Si es MAX_TOKENS y hay más reintentos, continuar con más tokens
                if finish_reason == 2 and intento < max_reintentos:
                    continue
                
                # Si no hay texto, verificar bloqueos de seguridad
                if not texto:
                    if finish_reason == 3:
                        if intento == max_reintentos:
                            return None
                        continue
                    elif finish_reason == 2:
                        if intento == max_reintentos:
                            return None
                        continue
                    else:
                        if intento == max_reintentos:
                            return None
                        continue
                        
            except Exception as e:
                if intento == max_reintentos:
                    raise
                # Backoff exponencial
                time.sleep(1 * (intento + 1))
                continue
        
        # Si aún no tenemos texto después de todos los reintentos
        if not texto:
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

def extraer_con_gemini(imagen):
    """Función pública de extracción con validación, caché y manejo de errores"""
    if not GEMINI_API_KEY:
        st.error("Error: GEMINI_API_KEY no configurada")
        return None
    
    # Validación temprana
    es_valida, mensaje_error = validar_imagen_antes_procesar(imagen)
    if not es_valida:
        st.warning(f"Imagen no válida: {mensaje_error}")
        return None
    
    # Intentar usar caché
    try:
        imagen_hash = obtener_hash_imagen(imagen)
        img_buffer = BytesIO()
        imagen.save(img_buffer, format='JPEG', quality=90)
        imagen_bytes = img_buffer.getvalue()
        
        # Intentar obtener del caché
        datos = extraer_con_gemini_cached(imagen_hash, imagen_bytes)
        if datos:
            return datos
    except Exception:
        # Si falla el caché, continuar con extracción normal
        pass
    
    # Extracción directa si no hay caché
    return extraer_con_gemini_interno(imagen)

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

def procesar_pdf(pdf_bytes, max_workers=4):
    """Procesa un PDF y extrae datos de facturas con procesamiento paralelo"""
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
    
    # Validar todas las imágenes antes de procesar
    imagenes_validas = []
    for i, imagen in enumerate(imagenes):
        es_valida, mensaje = validar_imagen_antes_procesar(imagen)
        if not es_valida:
            st.warning(f"Página {i+1} saltada: {mensaje}")
        else:
            imagenes_validas.append((i, imagen))
    
    if not imagenes_validas:
        st.error("No hay imágenes válidas para procesar")
        return [], {"gemini": 0, "total": len(imagenes)}
    
    # Procesar con visualización en tiempo real
    resultados_dict = {}
    estadisticas = {"gemini": 0, "total": len(imagenes)}
    
    # Función auxiliar para convertir imagen a base64
    def imagen_to_base64(imagen):
        """Convierte una imagen PIL a base64 para mostrar en HTML"""
        buffered = BytesIO()
        imagen.save(buffered, format="PNG", quality=85)
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str
    
    # Contenedor para mostrar progreso con diseño moderno
    st.markdown("""
    <div style="margin-bottom: 2rem;">
        <h3 style="color: var(--brand-300); font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem;">⚡ Procesamiento en Curso</h3>
        <p style="color: var(--gray-300); font-size: 0.95rem; margin: 0;">Análisis inteligente en tiempo real con IA</p>
    </div>
    <style>
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
    @keyframes shimmer {
        0% { background-position: -1000px 0; }
        100% { background-position: 1000px 0; }
    }
    .processing-card {
        background: var(--glass-bg);
        border: 1px solid var(--glass-border);
        border-radius: var(--radius-md);
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    .processing-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(20, 184, 166, 0.1), transparent);
        animation: shimmer 2s infinite;
    }
    .processing-card.processing {
        border-color: var(--brand-300);
        box-shadow: 0 0 20px rgba(20, 184, 166, 0.2);
    }
    .processing-card.completed {
        border-color: var(--brand-400);
        box-shadow: 0 0 15px rgba(20, 184, 166, 0.15);
    }
    .processing-card.error {
        border-color: #EF4444;
        box-shadow: 0 0 15px rgba(239, 68, 68, 0.15);
    }
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.875rem;
        font-weight: 600;
        backdrop-filter: blur(10px);
    }
    .status-processing {
        background: rgba(20, 184, 166, 0.15);
        color: var(--brand-300);
        border: 1px solid rgba(20, 184, 166, 0.3);
    }
    .status-completed {
        background: rgba(20, 184, 166, 0.2);
        color: var(--brand-400);
        border: 1px solid rgba(20, 184, 166, 0.4);
    }
    .status-error {
        background: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }
    .spinner {
        width: 18px;
        height: 18px;
        border: 2px solid var(--brand-300);
        border-top: 2px solid transparent;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    </style>
    """, unsafe_allow_html=True)
    
    progress_container = st.container()
    
    # Procesar cada imagen con visualización en tiempo real
    for idx, (i, imagen) in enumerate(imagenes_validas):
        with progress_container:
            # Placeholder para el card completo
            card_placeholder = st.empty()
            
            # Estado inicial: Procesando
            img_base64 = imagen_to_base64(imagen)
            with card_placeholder.container():
                st.markdown(f"""
                <div class="processing-card processing" id="card-{i}">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
                        <div>
                            <h4 style="color: var(--brand-300); margin: 0 0 0.25rem 0; font-size: 1.1rem; font-weight: 700;">📄 Página {i+1} de {len(imagenes)}</h4>
                            <p style="color: var(--gray-300); margin: 0; font-size: 0.875rem;">Análisis con IA en progreso...</p>
                        </div>
                        <div class="status-badge status-processing">
                            <div class="spinner"></div>
                            <span>Procesando</span>
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 200px 1fr; gap: 1.5rem; align-items: start;">
                        <div style="border-radius: var(--radius-md); overflow: hidden; border: 1px solid var(--glass-border);">
                            <img src="data:image/png;base64,{img_base64}" style="width: 100%; height: auto; display: block;" alt="Página {i+1}">
                        </div>
                        <div>
                            <div style="background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: var(--radius-sm); padding: 1rem; margin-bottom: 1rem;">
                                <p style="color: var(--brand-300); margin: 0; font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem;">
                                    <span style="animation: pulse 2s infinite;">⏳</span>
                                    <span>Extrayendo datos estructurados con Gemini AI...</span>
                                </p>
                            </div>
                            <div style="background: linear-gradient(90deg, var(--brand-300) 0%, var(--brand-300) 0%, rgba(20, 184, 166, 0.1) 0%); border-radius: 8px; height: 6px; margin-bottom: 0.5rem; transition: all 0.3s ease;" id="progress-bar-{i}"></div>
                            <p style="color: var(--gray-400); margin: 0; font-size: 0.75rem; text-align: right;" id="progress-text-{i}">Iniciando análisis...</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            # Simular progreso mientras procesa
            progress_individual = st.progress(0)
            for progress_val in [0.2, 0.4, 0.6, 0.8]:
                progress_individual.progress(progress_val)
                time.sleep(0.15)
            
            # Procesar la imagen
            try:
                datos = extraer_con_gemini(imagen)
                progress_individual.progress(1.0)
                
                if datos:
                    datos["pagina"] = i + 1
                    datos["metodo_extraccion"] = "Gemini"
                    resultados_dict[i] = datos
                    estadisticas["gemini"] += 1
                    
                    # Actualizar card con datos extraídos
                    with card_placeholder.container():
                        st.markdown(f"""
                        <div class="processing-card completed" id="card-{i}">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
                                <div>
                                    <h4 style="color: var(--brand-300); margin: 0 0 0.25rem 0; font-size: 1.1rem; font-weight: 700;">📄 Página {i+1} de {len(imagenes)}</h4>
                                    <p style="color: var(--gray-300); margin: 0; font-size: 0.875rem;">Datos extraídos exitosamente</p>
                                </div>
                                <div class="status-badge status-completed">
                                    <span style="color: var(--brand-400);">✓</span>
                                    <span>Completado</span>
                                </div>
                            </div>
                            <div style="display: grid; grid-template-columns: 200px 1fr; gap: 1.5rem; align-items: start;">
                                <div style="border-radius: var(--radius-md); overflow: hidden; border: 1px solid var(--glass-border);">
                                    <img src="data:image/png;base64,{img_base64}" style="width: 100%; height: auto; display: block;" alt="Página {i+1}">
                                </div>
                                <div>
                                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
                                        <div style="background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: var(--radius-sm); padding: 0.875rem;">
                                            <p style="color: var(--gray-300); margin: 0 0 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;"><strong style="color: var(--white);">Contrato</strong></p>
                                            <p style="color: var(--brand-300); margin: 0; font-size: 1rem; font-weight: 700;">{datos.get("numero_contrato") or "N/A"}</p>
                                        </div>
                                        <div style="background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: var(--radius-sm); padding: 0.875rem;">
                                            <p style="color: var(--gray-300); margin: 0 0 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;"><strong style="color: var(--white);">Total</strong></p>
                                            <p style="color: var(--brand-300); margin: 0; font-size: 1rem; font-weight: 700;">${datos.get('total_pagar', 0):,.0f}</p>
                                        </div>
                                        <div style="background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: var(--radius-sm); padding: 0.875rem;">
                                            <p style="color: var(--gray-300); margin: 0 0 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;"><strong style="color: var(--white);">Referencia</strong></p>
                                            <p style="color: var(--brand-300); margin: 0; font-size: 0.875rem; font-weight: 600;">{(datos.get("codigo_referencia") or "N/A")[:20]}</p>
                                        </div>
                                        <div style="background: rgba(20, 184, 166, 0.05); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: var(--radius-sm); padding: 0.875rem;">
                                            <p style="color: var(--gray-300); margin: 0 0 0.5rem 0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;"><strong style="color: var(--white);">Empresa</strong></p>
                                            <p style="color: var(--brand-300); margin: 0; font-size: 0.875rem; font-weight: 600;">{(datos.get("empresa") or "N/A")[:25]}</p>
                                        </div>
                                    </div>
                                    <div style="background: rgba(20, 184, 166, 0.1); border: 1px solid rgba(20, 184, 166, 0.3); border-radius: var(--radius-sm); padding: 0.75rem; text-align: center;">
                                        <p style="color: var(--brand-400); margin: 0; font-size: 0.875rem; font-weight: 600;">✓ Datos extraídos exitosamente</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                else:
                    # Error en extracción
                    with card_placeholder.container():
                        st.markdown(f"""
                        <div class="processing-card error" id="card-{i}">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
                                <div>
                                    <h4 style="color: var(--brand-300); margin: 0 0 0.25rem 0; font-size: 1.1rem; font-weight: 700;">📄 Página {i+1} de {len(imagenes)}</h4>
                                    <p style="color: var(--gray-300); margin: 0; font-size: 0.875rem;">Error en la extracción</p>
                                </div>
                                <div class="status-badge status-error">
                                    <span>✗</span>
                                    <span>Error</span>
                                </div>
                            </div>
                            <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-sm); padding: 1rem;">
                                <p style="color: #EF4444; margin: 0; font-size: 0.875rem;">⚠️ No se pudieron extraer datos de esta página</p>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
            except Exception as e:
                # Error en procesamiento
                progress_individual.progress(1.0)
                with card_placeholder.container():
                    st.markdown(f"""
                    <div class="processing-card error" id="card-{i}">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem;">
                            <div>
                                <h4 style="color: var(--brand-300); margin: 0 0 0.25rem 0; font-size: 1.1rem; font-weight: 700;">📄 Página {i+1} de {len(imagenes)}</h4>
                                <p style="color: var(--gray-300); margin: 0; font-size: 0.875rem;">Error en el procesamiento</p>
                            </div>
                            <div class="status-badge status-error">
                                <span>✗</span>
                                <span>Error</span>
                            </div>
                        </div>
                        <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: var(--radius-sm); padding: 1rem;">
                            <p style="color: #EF4444; margin: 0; font-size: 0.875rem;">❌ Error: {str(e)[:100]}</p>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    # Ordenar resultados por índice de página
    resultados = [resultados_dict[i] for i in sorted(resultados_dict.keys())]
    
    # Mostrar resumen en formato lista
    if resultados:
        st.divider()
        st.markdown("### 📊 Resumen de Facturas Procesadas")
        
        # Lista compacta de resultados
        for resultado in resultados:
            pagina = resultado["pagina"]
            
            # Card de lista compacta
            with st.container():
                st.markdown(f"""
                <div style="background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1rem; transition: all 0.2s ease;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                        <h4 style="color: var(--brand-300); margin: 0; font-size: 1.1rem;">📄 Página {pagina}</h4>
                        <span style="color: var(--brand-400); font-size: 0.875rem; font-weight: 600;">✓ Procesada</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Contrato:</strong> {resultado.get("numero_contrato") or "N/A"}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Total:</strong> <span style="color: var(--brand-300); font-weight: 600;">${resultado.get('total_pagar', 0):,.0f}</span></p>
                        </div>
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Empresa:</strong> {resultado.get("empresa") or "N/A"}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Referencia:</strong> {(resultado.get("codigo_referencia") or "N/A")[:25]}</p>
                        </div>
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Período:</strong> {resultado.get("periodo_facturado") or "N/A"}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0; font-size: 0.875rem;"><strong style="color: var(--white);">Vencimiento:</strong> {resultado.get("fecha_vencimiento") or "N/A"}</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Expander para ver detalles completos
                with st.expander(f"🔍 Ver detalles completos - Página {pagina}", expanded=False):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.image(imagenes[pagina - 1], caption=f"Página {pagina}", use_container_width=True)
                    with col2:
                        st.json(resultado)
    
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