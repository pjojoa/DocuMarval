"""Validadores para la aplicación"""
import logging
from PIL import Image
import numpy as np
from PyPDF2 import PdfReader
from io import BytesIO

logger = logging.getLogger(__name__)

def validar_imagen_antes_procesar(imagen):
    """Valida que la imagen sea procesable antes de enviar a Gemini"""
    # Verificar tamaño mínimo
    if min(imagen.size) < 100:
        return False, "Imagen muy pequeña (menos de 100px en alguna dimensión)"
    
    # Verificar que tenga contenido (no completamente en blanco/negro)
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

def validar_pdf(pdf_bytes, max_size, max_pages):
    """Valida un PDF antes de procesarlo"""
    # Validar tamaño
    if len(pdf_bytes) > max_size:
        size_mb = len(pdf_bytes) / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        return False, f"El archivo es demasiado grande ({size_mb:.1f} MB). Máximo: {max_mb} MB"
    
    # Validar magic bytes
    if not pdf_bytes.startswith(b'%PDF'):
        return False, "El archivo no es un PDF válido"
    
    # Validar número de páginas
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        if num_pages > max_pages:
            return False, f"El PDF tiene demasiadas páginas ({num_pages}). Máximo: {max_pages}"
        logger.info(f"PDF validado: {num_pages} páginas, {len(pdf_bytes) / 1024:.1f} KB")
        return True, num_pages
    except Exception as e:
        logger.warning(f"No se pudo validar número de páginas: {type(e).__name__}")
        return True, None  # Continuar si no se puede validar

