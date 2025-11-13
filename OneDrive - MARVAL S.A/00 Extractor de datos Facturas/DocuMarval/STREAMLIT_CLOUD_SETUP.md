# 📋 Configuración Paso a Paso en Streamlit Cloud

## 🎯 Resumen

Tu aplicación **DocuMarval** está lista para desplegarse en Streamlit Cloud. El código funciona tanto localmente (usando `.env`) como en Streamlit Cloud (usando secrets).

---

## 📝 PASO 1: Acceder a Streamlit Cloud

1. Ve a: **https://share.streamlit.io**
2. Inicia sesión con tu cuenta de **GitHub**
3. Autoriza a Streamlit Cloud para acceder a tus repositorios

---

## 📝 PASO 2: Crear Nueva Aplicación

1. Haz clic en el botón **"New app"** o **"Deploy an app"**
2. Completa el formulario:

   ```
   Repository: pjojoa/DocuMarval
   Branch: main
   Main file path: app.py  ⚠️ IMPORTANTE: Debe ser "app.py"
   App URL: documarval (o el nombre que prefieras)
   ```

3. Haz clic en **"Deploy"**

---

## 🔐 PASO 3: Configurar Secrets (CRÍTICO)

**⚠️ ESTO ES LO MÁS IMPORTANTE** - Sin esto, la app no funcionará.

### Opción A: Desde la Página de Configuración

1. Una vez creada la app, ve a la página de tu aplicación
2. Haz clic en el menú de **3 puntos (⋮)** en la esquina superior derecha
3. Selecciona **"Settings"**
4. En el menú lateral izquierdo, haz clic en **"Secrets"**
5. Verás un editor de texto donde debes pegar:

```toml
GEMINI_API_KEY = "tu-clave-de-api-de-google-gemini-aqui"
GEMINI_MODEL = "gemini-2.5-flash"
```

6. Haz clic en **"Save"**

### Opción B: Desde el Dashboard

1. En el dashboard de Streamlit Cloud, encuentra tu app
2. Haz clic en el menú de 3 puntos junto a tu app
3. Selecciona **"Settings"**
4. Ve a la pestaña **"Secrets"**
5. Pega el contenido TOML y guarda

### 📌 Formato Correcto

**✅ CORRECTO:**
```toml
GEMINI_API_KEY = "AIzaSyBYHAkqVS5YkOf2BeiWqwL3oL9YqZxyRlw"
GEMINI_MODEL = "gemini-2.5-flash"
```

**❌ INCORRECTO (NO uses [secrets]):**
```toml
[secrets]
GEMINI_API_KEY = "..."
```

Streamlit Cloud agrega automáticamente el encabezado `[secrets]`, así que **NO lo incluyas**.

### 🔑 Dónde Obtener tu GEMINI_API_KEY

1. Ve a: **https://aistudio.google.com/**
2. Inicia sesión con tu cuenta de Google
3. Ve a la sección **"API Keys"**
4. Genera una nueva clave o copia una existente
5. Pégala en los secrets de Streamlit Cloud

---

## 📝 PASO 4: Verificar el Despliegue

1. Espera 2-5 minutos mientras Streamlit Cloud construye tu app
2. Revisa la pestaña **"Logs"** para ver si hay errores
3. Si todo está bien, verás: **"Your app is live!"**

---

## ✅ PASO 5: Probar la Aplicación

1. Accede a tu app en: `https://documarval.streamlit.app` (o la URL que configuraste)
2. Deberías ver la interfaz de DocuMarval
3. Verifica que aparezca:
   - ✅ Estado: "Gemini AI (gemini-2.5-flash)" con ✓
   - ✅ Estado: "Poppler disponible" con ✓
4. Prueba subir un PDF para verificar que funciona

---

## 🔧 Configuración Avanzada (Opcional)

### Si Necesitas Configurar POPPLER_PATH

Normalmente **NO es necesario**, ya que Streamlit Cloud tiene Poppler preinstalado y el código lo detecta automáticamente.

Solo si ves errores relacionados con Poppler en los logs, agrega esto a tus secrets:

```toml
GEMINI_API_KEY = "tu-clave"
GEMINI_MODEL = "gemini-2.5-flash"
POPPLER_PATH = "/usr/bin"
```

O prueba con:
```toml
POPPLER_PATH = "/usr/local/bin"
```

---

## 🐛 Solución de Problemas

### Error: "GEMINI_API_KEY not found"

**Solución:**
- Verifica que configuraste los secrets correctamente
- Asegúrate de que el formato sea correcto (sin `[secrets]`)
- Verifica que guardaste los cambios

### Error: "Poppler not found"

**Solución:**
- Normalmente no debería pasar
- Si ocurre, agrega `POPPLER_PATH = "/usr/bin"` a los secrets
- Revisa los logs para más detalles

### La app no se carga

**Solución:**
1. Revisa los logs en Streamlit Cloud
2. Verifica que el "Main file path" sea `app.py`
3. Verifica que todas las dependencias estén en `requirements.txt`
4. Intenta hacer "Redeploy" manualmente

### Error: "Module not found"

**Solución:**
- Verifica que `requirements.txt` tenga todas las dependencias
- Revisa los logs para ver qué módulo falta
- Asegúrate de que hiciste push de `requirements.txt` a GitHub

---

## 📊 Resumen de Configuración

| Configuración | Local | Streamlit Cloud |
|--------------|-------|-----------------|
| **Archivo principal** | `app.py` | `app.py` |
| **Configuración** | `.env` | Secrets (dashboard) |
| **GEMINI_API_KEY** | En `.env` | En Secrets |
| **GEMINI_MODEL** | En `.env` | En Secrets |
| **POPPLER_PATH** | En `.env` | Auto-detectado (no necesario) |

---

## 🔄 Actualizar la Aplicación

Para actualizar tu app después de hacer cambios:

1. Haz cambios en tu código local
2. Haz commit y push a GitHub:
   ```bash
   git add .
   git commit -m "Actualización"
   git push origin main
   ```
3. Streamlit Cloud detectará los cambios automáticamente
4. Redesplegará la app en 1-2 minutos

---

## ✅ Checklist Final

Antes de considerar que todo está listo:

- [ ] App creada en Streamlit Cloud
- [ ] Main file path configurado como `app.py`
- [ ] Secrets configurados (GEMINI_API_KEY, GEMINI_MODEL)
- [ ] App desplegada exitosamente
- [ ] Logs sin errores
- [ ] App accesible en la URL
- [ ] Estado de Gemini muestra ✓
- [ ] Estado de Poppler muestra ✓
- [ ] Probar subir un PDF funciona correctamente

---

## 📞 Recursos Útiles

- **Streamlit Cloud Dashboard**: https://share.streamlit.io
- **Documentación**: https://docs.streamlit.io/streamlit-community-cloud
- **Secrets Management**: https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management
- **Soporte**: https://discuss.streamlit.io/

---

## 🎉 ¡Listo!

Una vez completados estos pasos, tu aplicación **DocuMarval** estará funcionando en Streamlit Cloud y será accesible desde cualquier lugar del mundo.

**URL de ejemplo**: `https://documarval.streamlit.app`

¡Feliz despliegue! 🚀

