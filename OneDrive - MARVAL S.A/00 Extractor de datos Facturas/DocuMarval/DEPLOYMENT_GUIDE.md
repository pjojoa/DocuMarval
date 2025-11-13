# 🚀 Guía Rápida de Despliegue en Streamlit Cloud

## ⚡ Pasos Rápidos

### 1. Preparar el Repositorio
- ✅ Asegúrate de que tu código esté en GitHub
- ✅ El archivo principal debe ser `app.py`
- ✅ `requirements.txt` debe estar actualizado

### 2. Crear App en Streamlit Cloud

1. Ve a [share.streamlit.io](https://share.streamlit.io)
2. Inicia sesión con GitHub
3. Haz clic en **"New app"**
4. Configura:
   - **Repository**: `pjojoa/DocuMarval`
   - **Branch**: `main`
   - **Main file path**: `app.py` ⚠️ **IMPORTANTE**
   - **App URL**: Se genera automáticamente

### 3. Configurar Secrets (CRÍTICO)

**IMPORTANTE**: Debes configurar los secrets ANTES de desplegar.

1. En la página de configuración de tu app, busca **"Secrets"** o **"Advanced settings"**
2. Haz clic en **"Secrets"**
3. Pega el siguiente contenido (reemplaza con tus valores reales):

```toml
GEMINI_API_KEY = "tu-clave-de-api-de-google-gemini"
GEMINI_MODEL = "gemini-2.5-flash"
```

**Nota**: `POPPLER_PATH` NO es necesario normalmente, ya que Streamlit Cloud tiene Poppler preinstalado y el código lo detecta automáticamente.

### 4. Desplegar

1. Haz clic en **"Deploy"** o **"Save"**
2. Espera 2-5 minutos mientras se construye la app
3. Revisa los logs si hay errores

### 5. Verificar

- Tu app estará en: `https://documarval.streamlit.app` (o la URL que configuraste)
- Prueba subir un PDF para verificar que funciona

## 🔧 Configuración Detallada en Streamlit Cloud

### Dónde Configurar Secrets

1. Ve a tu app en [share.streamlit.io](https://share.streamlit.io)
2. Haz clic en el menú de 3 puntos (⋮) junto a tu app
3. Selecciona **"Settings"**
4. En el menú lateral, haz clic en **"Secrets"**
5. Pega el contenido TOML con tus secrets

### Formato Correcto de Secrets

```toml
GEMINI_API_KEY = "AIzaSy..."
GEMINI_MODEL = "gemini-2.5-flash"
```

**NO uses** `[secrets]` como encabezado. Streamlit Cloud lo agrega automáticamente.

### Si Necesitas POPPLER_PATH

Solo si ves errores relacionados con Poppler en los logs:

```toml
GEMINI_API_KEY = "tu-clave"
GEMINI_MODEL = "gemini-2.5-flash"
POPPLER_PATH = "/usr/bin"
```

## ✅ Checklist

- [ ] Código en GitHub
- [ ] App creada en Streamlit Cloud
- [ ] Main file path: `app.py`
- [ ] Secrets configurados (GEMINI_API_KEY, GEMINI_MODEL)
- [ ] App desplegada exitosamente
- [ ] Logs sin errores
- [ ] App funciona correctamente

## 🐛 Problemas Comunes

### Error: "Module not found"
- Verifica que `requirements.txt` tenga todas las dependencias
- Revisa los logs para ver qué módulo falta

### Error: "GEMINI_API_KEY not found"
- Verifica que configuraste los secrets correctamente
- Asegúrate de que el formato sea correcto (sin `[secrets]`)

### Error: "Poppler not found"
- Normalmente no debería pasar, pero si ocurre:
  - Agrega `POPPLER_PATH = "/usr/bin"` a los secrets
  - O prueba con `POPPLER_PATH = "/usr/local/bin"`

### La app no se actualiza
- Verifica que hiciste push a GitHub
- Revisa los logs
- Intenta "Redeploy" manualmente

## 📝 Notas

- **Local**: La app usa `.env` para configuración
- **Streamlit Cloud**: La app usa `secrets` desde el dashboard
- **Ambos funcionan**: El código detecta automáticamente dónde está corriendo

¡Listo! 🎉

