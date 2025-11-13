"""Configuración centralizada de la aplicación"""
import os
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from dataclasses import dataclass
from typing import Optional
import logging
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

logger = logging.getLogger(__name__)

def get_secret(key, default=None):
    """Obtiene un secreto de forma segura, manejando cuando no existe secrets.toml"""
    try:
        if not hasattr(st, 'secrets'):
            logger.debug(f"st.secrets no disponible, usando default para {key}")
            return default
        value = st.secrets.get(key, default)
        if value and key.upper().endswith('_KEY'):
            logger.debug(f"Secret {key} configurado (longitud: {len(value)})")
        return value
    except (StreamlitSecretNotFoundError, AttributeError, KeyError, FileNotFoundError) as e:
        logger.debug(f"Error obteniendo secret {key}: {type(e).__name__}")
        return default
    except Exception as e:
        logger.error(f"Error inesperado obteniendo secret {key}: {type(e).__name__}")
        return default

@dataclass
class AppConfig:
    """Configuración de la aplicación"""
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-1.5-flash"
    max_pdf_size: int = 50 * 1024 * 1024  # 50 MB
    max_pages: int = 200
    rate_limit_calls: int = 40
    rate_limit_window: int = 60
    cache_ttl: int = 3600
    dpi: int = 200
    poppler_path: Optional[str] = None
    poppler_disponible: bool = False
    
    @classmethod
    def from_env(cls):
        """Crea configuración desde variables de entorno"""
        from utils.poppler_detector import detectar_poppler
        
        poppler_disponible, poppler_path = detectar_poppler()
        
        return cls(
            gemini_api_key=os.getenv('GEMINI_API_KEY') or get_secret("GEMINI_API_KEY"),
            gemini_model=os.getenv('GEMINI_MODEL') or get_secret("GEMINI_MODEL", "gemini-1.5-flash"),
            max_pdf_size=int(os.getenv('MAX_PDF_SIZE', 50 * 1024 * 1024)),
            max_pages=int(os.getenv('MAX_PAGES', 200)),
            rate_limit_calls=int(os.getenv('RATE_LIMIT_CALLS', 40)),
            rate_limit_window=int(os.getenv('RATE_LIMIT_WINDOW', 60)),
            cache_ttl=int(os.getenv('CACHE_TTL', 3600)),
            dpi=int(os.getenv('DPI', 200)),
            poppler_path=poppler_path,
            poppler_disponible=poppler_disponible,
        )

# Instancia global de configuración
config = AppConfig.from_env()

