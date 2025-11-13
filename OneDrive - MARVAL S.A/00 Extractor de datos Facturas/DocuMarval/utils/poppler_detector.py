"""Detección automática de Poppler"""
import os
import platform
import subprocess
import logging

logger = logging.getLogger(__name__)

def detectar_poppler():
    """Detecta si Poppler está disponible y retorna su ruta"""
    # Obtener POPPLER_PATH desde variables de entorno directamente
    poppler_path = os.getenv('POPPLER_PATH')
    
    # Intentar obtener desde secrets si está disponible (evitar importación circular)
    if not poppler_path:
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                poppler_path = st.secrets.get("POPPLER_PATH", None)
        except:
            pass
    
    if poppler_path and os.path.exists(poppler_path):
        logger.info(f"Poppler encontrado en: {poppler_path}")
        return True, poppler_path
    
    # Detección para Windows
    if platform.system() == 'Windows':
        rutas_comunes = [
            r'C:\Program Files\poppler-25.07.0\Library\bin',
            r'C:\Program Files\poppler-24.08.0\Library\bin',
            r'C:\Program Files\poppler-23.11.0\Library\bin',
            r'C:\Program Files\poppler\Library\bin',
            r'C:\poppler\Library\bin',
            r'C:\Program Files (x86)\poppler\Library\bin',
        ]
        for ruta in rutas_comunes:
            if os.path.exists(ruta) and os.path.exists(os.path.join(ruta, 'pdftoppm.exe')):
                logger.info(f"Poppler encontrado en: {ruta}")
                return True, ruta
    
    # Detección para Linux (incluye Streamlit Cloud)
    if platform.system() == 'Linux' or os.path.exists('/usr/bin'):
        rutas_linux = ['/usr/bin', '/usr/local/bin', '/bin']
        for ruta in rutas_linux:
            pdftoppm_path = os.path.join(ruta, 'pdftoppm')
            if os.path.exists(pdftoppm_path):
                logger.info(f"Poppler encontrado en: {ruta}")
                return True, ruta
    
    # Intentar ejecutar pdftoppm directamente (útil en Streamlit Cloud)
    try:
        result = subprocess.run(['pdftoppm', '-v'], capture_output=True, timeout=2, check=False)
        if result.returncode == 0 or result.returncode == 1:  # -v puede retornar código 1 pero significa que existe
            logger.info("Poppler disponible en PATH")
            return True, None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"Error al verificar pdftoppm en PATH: {e}")
    
    logger.warning("Poppler no encontrado")
    return False, None

