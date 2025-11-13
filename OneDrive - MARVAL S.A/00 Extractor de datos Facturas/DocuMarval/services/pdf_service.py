"""Servicio de procesamiento de PDFs con procesamiento paralelo"""
import streamlit as st
from pdf2image import convert_from_bytes
import platform
import gc
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from config.settings import config
from services.gemini_service import extraer_con_gemini
from services.cache_service import extraer_con_gemini_cached_wrapper
from utils.validators import validar_imagen_antes_procesar
from utils.image_utils import imagen_to_base64

logger = logging.getLogger(__name__)

def procesar_pdf(pdf_bytes):
    """Procesa un PDF y extrae datos de facturas con procesamiento paralelo"""
    try:
        with st.spinner("Convirtiendo PDF a imágenes..."):
            kwargs = {'dpi': config.dpi}
            if config.poppler_path and platform.system() == 'Windows':
                kwargs['poppler_path'] = config.poppler_path
            
            imagenes = convert_from_bytes(pdf_bytes, **kwargs)
            st.success(f"{len(imagenes)} página(s) convertida(s)")
        
        del pdf_bytes
        gc.collect()
        
    except Exception as e:
        logger.error(f"Error al convertir PDF: {type(e).__name__}: {str(e)[:200]}")
        st.error(f"Error al convertir PDF: {str(e)}")
        if not config.poppler_disponible:
            st.warning("Poppler no está instalado.")
        return [], {}
    
    # Validar imágenes
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
    
    # Procesar con ThreadPoolExecutor para paralelismo
    resultados_dict = {}
    estadisticas = {"gemini": 0, "total": len(imagenes)}
    lock = threading.Lock()
    
    def procesar_imagen(args):
        """Procesa una imagen y retorna resultado"""
        idx, i, imagen = args
        try:
            datos = extraer_con_gemini_cached_wrapper(imagen)
            if datos:
                datos["pagina"] = i + 1
                datos["metodo_extraccion"] = "Gemini"
                with lock:
                    resultados_dict[i] = datos
                    estadisticas["gemini"] += 1
                return idx, i, datos, None
            return idx, i, None, "No se extrajeron datos"
        except Exception as e:
            logger.error(f"Error procesando página {i+1}: {type(e).__name__}: {str(e)[:200]}")
            return idx, i, None, str(e)
    
    # UI de procesamiento con CSS
    st.markdown("""
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
    </style>
    <div style="margin-bottom: 2rem;">
        <h3 style="color: var(--brand-300); font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem;">⚡ Procesamiento Paralelo en Curso</h3>
        <p style="color: var(--gray-300); font-size: 0.95rem; margin: 0;">Análisis inteligente en tiempo real con IA (procesamiento paralelo)</p>
    </div>
    """, unsafe_allow_html=True)
    
    progress_container = st.container()
    placeholders_ui = {}
    
    # Preparar placeholders antes de procesar
    with progress_container:
        for idx, (i, _) in enumerate(imagenes_validas):
            placeholders_ui[i] = st.empty()
    
    # Procesar en paralelo
    max_workers = min(4, len(imagenes_validas))  # Máximo 4 workers
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(procesar_imagen, (idx, i, img)): (idx, i) 
            for idx, (i, img) in enumerate(imagenes_validas)
        }
        
        # Actualizar UI conforme se completan
        for future in as_completed(futures):
            idx, i = futures[future]
            placeholder = placeholders_ui[i]
            
            try:
                _, page_idx, datos, error = future.result()
                
                from utils.image_utils import imagen_to_base64
                img_base64 = imagen_to_base64(imagenes[page_idx])
                
                if datos:
                    # Mostrar resultado exitoso
                    with placeholder.container():
                        from utils.image_utils import sanitize_html
                        st.markdown(f"""
                        <div class="processing-card completed">
                            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                                <h4 style="color: var(--brand-300); margin: 0;">📄 Página {page_idx+1}</h4>
                                <span style="color: var(--brand-400);">✓ Completado</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 200px 1fr; gap: 1rem;">
                                <img src="data:image/png;base64,{img_base64}" style="width: 100%; border-radius: 8px;">
                                <div>
                                    <p><strong>Contrato:</strong> {sanitize_html(datos.get("numero_contrato") or "N/A")}</p>
                                    <p><strong>Total:</strong> ${datos.get('total_pagar', 0):,.0f}</p>
                                    <p><strong>Empresa:</strong> {sanitize_html(datos.get("empresa") or "N/A")}</p>
                                </div>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Mostrar error
                    with placeholder.container():
                        st.markdown(f"""
                        <div class="processing-card error">
                            <h4 style="color: var(--brand-300);">📄 Página {page_idx+1}</h4>
                            <p style="color: #EF4444;">⚠️ {error or 'No se pudieron extraer datos'}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
            except Exception as e:
                logger.error(f"Error en future para página {i+1}: {type(e).__name__}")
                with placeholder.container():
                    st.markdown(f"""
                    <div class="processing-card error">
                        <h4 style="color: var(--brand-300);">📄 Página {i+1}</h4>
                        <p style="color: #EF4444;">❌ Error: {str(e)[:100]}</p>
                    </div>
                    """, unsafe_allow_html=True)
    
    # Ordenar resultados
    resultados = [resultados_dict[i] for i in sorted(resultados_dict.keys())]
    
    # Guardar imágenes para el resumen
    imagenes_dict = {i: imagenes[i] for i in resultados_dict.keys()}
    
    # Mostrar resumen
    if resultados:
        st.divider()
        st.markdown("### 📊 Resumen de Facturas Procesadas")
        
        for resultado in resultados:
            pagina = resultado["pagina"]
            with st.container():
                from utils.image_utils import sanitize_html
                st.markdown(f"""
                <div style="background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 1.25rem; margin-bottom: 1rem;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem;">
                        <h4 style="color: var(--brand-300); margin: 0;">📄 Página {pagina}</h4>
                        <span style="color: var(--brand-400);">✓ Procesada</span>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Contrato:</strong> {sanitize_html(resultado.get("numero_contrato") or "N/A")}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Total:</strong> <span style="color: var(--brand-300);">${resultado.get('total_pagar', 0):,.0f}</span></p>
                        </div>
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Empresa:</strong> {sanitize_html(resultado.get("empresa") or "N/A")}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Referencia:</strong> {sanitize_html((resultado.get("codigo_referencia") or "N/A")[:25])}</p>
                        </div>
                        <div>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Período:</strong> {sanitize_html(resultado.get("periodo_facturado") or "N/A")}</p>
                            <p style="color: var(--gray-300); margin: 0.25rem 0;"><strong>Vencimiento:</strong> {sanitize_html(resultado.get("fecha_vencimiento") or "N/A")}</p>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with st.expander(f"🔍 Ver detalles completos - Página {pagina}", expanded=False):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        if pagina - 1 in imagenes_dict:
                            st.image(imagenes_dict[pagina - 1], caption=f"Página {pagina}", use_container_width=True)
                    with col2:
                        st.json(resultado)
    
    return resultados, estadisticas

