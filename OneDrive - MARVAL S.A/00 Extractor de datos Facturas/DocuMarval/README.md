# 📄 DocuMarval - Extractor Inteligente de Facturas

Sistema inteligente que extrae datos de facturas en PDF usando Google Gemini AI.

## 🚀 Características

- **IA Avanzada**: Usa Google Gemini para extracción precisa de datos
- **Procesamiento Paralelo**: Procesa múltiples páginas simultáneamente
- **Optimizado**: Caché, rate limiting y validación temprana
- **Multi-plataforma**: Funciona en Windows, Linux, Mac y Streamlit Cloud

## 🛠️ Instalación Local (Windows)

### Requisitos
- Python 3.12.10
- Última versión de Poppler descargada e instalada en el equipo. (https://github.com/oschwartz10612/poppler-windows/releases)
- Archivo `.env` en la raíz del proyecto, debe contener la siguiente información (reemplaza "..." con los datos correspondientes):
```markdown
GEMINI_API_KEY="..."
GEMINI_MODEL="..."
POPPLER_PATH="..."
```

### Cómo obtener la API Key de Google Gemini

1. Ve a la página de Google AI Studio: https://aistudio.google.com/

2. Inicia sesión con tu cuenta de Google.

3. Dirígete a la sección de "API Keys" y genera una nueva clave.

4. Copia la clave y colócala en el archivo .env así:

```markdown
GEMINI_API_KEY="tu_clave_aqui"
...
```

La API de Gemini ofrece un plan gratuito con límites mensuales. Consulta la documentación oficial para detalles actualizados.

#### 1. Clonar el repositorio
```bash
# Clonar repositorio
git clone https://github.com/KevinVincent016/LectorDeFacturas-IA.git
cd LectorDeFacturas-IA
```

#### 2. Crear entorno virtual
```bash
python -m venv venv
venv\Scripts\activate
```

#### 3. Instalar Poppler
Accede al repositorio de Poppler: https://github.com/oschwartz10612/poppler-windows/

Descarga el ultimo Zip, descomprime el archivo en la ubicacion de tu preferencia

#### 4. Configurar las variables de entorno
Entra o crea un archivo ´.env´ en la raíz del proyecto. Añade las siguientes variables:

```markdown
GEMINI_API_KEY="..."
GEMINI_MODEL="..."
POPPLER_PATH="..."
```

Y reemplaza los puntos suspensivos con los datos correspondientes.

#### 5. Instalar dependencias Python
```bash
pip install -r requirements.txt
```

#### 6. Ejecutar la aplicación
   ```powershell
   streamlit run lectorFacturas.py
   ```

## 🌐 Despliegue en Streamlit Cloud

Para desplegar la aplicación en Streamlit Cloud, consulta la guía completa en `STREAMLIT_CLOUD_DEPLOY.md`.

## Notas
- Si el entorno virtual fue movido de carpeta, se recomienda eliminarlo y crearlo nuevamente.
- Todas las dependencias necesarias están en el archivo `requirements.txt`.
- La aplicación usa Google Gemini AI para la extracción de datos, por lo que se recomienda que el PDF y las facturas tengan la mejor calidad posible.
- La solución procesa cada factura en el PDF con procesamiento paralelo para mayor velocidad.