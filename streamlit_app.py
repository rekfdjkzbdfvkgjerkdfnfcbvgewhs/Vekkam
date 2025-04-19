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

# --- Gemini API Call (needed by translation & generative functions) ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    max_retries = 3
    retry_delay = 30  # seconds
    for attempt in range(max_retries):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            try:
                return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                return f"<p>Error parsing response: {e}</p>"
        elif res.status_code == 429:
            if attempt < max_retries - 1:
                st.warning("Rate limit reached. Retrying in 30 seconds...")
                time.sleep(retry_delay)
            else:
                return "<p>API rate limit reached. Please try again later.</p>"
        else:
            break
    return f"<p>Gemini API error {res.status_code}: {res.text}</p>"

# --- Translation Helper ---
def translate_text(text, target_language):
    """
    Translate text to the target language using Gemini API.
    Skips translation if target_language is 'en' or text is empty.
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
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Brainrot Loader</title>
  <style>
    body { margin: 0; font-family: 'Comic Sans MS', cursive, sans-serif; background: linear-gradient(135deg, #ff9a9e 0%, #fad0c4 100%); overflow: hidden; text-align: center; }
    #loader { width: 100%; height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; }
    #progress { font-size: 30px; margin-top: 30px; color: #ff4500; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); animation: pulse 2s infinite; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.1); } 100% { transform: scale(1); } }
    .mascot { width: 150px; height: 150px; background: url('mascot.png') no-repeat center center; background-size: contain; animation: bounce 2s infinite; }
    @keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-20px); } }
  </style>
</head>
<body>
  <div id="loader">
    <div class="mascot"></div>
    <div id="progress">Loading... 0%</div>
  </div>
  <script>
    let progress = 0;
    const progressText = document.getElementById('progress');
    const interval = setInterval(() => {
      progress = (progress + 1) % 101;
      progressText.textContent = `Loading... ${progress}%`;
    }, 550);
    const observer = new MutationObserver(mutations => {
      mutations.forEach(mutation => {
        if (!document.body.contains(document.getElementById("loader"))) {
          clearInterval(interval);
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  </script>
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

# --- Generate Mind Map JSON ---
def get_mind_map(text):
    prompt = f"..."  # original mind map prompt
    response = call_gemini(prompt, temperature=0.5)
    # parse JSON as before
    parsed = json.loads(re.search(r'\{.*\}', response, re.DOTALL).group(0))
    # translate labels and descriptions
    for node in parsed.get('nodes', []):
        node['label'] = translate_text(node['label'], target_lang)
        node['description'] = translate_text(node.get('description', ''), target_lang)
    return parsed

# --- Plot Mind Map ---
def plot_mind_map(nodes, edges):
    # plotting logic unchanged
    ...

# --- AI Learning Aids ---
def generate_summary(text):
    out = call_gemini(f"Summarize this for an exam: {text}", temperature=0.5)
    return translate_text(out, target_lang)

# similarly wrap other generators
def generate_questions(text): return translate_text(call_gemini(f"Generate 15 quiz questions: {text}"), target_lang)
def generate_flashcards(text): return translate_text(call_gemini(f"Create flashcards (Q&A): {text}"), target_lang)
def generate_mnemonics(text): return translate_text(call_gemini(f"Generate mnemonics: {text}"), target_lang)
def generate_key_terms(text): return translate_text(call_gemini(f"List 10 key terms with definitions: {text}"), target_lang)
def generate_cheatsheet(text): return translate_text(call_gemini(f"Create a cheat sheet: {text}"), target_lang)
def generate_highlights(text): return translate_text(call_gemini(f"List key facts and highlights: {text}"), target_lang)

# --- Display Helper ---
def render_section(title, content):
    st.subheader(translate_text(title, target_lang))
    if content.strip().startswith("<"):
        components.html(content, height=600, scrolling=True)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main ---
if uploaded_files:
    loader = st.empty(); loader.components.html(loader_html, height=600)
    first = False
    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        t = extract_text(file)
        mm = get_mind_map(t)
        s = generate_summary(t)
        q = generate_questions(t)
        f = generate_flashcards(t)
        m = generate_mnemonics(t)
        kt = generate_key_terms(t)
        cs = generate_cheatsheet(t)
        h = generate_highlights(t)
        if mm:
            st.subheader(translate_text("🧠 Mind Map", target_lang)); plot_mind_map(mm['nodes'], mm['edges'])
        else:
            st.error(translate_text("Mind map generation failed.", target_lang))
        render_section("📌 Summary", s)
        render_section("📝 Quiz Questions", q)
        with st.expander(translate_text("📚 Flashcards", target_lang)): render_section("Flashcards", f)
        with st.expander(translate_text("🧠 Mnemonics", target_lang)): render_section("Mnemonics", m)
        with st.expander(translate_text("🔑 Key Terms", target_lang)): render_section("Key Terms", kt)
        with st.expander(translate_text("📋 Cheat Sheet", target_lang)): render_section("Cheat Sheet", cs)
        with st.expander(translate_text("⭐ Highlights", target_lang)): render_section("Highlights", h)
        if not first:
            loader.empty(); first = True
else:
    st.info(translate_text("Upload a document to get started.", target_lang))
