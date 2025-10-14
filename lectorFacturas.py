import streamlit as st
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
                elif os.getenv('TESSERACT_PATH') or st.secrets.get("TESSERACT_PATH", None):
                    ruta_secrets = st.secrets["TESSERACT_PATH"]
                    if os.path.exists(ruta_secrets):
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
        poppler_path = os.getenv('POPPLER_PATH') or st.secrets.get("POPPLER_PATH", None)
        
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
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY') or st.secrets.get("GEMINI_API_KEY", "")
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
        model = genai.GenerativeModel(os.getenv('GEMINI_MODEL') or st.secrets.get("GEMINI_MODEL", "gemini-2.5-flash"))
        
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
            st.info("ℹ️ Tesseract no disponible, usando Gemini")
        
        with st.spinner("🤖 Extrayendo con Gemini..."):
            datos = extraer_con_gemini(imagen)
            metodo_usado = "Gemini"
            
            if datos:
                st.success("✅ Extraído con Gemini")
            else:
                st.error("❌ Error con Gemini")
                datos = {}
            
            return datos, metodo_usado, ""
    
    # Intentar con Tesseract primero
    with st.spinner("🔍 Extrayendo con Tesseract..."):
        texto_ocr, data_ocr = extraer_con_tesseract(imagen)
        confianza = calcular_confianza_ocr(texto_ocr, data_ocr)
        
        st.info(f"📊 Confianza Tesseract: {confianza:.1%}")
        
        if confianza >= umbral_confianza:
            st.success("✅ Calidad suficiente, usando Tesseract")
            datos = parsear_factura_tesseract(texto_ocr)
            metodo_usado = "Tesseract"
            return datos, metodo_usado, texto_ocr
        else:
            st.warning("⚠️ Confianza baja, usando Gemini...")
    
    # Usar Gemini como fallback
    with st.spinner("🤖 Extrayendo con Gemini..."):
        datos = extraer_con_gemini(imagen)
        metodo_usado = "Gemini"
        
        if datos:
            st.success("✅ Extraído con Gemini")
        else:
            st.error("❌ Usando datos de Tesseract como fallback")
            datos = parsear_factura_tesseract(texto_ocr)
        
        return datos, metodo_usado, texto_ocr

# ==================== PROCESAMIENTO DE PDF ====================

def procesar_pdf(pdf_bytes, umbral_confianza=0.8, forzar_gemini=False):
    """Procesa un PDF con detección automática de herramientas disponibles"""
    
    try:
        with st.spinner("📄 Convirtiendo PDF a imágenes..."):
            if POPPLER_PATH and platform.system() == 'Windows':
                imagenes = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH)
            else:
                imagenes = convert_from_bytes(pdf_bytes, dpi=300)
        
        st.success(f"✅ {len(imagenes)} página(s) convertida(s)")
        
    except Exception as e:
        st.error(f"❌ Error al convertir PDF: {str(e)}")
        if not POPPLER_DISPONIBLE:
            st.warning("⚠️ Poppler no está instalado. Instálalo para procesar PDFs.")
        return [], {}
    
    resultados = []
    estadisticas = {"tesseract": 0, "gemini": 0, "total": len(imagenes)}
    
    progress_bar = st.progress(0)
    
    for i, imagen in enumerate(imagenes):
        st.divider()
        st.subheader(f"🧾 Factura {i+1} de {len(imagenes)}")
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(imagen, caption=f"Página {i+1}", width=300)
        
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
                    st.metric("📄 Contrato", datos.get("numero_contrato", "N/A"))
                    st.metric("💰 Total", f"${datos.get('total_pagar', 0):,.0f}")
                
                with col_b:
                    st.metric("🔢 Referencia", datos.get("codigo_referencia", "N/A")[:15] + "...")
                    st.metric("🏠 Dirección", datos.get("direccion", "N/A")[:20] + "...")
                
                # Expandible con datos completos
                with st.expander("📋 Ver todos los datos extraídos"):
                    st.json(datos)
                
                if texto_ocr and metodo == "Tesseract":
                    with st.expander("📝 Ver texto OCR (Tesseract)"):
                        st.warning("⚠️ Este texto puede contener errores de OCR")
                        st.text(texto_ocr[:1000] + "..." if len(texto_ocr) > 1000 else texto_ocr)
        
        progress_bar.progress((i + 1) / len(imagenes))
    
    return resultados, estadisticas

# ==================== INTERFAZ STREAMLIT ====================

