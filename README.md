# 📄 Extractor Híbrido de Facturas

Sistema inteligente que extrae datos de facturas en PDF usando Tesseract OCR y Gemini AI.

## 🚀 Características

- **Adaptativo**: Detecta automáticamente qué herramientas están disponibles
- **Híbrido**: Usa Tesseract primero (gratis) y Gemini como fallback
- **Multi-plataforma**: Funciona en Windows, Linux, Mac y en la nube

## 🛠️ Instalación Local (Windows)

### Requisitos
- Python 3.12.10
- Ultima version de Tesseract descargado e instalado en el equipo. (https://github.com/UB-Mannheim/tesseract/wiki)
- Ultima version de Poppler descargada e instalada en el equipo. (https://github.com/oschwartz10612/poppler-windows/releases)
- Archivo `.env` en la raíz del proyecto, debe contener la siguiente información (reemplazae "..." con los datos correspondientes):
```markdown
GEMINI_API_KEY="..."
GEMINI_MODEL="..."
TESSERACT_PATH="..."
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

#### 3. Instalar Tesseract OCR
Accede al repositorio de Tesseract: https://github.com/UB-Mannheim/tesseract/wiki

Descarga el instalador, ejecutalo y sigue las instrucciones.

#### 4. Instalar Poppler
Accede al repositorio de Poppler: https://github.com/oschwartz10612/poppler-windows/

Descarga el ultimo Zip, descomprime el archivo en la ubicacion de tu preferencia

#### 5. Configurar variables de entorno
Añade Tesseract OCR y Poppler al PATH del sistema.

#### 6. Configurar las variables de entorno
Entra o crea un archivo ´.env´ en la raíz del proyecto. Añade las siguientes variables:

```markdown
GEMINI_API_KEY="..."
GEMINI_MODEL="..."
TESSERACT_PATH="..."
POPPLER_PATH="..."
```

Y reemplaza los puntos suspensivos con los datos correspondientes.

#### 7. Instalar dependencias Python
```bash
pip install -r requirements.txt
```

#### 8. Ejecutar la aplicación
   ```powershell
   streamlit run lectorFacturas.py
   ```

## Notas
- Si el entorno virtual fue movido de carpeta, se recomienda eliminarlo y crearlo nuevamente.
- Todas las dependencias necesarias están en el archivo `requirements.txt`.
- En de que Tesseract falle o presente resultados insatisfactorios se utiliza Gemini AI como respaldo, por lo que se recomienda que el PDF y las facturas en el tengan la mejor calidad posible.
