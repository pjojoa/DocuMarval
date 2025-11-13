# 🚀 Guía de Despliegue en Streamlit Cloud

Esta guía te ayudará a desplegar DocuMarval en Streamlit Cloud (gratis y oficial).

## 📋 Requisitos Previos

1. **Cuenta en Streamlit Cloud**: 
   - Ve a [share.streamlit.io](https://share.streamlit.io)
   - Inicia sesión con tu cuenta de GitHub

2. **Repositorio en GitHub**: 
   - Tu código debe estar en un repositorio público de GitHub
   - O en un repositorio privado si tienes cuenta de Streamlit Cloud Pro

3. **API Key de Gemini**: 
   - Necesitas tu clave de API de Google Gemini

## 🎯 Pasos para Desplegar

### Paso 1: Verificar que tu código esté en GitHub

Asegúrate de que todos los archivos estén en tu repositorio:
- ✅ `lectorFacturas.py` (archivo principal)
- ✅ `requirements.txt`
- ✅ `.streamlit/config.toml`
- ✅ `Logo.svg` y `Logo_DocuMarval.svg` (si los usas)

### Paso 2: Acceder a Streamlit Cloud

1. Ve a [share.streamlit.io](https://share.streamlit.io)
2. Inicia sesión con tu cuenta de GitHub
3. Autoriza a Streamlit Cloud para acceder a tus repositorios

### Paso 3: Crear Nueva App

1. Haz clic en **"New app"** o **"Deploy an app"**
2. Selecciona tu repositorio: `pjojoa/DocuMarval`
3. Selecciona la rama: `main` (o la que uses)

### Paso 4: Configurar la App

#### Configuración Básica:
- **App name**: `documarval` (o el nombre que prefieras)
- **Main file path**: `lectorFacturas.py`
- **Python version**: Streamlit Cloud usa automáticamente la versión compatible

#### Configuración Avanzada (opcional):
- **App URL**: Se generará automáticamente como `documarval.streamlit.app`
- Puedes personalizarlo si tienes cuenta Pro

### Paso 5: Configurar Secrets (Variables de Entorno)

**IMPORTANTE**: Necesitas configurar tus secrets antes de desplegar.

1. En la página de configuración de tu app, haz clic en **"Advanced settings"**
2. Haz clic en **"Secrets"** o busca el botón de configuración de secrets
3. Agrega las siguientes variables:

```toml
GEMINI_API_KEY = "tu-clave-de-api-aqui"
GEMINI_MODEL = "gemini-2.5-flash"
POPPLER_PATH = "/usr/bin"
```

**Formato del archivo secrets.toml en Streamlit Cloud:**
```toml
[secrets]
GEMINI_API_KEY = "AIzaSyBYHAkqVS5YkOf2BeiWqwL3oL9YqZxyRlw"
GEMINI_MODEL = "gemini-2.5-flash"
POPPLER_PATH = "/usr/bin"
```

### Paso 6: Desplegar

1. Haz clic en **"Deploy"** o **"Save"**
2. Streamlit Cloud comenzará a construir y desplegar tu aplicación
3. El proceso tomará aproximadamente 2-5 minutos

### Paso 7: Verificar el Despliegue

1. **Revisa los logs**:
   - Ve a la pestaña "Logs" en tu app
   - Busca mensajes de éxito o errores

2. **Accede a tu aplicación**:
   - Tu app estará disponible en: `https://documarval.streamlit.app`
   - O la URL que hayas configurado

## 🔧 Configuración de Poppler en Streamlit Cloud

Streamlit Cloud tiene Poppler preinstalado, pero puede estar en diferentes ubicaciones. Tu código ya maneja esto automáticamente, pero si hay problemas:

1. Verifica en los logs si hay errores relacionados con Poppler
2. Si es necesario, ajusta `POPPLER_PATH` en los secrets:
   - `/usr/bin` (más común)
   - `/usr/local/bin`
   - O déjalo vacío si está en PATH

## 📝 Notas Importantes

### Ventajas de Streamlit Cloud:
- ✅ **Gratis** para repositorios públicos
- ✅ **Despliegue automático** con cada push a GitHub
- ✅ **Sin configuración de servidor**
- ✅ **URL pública** automática
- ✅ **Poppler preinstalado**

### Limitaciones del Plan Gratuito:
- ⚠️ Repositorios deben ser **públicos**
- ⚠️ Límite de uso (pero generoso)
- ⚠️ Se puede "dormir" después de inactividad (se despierta automáticamente)

### Plan Pro (de pago):
- ✅ Repositorios privados
- ✅ Apps siempre activas
- ✅ Más recursos
- ✅ URLs personalizadas

## 🔄 Actualizar la Aplicación

Para actualizar tu aplicación:
1. Haz cambios en tu código local
2. Haz commit y push a GitHub
3. Streamlit Cloud detectará los cambios automáticamente
4. Redesplegará la app en 1-2 minutos

## 🐛 Solución de Problemas

### Error: "Module not found"
- Verifica que todas las dependencias estén en `requirements.txt`
- Revisa los logs para ver qué módulo falta

### Error: "GEMINI_API_KEY not found"
- Verifica que hayas configurado los secrets correctamente
- Asegúrate de que el formato del secrets.toml sea correcto

### Error: "Poppler not found"
- Streamlit Cloud tiene Poppler, pero verifica la ruta
- Prueba diferentes valores para `POPPLER_PATH` en secrets

### La app no se actualiza
- Verifica que hayas hecho push a GitHub
- Revisa los logs para ver si hay errores de build
- Intenta hacer "Redeploy" manualmente desde el dashboard

## 📞 Recursos

- [Documentación de Streamlit Cloud](https://docs.streamlit.io/streamlit-community-cloud)
- [Guía de Secrets](https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Soporte de Streamlit](https://discuss.streamlit.io/)

## ✅ Checklist de Despliegue

- [ ] Código subido a GitHub
- [ ] Cuenta creada en Streamlit Cloud
- [ ] App creada en Streamlit Cloud
- [ ] Secrets configurados (GEMINI_API_KEY, GEMINI_MODEL)
- [ ] App desplegada exitosamente
- [ ] App accesible en la URL proporcionada
- [ ] Probar subir un PDF y verificar que funciona

¡Listo! Tu aplicación debería estar funcionando en Streamlit Cloud. 🎉

