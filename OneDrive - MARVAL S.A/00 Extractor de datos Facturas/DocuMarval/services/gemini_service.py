"""Servicio de extracción con Gemini AI"""
import streamlit as st
import google.generativeai as genai
import json
import re
import time
import logging
from io import BytesIO
from PIL import Image

from config.settings import config
from utils.rate_limiter import RateLimiter
from utils.image_utils import optimizar_imagen_para_gemini
from utils.validators import validar_imagen_antes_procesar

logger = logging.getLogger(__name__)

# Prompt para Gemini
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
    "max_output_tokens": 2048,
}

# Configurar Gemini
if config.gemini_api_key:
    genai.configure(api_key=config.gemini_api_key)

# Rate limiter global
rate_limiter = RateLimiter(
    max_calls=config.rate_limit_calls,
    time_window=config.rate_limit_window
)

@st.cache_resource
def get_gemini_model():
    """Obtiene el modelo de Gemini (cacheado) con manejo de errores mejorado"""
    if not config.gemini_api_key:
        logger.warning("GEMINI_API_KEY no configurada")
        st.error("GEMINI_API_KEY no está configurada. Por favor configura tu API key en el archivo .env")
        return None
    
    modelos_a_probar = [
        config.gemini_model,
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro",
    ]
    
    for modelo_nombre in modelos_a_probar:
        try:
            modelo = genai.GenerativeModel(modelo_nombre)
            if modelo_nombre != config.gemini_model:
                logger.info(f"Usando modelo fallback: {modelo_nombre} (configurado: {config.gemini_model})")
                st.info(f"Usando modelo: {modelo_nombre} (el modelo configurado {config.gemini_model} no está disponible)")
            else:
                logger.info(f"Modelo {config.gemini_model} cargado exitosamente")
            return modelo
        except Exception as e:
            error_msg = str(e).lower()
            error_type = type(e).__name__
            if "not found" in error_msg or "404" in error_msg or "model" in error_msg:
                logger.debug(f"Modelo {modelo_nombre} no disponible: {error_type}")
                continue
            else:
                logger.error(f"Error al cargar modelo {modelo_nombre}: {error_type}")
                st.error(f"Error al cargar modelo {modelo_nombre}: {error_type}")
                if "api" in error_msg or "key" in error_msg or "401" in error_msg or "403" in error_msg:
                    logger.error("Error de autenticación con API key")
                    return None
    
    logger.error("No se pudo cargar ningún modelo de Gemini")
    st.error("No se pudo cargar ningún modelo de Gemini. Verifica tu API key y la disponibilidad de los modelos.")
    return None

