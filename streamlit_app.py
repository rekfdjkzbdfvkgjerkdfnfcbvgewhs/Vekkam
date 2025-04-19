import streamlit as st
import fitz  # PyMuPDF
import docx
import json
import re
from io import StringIO
from PIL import Image
import pytesseract
import plotly.graph_objects as go
import igraph as ig
import requests
from pptx import Presentation
import streamlit.components.v1 as components
import time
import networkx as nx

# --- Page Config & Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown("""
    <div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
        <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
    </div>
""", unsafe_allow_html=True)

# --- Language Selection ---
LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Spanish": "es",
    "French": "fr",
    "German": "de"
}
selected_lang = st.sidebar.selectbox("Select Output Language", list(LANGUAGES.keys()), index=0)
target_lang = LANGUAGES[selected_lang]

# --- Translation Helper ---
def translate_text(text, target_language):
    """
    Translate text to the target language using Gemini API.
    Skips translation if target_language is 'en'.
    """
    if target_language == 'en' or not text.strip():
        return text
    prompt = f"Translate the following text to {selected_lang}:\n\n{text}"
    return call_gemini(prompt, temperature=0)

# --- File Upload ---
uploaded_files = st.file_uploader(
    translate_text("Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)", target_lang),
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Interactive Loader HTML ---
loader_html = """
<!DOCTYPE html>
<html lang="en">
<head>
... (loader HTML remains unchanged) ...
</body>
</html>
"""

# --- Text Extraction ---
def extract_text(file):
    ext = file.name.lower()
    if ext.endswith(".pdf"):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            return "".join([page.get_text() for page in doc])
    elif ext.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    elif ext.endswith(".pptx"):
        return "\n".join(shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape, "text"))
    elif ext.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    elif ext.endswith((".jpg", ".jpeg", ".png")):
        return pytesseract.image_to_string(Image.open(file))
    return ""

# --- Gemini API Call ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    # ... existing retry logic ...
    # same as original code

# --- Generate Mind Map JSON ---
def get_mind_map(text):
    # ... original prompt and call_gemini logic ...
    parsed = json.loads(cleaned)
    if "nodes" not in parsed or "edges" not in parsed:
        raise ValueError("Response missing 'nodes' or 'edges'.")
    # Translate nodes/descriptions
    for node in parsed['nodes']:
        node['label'] = translate_text(node['label'], target_lang)
        node['description'] = translate_text(node.get('description', ''), target_lang)
    return parsed

# --- Plot Mind Map ---
def plot_mind_map(nodes, edges):
    # identical to original, labels already translated
    # ... original plotting code ...
    fig = go.Figure(...)
    components.html(fig.to_html(full_html=False, include_plotlyjs='cdn'), height=900, scrolling=True)

# --- AI Learning Aids ---
def generate_summary(text): 
    summary = call_gemini(f"Summarize this for an exam and separately list any formulae: {text}", temperature=0.5)
    return translate_text(summary, target_lang)

def generate_questions(text): 
    questions = call_gemini(f"Generate 15 quiz questions for an exam: {text}")
    return translate_text(questions, target_lang)

def generate_flashcards(text): 
    flashcards = call_gemini(f"Create flashcards (Q&A): {text}")
    return translate_text(flashcards, target_lang)

def generate_mnemonics(text): 
    mnemonics = call_gemini(f"Generate mnemonics: {text}")
    return translate_text(mnemonics, target_lang)

def generate_key_terms(text): 
    terms = call_gemini(f"List 10 key terms with definitions: {text}")
    return translate_text(terms, target_lang)

def generate_cheatsheet(text): 
    cheatsheet = call_gemini(f"Create a cheat sheet: {text}")
    return translate_text(cheatsheet, target_lang)

def generate_highlights(text): 
    highlights = call_gemini(f"List key facts and highlights: {text}")
    return translate_text(highlights, target_lang)

# --- Display Helper ---
def render_section(title, content):
    translated_title = translate_text(title, target_lang)
    st.subheader(translated_title)
    if content.strip().startswith("<"):
        components.html(content, height=600, scrolling=True)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
if uploaded_files:
    loader_placeholder = st.empty()
    with loader_placeholder:
        components.html(loader_html, height=600)
    first_file_processed = False

    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)
        mind_map = get_mind_map(text)
        summary = generate_summary(text)
        questions = generate_questions(text)
        flashcards = generate_flashcards(text)
        mnemonics = generate_mnemonics(text)
        key_terms = generate_key_terms(text)
        cheatsheet = generate_cheatsheet(text)
        highlights = generate_highlights(text)

        if mind_map:
            st.subheader(translate_text("🧠 Mind Map (ChatGPT can't do this)", target_lang))
            plot_mind_map(mind_map["nodes"], mind_map["edges"])
        else:
            st.error(translate_text("Mind map generation failed.", target_lang))

        render_section("📌 Summary", summary)
        render_section("📝 Quiz Questions", questions)
        with st.expander(translate_text("📚 Flashcards", target_lang)):
            render_section("Flashcards", flashcards)
        with st.expander(translate_text("🧠 Mnemonics", target_lang)):
            render_section("Mnemonics", mnemonics)
        with st.expander(translate_text("🔑 Key Terms", target_lang)):
            render_section("Key Terms", key_terms)
        with st.expander(translate_text("📋 Cheat Sheet", target_lang)):
            render_section("Cheat Sheet", cheatsheet)
        with st.expander(translate_text("⭐ Highlights", target_lang)):
            render_section("Highlights", highlights)

        if not first_file_processed:
            loader_placeholder.empty()
            first_file_processed = True
else:
    st.info(translate_text("Upload a document to get started.", target_lang))
