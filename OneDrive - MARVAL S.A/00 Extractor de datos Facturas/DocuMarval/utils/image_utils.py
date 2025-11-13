"""Utilidades para procesamiento de imágenes"""
import base64
import hashlib
from io import BytesIO
from PIL import Image, ImageEnhance
import html
import logging

logger = logging.getLogger(__name__)

def sanitize_html(text):
    """Sanitiza texto para uso seguro en HTML, previniendo XSS"""
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text)

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

def obtener_hash_imagen(imagen):
    """Obtiene hash MD5 de la imagen para usar como clave de caché (optimizado)"""
    # Usar una copia más pequeña para el hash (más rápido)
    img_small = imagen.copy()
    if max(img_small.size) > 512:
        img_small.thumbnail((512, 512), Image.Resampling.LANCZOS)
    
    img_buffer = BytesIO()
    img_small.save(img_buffer, format='JPEG', quality=75)
    return hashlib.md5(img_buffer.getvalue()).hexdigest()

def imagen_to_base64(imagen):
    """Convierte una imagen PIL a base64 para mostrar en HTML"""
    buffered = BytesIO()
    imagen.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