def main():
    st.set_page_config(
        page_title="Extractor Híbrido de Facturas",
        page_icon="📄",
        layout="wide"
    )
    
    st.title("📄 Extractor de Facturas de Servicios Públicos")
    
    # Banner de estado del sistema
    st.markdown("### 🔧 Estado del Sistema")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if TESSERACT_DISPONIBLE:
            st.success(f"✅ Tesseract {TESSERACT_VERSION}")
        else:
            st.warning("⚠️ Tesseract no disponible")
    
    with col2:
        if OPENCV_DISPONIBLE:
            st.success("✅ OpenCV disponible")
        else:
            st.info("ℹ️ OpenCV no disponible (opcional)")
    
    with col3:
        if POPPLER_DISPONIBLE:
            st.success("✅ Poppler disponible")
        else:
            st.error("❌ Poppler requerido")
    
    st.markdown("""
    ---
    **Sistema Híbrido Inteligente:**
    - 🔍 Extrae: No. Contrato, Dirección, Código de Referencia, Total a Pagar
    - 🤖 Usa Tesseract primero (gratis), Gemini como respaldo
    - ⚡ Optimizado para facturas de servicios públicos colombianos
    """)
    
    # Mostrar ejemplo de campos
    with st.expander("📋 Campos que se extraen"):
        st.markdown("""
        1. **No. CONTRATO**: Número de contrato del cliente
        2. **Dirección**: Dirección completa del inmueble
        3. **Código de Referencia**: Para pago electrónico/PSE
        4. **TOTAL A PAGAR**: Monto final a pagar
        5. *Adicionales*: Empresa, periodo, fecha de vencimiento
        """)
    
    # Sidebar
    with st.sidebar:
        
        st.subheader("🎯 Opciones")
        
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
            value=0.8,  # Aumentado para facturas complejas
            step=0.1,
            disabled=not TESSERACT_DISPONIBLE,
            help="Para facturas de servicios públicos, se recomienda 0.7-0.8 (usa más Gemini)"
        )
        
        st.divider()
        
        with st.expander("📦 Instalación de dependencias"):
            st.markdown("""
            **Para Windows (desarrollo local):**
            - Tesseract: [Descargar](https://github.com/UB-Mannheim/tesseract/wiki)
            - Poppler: [Descargar](https://github.com/oschwartz10612/poppler-windows/releases)
            
            **Para Streamlit Cloud (deployment):**
            Crea `packages.txt`:
            ```
            tesseract-ocr
            tesseract-ocr-spa
            poppler-utils
            ```
            
            **Requirements.txt:**
            ```
            streamlit
            google-generativeai
            pytesseract
            pdf2image
            Pillow
            pandas
            openpyxl
            opencv-python-headless
            ```
            """)
    
    # Upload
    uploaded_file = st.file_uploader(
        "📤 Sube tu PDF con facturas",
        type=['pdf']
    )
    
    if uploaded_file:
        if not POPPLER_DISPONIBLE:
            st.error("❌ No se puede procesar PDF sin Poppler instalado")
            st.info("Instala Poppler siguiendo las instrucciones en el sidebar")
            return
        
        if st.button("🚀 Procesar Facturas", type="primary", use_container_width=True):
            
            if not GEMINI_API_KEY:
                st.error("⚠️ No se encontró la API key de Gemini. Configúrala en los secrets de la aplicación.")
                return
            
            pdf_bytes = uploaded_file.read()
            facturas, stats = procesar_pdf(pdf_bytes, umbral, forzar_gemini)
            
            if facturas:
                st.divider()
                st.balloons()
                st.success(f"🎉 {len(facturas)} factura(s) procesada(s)")
                
                # Estadísticas
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📊 Total", stats['total'])
                with col2:
                    st.metric("🔧 Tesseract", stats['tesseract'])
                with col3:
                    st.metric("🤖 Gemini", stats['gemini'])
                with col4:
                    ahorro = (stats['tesseract'] / stats['total'] * 100) if stats['total'] > 0 else 0
                    st.metric("💰 Ahorro", f"{ahorro:.0f}%")
                
                # DataFrame
                df = pd.DataFrame(facturas)
                
                columnas_orden = ['pagina', 'numero_contrato', 'direccion', 'codigo_referencia',
                                 'total_pagar', 'empresa', 'periodo_facturado', 
                                 'fecha_vencimiento', 'metodo_extraccion']
                columnas_existentes = [col for col in columnas_orden if col in df.columns]
                df = df[columnas_existentes]
                
                st.subheader("📋 Resultados")
                st.dataframe(df)
                
                # Excel
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Facturas')
                    pd.DataFrame([stats]).to_excel(writer, index=False, sheet_name='Estadísticas')
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_data,
                    file_name=f"facturas_{uploaded_file.name.replace('.pdf', '')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

if __name__ == "__main__":
    main()