def extraer_con_gemini_interno(imagen, max_output_tokens=2048, max_reintentos=2):
    """Función interna de extracción con reintentos inteligentes y rate limiting"""
    if not config.gemini_api_key:
        return None
    
    try:
        model = get_gemini_model()
        if not model:
            return None
        
        img_buffer = optimizar_imagen_para_gemini(imagen)
        tokens_por_reintento = [max_output_tokens, 3072, 4096]
        texto = ""
        
        for intento in range(max_reintentos + 1):
            try:
                rate_limiter.wait_if_needed()
                
                gen_config = GENERATION_CONFIG.copy()
                gen_config["max_output_tokens"] = tokens_por_reintento[min(intento, len(tokens_por_reintento) - 1)]
                
                response = model.generate_content(
                    [PROMPT_GEMINI, {'mime_type': 'image/jpeg', 'data': img_buffer.getvalue()}],
                    generation_config=gen_config
                )
                
                if not response.candidates:
                    if intento == max_reintentos:
                        return None
                    continue
                
                candidate = response.candidates[0]
                
                try:
                    texto = response.text
                except (AttributeError, ValueError):
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    texto += part.text
                        elif hasattr(candidate.content, 'text'):
                            texto = candidate.content.text
                
                finish_reason = getattr(candidate, 'finish_reason', None)
                
                if texto and finish_reason != 2:
                    break
                
                if finish_reason == 2 and intento < max_reintentos:
                    continue
                
                if not texto:
                    if finish_reason in [2, 3]:
                        if intento == max_reintentos:
                            return None
                        continue
                    else:
                        if intento == max_reintentos:
                            return None
                        continue
                        
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e).lower()
                logger.error(f"Error en intento {intento + 1}/{max_reintentos + 1}: {error_type}: {error_msg[:200]}")
                
                if "rate limit" in error_msg or "429" in error_msg:
                    if intento == max_reintentos:
                        logger.warning("Límite de tasa excedido después de todos los reintentos")
                        st.warning("Límite de tasa excedido. Intenta más tarde.")
                        return None
                    sleep_time = 2 * (intento + 1)
                    logger.info(f"Rate limit detectado, esperando {sleep_time}s")
                    time.sleep(sleep_time)
                elif intento == max_reintentos:
                    logger.error(f"Error final después de {max_reintentos + 1} intentos: {error_type}")
                    st.error(f"Error al procesar: {error_type}")
                    return None
                else:
                    sleep_time = 1 * (intento + 1)
                    logger.debug(f"Reintentando en {sleep_time}s (intento {intento + 1}/{max_reintentos + 1})")
                    time.sleep(sleep_time)
                continue
        
        if not texto:
            return None

        texto = texto.strip()
        texto = re.sub(r'```json\s*|```\s*', '', texto).strip()
        
        json_match = re.search(r'\{.*\}', texto, re.DOTALL)
        if json_match:
            texto = json_match.group(0)
        
        datos = json.loads(texto)
        
        if not isinstance(datos, dict):
            raise ValueError("Respuesta no es un diccionario válido")
        
        # Validar y limpiar datos extraídos
        palabras_prohibidas = ['adultos', 'mayores', 'millones', 'dólares', 'familia', 'demográfico', 'grupo', 'estadística']
        
        for campo in ['numero_contrato', 'direccion', 'codigo_referencia', 'empresa', 'periodo_facturado', 'fecha_vencimiento', 'numero_factura', 'nit_empresa', 'medidor']:
            if campo in datos and isinstance(datos[campo], str):
                texto_campo = datos[campo].lower()
                if any(palabra in texto_campo for palabra in palabras_prohibidas):
                    datos[campo] = ""
                datos[campo] = datos[campo].strip()
                if len(datos[campo]) > 200:
                    datos[campo] = datos[campo][:200].strip()
        
        if "codigo_referencia" in datos and datos["codigo_referencia"]:
            ref = datos["codigo_referencia"].strip()
            if re.match(r'^\d{10}$', ref.replace(' ', '').replace('-', '')):
                datos["codigo_referencia"] = ""
        
        if "total_pagar" in datos:
            try:
                if isinstance(datos["total_pagar"], str):
                    texto_limpio = re.sub(r'[^\d.]', '', datos["total_pagar"])
                    if any(palabra in datos["total_pagar"].lower() for palabra in palabras_prohibidas):
                        datos["total_pagar"] = 0.0
                    else:
                        datos["total_pagar"] = float(texto_limpio or 0)
                else:
                    datos["total_pagar"] = float(datos["total_pagar"])
            except:
                datos["total_pagar"] = 0.0
        
        if "consumo" in datos:
            try:
                consumo_val = float(datos["consumo"])
                if consumo_val > 1000000:
                    datos["consumo"] = 0.0
                else:
                    datos["consumo"] = consumo_val
            except:
                datos["consumo"] = 0.0
        
        return datos
        
    except json.JSONDecodeError as e:
        logger.error(f"Error al parsear JSON: {str(e)}")
        if 'texto' in locals() and texto:
            logger.debug(f"Texto recibido (primeros 500 chars): {texto[:500]}")
            st.error(f"Error al parsear respuesta JSON: {str(e)[:100]}")
            st.info(f"Respuesta recibida: {texto[:500]}...")
        else:
            st.error("Error al parsear respuesta JSON: No se recibió texto válido")
        return None
    except ValueError as e:
        logger.error(f"Error de validación: {str(e)}")
        st.error(f"Error de validación: {str(e)[:100]}")
        return None
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Error inesperado con Gemini: {error_type}: {error_msg[:200]}")
        st.error(f"Error con Gemini: {error_type}")
        return None

def extraer_con_gemini(imagen):
    """Función pública de extracción con validación y manejo de errores"""
    if not config.gemini_api_key:
        st.error("Error: GEMINI_API_KEY no configurada")
        return None
    
    es_valida, mensaje_error = validar_imagen_antes_procesar(imagen)
    if not es_valida:
        st.warning(f"Imagen no válida: {mensaje_error}")
        return None
    
    return extraer_con_gemini_interno(imagen)

