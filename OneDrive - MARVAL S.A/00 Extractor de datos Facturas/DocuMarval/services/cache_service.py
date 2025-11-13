"""Servicio de caché optimizado para imágenes"""
import streamlit as st
import hashlib
import logging
from io import BytesIO
from PIL import Image

from services.gemini_service import extraer_con_gemini
from utils.image_utils import obtener_hash_imagen

logger = logging.getLogger(__name__)

@st.cache_data(ttl=86400, max_entries=500)  # Cache por 24 horas, máximo 500 entradas
def extraer_con_gemini_cached(_imagen_hash, imagen_bytes):
    """Extrae datos con caché basado en hash de imagen - Optimizado"""
    try:
        imagen = Image.open(BytesIO(imagen_bytes))
        from services.gemini_service import extraer_con_gemini_interno
        return extraer_con_gemini_interno(imagen)
    except Exception as e:
        logger.error(f"Error en caché: {type(e).__name__}")
        return None

@st.cache_data(ttl=86400, max_entries=500)
def optimizar_imagen_cached(_imagen_hash, imagen_bytes):
    """Cachea la optimización de imagen"""
    from utils.image_utils import optimizar_imagen_para_gemini
    imagen = Image.open(BytesIO(imagen_bytes))
    return optimizar_imagen_para_gemini(imagen).getvalue()

def extraer_con_gemini_cached_wrapper(imagen):
    """Wrapper que usa caché optimizado"""
    from services.gemini_service import extraer_con_gemini
    
    try:
        # Calcular hash y bytes en una sola pasada
        img_buffer = BytesIO()
        imagen.save(img_buffer, format='JPEG', quality=90)
        imagen_bytes = img_buffer.getvalue()
        imagen_hash = hashlib.md5(imagen_bytes).hexdigest()
        
        # Intentar obtener del caché
        datos = extraer_con_gemini_cached(imagen_hash, imagen_bytes)
        if datos:
            logger.debug("Datos obtenidos del caché")
            return datos
        
        # Si no hay caché, usar extracción directa
        return extraer_con_gemini(imagen)
    except Exception as e:
        logger.warning(f"Error en caché, usando extracción directa: {type(e).__name__}")
        return extraer_con_gemini(imagen)

