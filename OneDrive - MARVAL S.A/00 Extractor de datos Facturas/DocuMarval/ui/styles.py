"""Estilos CSS para DocuMarval"""
import streamlit as st

def load_custom_css():
    """Carga el CSS personalizado con identidad visual DocuMarval"""
    # Leer CSS del archivo original para mantener consistencia
    css_file = "lectorFacturas.py"
    try:
        with open(css_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Extraer solo la función load_custom_css
            start = content.find('def load_custom_css():')
            end = content.find('def main():', start)
            if start != -1 and end != -1:
                # Ejecutar la función directamente desde el archivo original
                exec(compile(content[start:end], css_file, 'exec'))
                # Llamar a la función
                load_custom_css()
                return
    except:
        pass
    
    # Fallback: CSS básico
    css = """
    <style>
    :root {
        --brand-900: #0B1220;
        --brand-800: #0F172A;
        --brand-700: #13223A;
        --brand-600: #173B5F;
        --brand-500: #1E5AA5;
        --brand-400: #2F7DEB;
        --brand-300: #72A8FF;
        --brand-200: #CFE1FF;
        --brand-100: #EAF1FF;
        --gray-900: #0F172A;
        --gray-700: #334155;
        --gray-500: #64748B;
        --gray-300: #CBD5E1;
        --gray-100: #F1F5F9;
        --white: #FFFFFF;
        --radius-md: 14px;
        --radius-lg: 16px;
        --elevation-1: 0 8px 24px rgba(0, 0, 0, 0.12);
        --elevation-2: 0 16px 36px rgba(0, 0, 0, 0.16);
        --glass-bg: rgba(255, 255, 255, 0.1);
        --glass-border: rgba(207, 225, 255, 0.3);
    }
    .stApp {
        background: linear-gradient(135deg, var(--brand-900) 0%, var(--brand-800) 50%, var(--brand-700) 100%);
        background-attachment: fixed;
        color: var(--white);
        min-height: 100vh;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

