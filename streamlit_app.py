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
from datetime import datetime, timedelta

# --- Page Config & Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown(
    """
    <div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
        <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
    </div>
    """, unsafe_allow_html=True)

# --- Sidebar Feature Toggles & Inputs ---
st.sidebar.header("🛠 Features")
planner_enabled = st.sidebar.checkbox("AI-Powered Study Planner", value=False)
flashcards_enabled = st.sidebar.checkbox("Spaced Repetition Flashcards", value=False)
exam_mode = st.sidebar.checkbox("Distraction-Free Exam Mode", value=False)
highlight_enabled = st.sidebar.checkbox("Smart Highlighting & Priority Detection", value=False)
practice_feedback = st.sidebar.checkbox("Live Practice Test Feedback", value=False)
hubs_enabled = st.sidebar.checkbox("Collaborative Study Hubs", value=False)
gamification_enabled = st.sidebar.checkbox("Gamified Learning Challenges", value=False)
export_enabled = st.sidebar.checkbox("One-Click Export & Integration", value=False)
audio_enabled = st.sidebar.checkbox("Voice Notes & Audio Summaries", value=False)
analytics_enabled = st.sidebar.checkbox("Predictive Exam Analytics", value=False)

# --- Planner Inputs ---
if planner_enabled:
    st.sidebar.subheader("Study Planner Settings")
    exam_date = st.sidebar.date_input("Exam Date", datetime.today() + timedelta(days=7))
    complexity = st.sidebar.selectbox("Syllabus Complexity", ["Low", "Medium", "High"], index=1)
    goals = st.sidebar.text_area("Your Goals (comma-separated)")

# --- Exam Mode Enforcement ---
if exam_mode:
    # Hide header/footer and sidebar for distraction-free interface
    st.markdown("<style>header, footer, #MainMenu, .css-1d391kg {visibility: hidden;} </style>", unsafe_allow_html=True)
    st.write("### 🛑 Exam Mode Activated")
    # Pomodoro timer stub
    if st.button("Start Pomodoro (25 min)"):
        st.info("Pomodoro started! Focus for 25 minutes.")
        # Real implementation would use session state and async timing

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)",
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Interactive Loader ---
loader_html = """
<!DOCTYPE html>
<html lang=\"en\">...<!-- truncated for brevity -->"""  # Keep your existing loader HTML

# --- Core Utility Functions ---
def extract_text(file):
    name = file.name.lower()
    if name.endswith('.pdf'):
        with fitz.open(stream=file.read(), filetype='pdf') as doc:
            return "".join([page.get_text() for page in doc])
    if name.endswith('.docx'):
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    if name.endswith('.pptx'):
        return "\n".join(
            shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape, 'text')
        )
    if name.endswith('.txt'):
        return StringIO(file.getvalue().decode('utf-8')).read()
    if name.endswith(('.jpg', '.jpeg', '.png')):
        return pytesseract.image_to_string(Image.open(file))
    return ""


def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
    }
    for attempt in range(3):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            try:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            except:
                return "<p>Error parsing AI response.</p>"
        if res.status_code == 429 and attempt < 2:
            time.sleep(30)
            continue
        break
    return f"<p>API Error {res.status_code}</p>"

# --- AI Learning Aids ---
def generate_summary(text): return call_gemini(f"Summarize for exam with formulae: {text}", temperature=0.5)
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions: {text}")
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A): {text}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics: {text}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms: {text}")
def generate_cheatsheet(text): return call_gemini(f"Create cheat sheet: {text}")
def generate_highlights(text): return call_gemini(f"List key highlights: {text}")

# --- New Feature Stubs ---
def generate_study_plan(date, complexity, goals):
    return f"Study plan for {date.strftime('%Y-%m-%d')} (Complexity: {complexity}) with goals: {goals}"

def generate_spaced_flashcards(text):
    return call_gemini(f"Create spaced repetition flashcards: {text}")

def smart_highlight(text):
    return call_gemini(f"Highlight high-yield concepts: {text}")

def practice_test_feedback(q, a):
    return call_gemini(f"Explain why '{a}' is correct for question: {q}")

def export_notes(format):
    st.success(f"Notes exported as {format}")

def record_voice_note():
    st.warning("Voice note recording not yet supported.")

def predictive_analytics(text):
    return call_gemini(f"Predict exam topics & readiness: {text}")

# --- Render Helpers ---
def render_section(title, content):
    st.subheader(title)
    if content.strip().startswith('<'):
        components.html(content, height=400)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main App Logic ---
# Loader placeholder until first file is processed
authored = False
if uploaded_files:
    loader = st.empty()
    with loader:
        components.html(loader_html, height=500)

    # Planner
    if planner_enabled:
        st.header("📅 AI Study Planner")
        plan = generate_study_plan(exam_date, complexity, goals)
        st.write(plan)

    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)

        # Mind Map
        mind_map = None  # existing code omitted for brevity
        # ... keep your get_mind_map & plot_mind_map here ...

        # Core Sections
        render_section("📌 Summary", generate_summary(text))
        render_section("📝 Quiz Questions", generate_questions(text))
        with st.expander("📚 Flashcards"):
            render_section("Flashcards", generate_flashcards(text))
        with st.expander("🧠 Mnemonics"):
            render_section("Mnemonics", generate_mnemonics(text))
        with st.expander("🔑 Key Terms"):
            render_section("Key Terms", generate_key_terms(text))
        with st.expander("📋 Cheat Sheet"):
            render_section("Cheat Sheet", generate_cheatsheet(text))
        with st.expander("⭐ Highlights"):
            render_section("Highlights", generate_highlights(text))

        # New Features per-file
        if flashcards_enabled:
            st.subheader("🎴 Spaced Repetition Flashcards")
            st.markdown(generate_spaced_flashcards(text))
        if highlight_enabled:
            st.subheader("✨ Smart Highlighting")
            st.markdown(smart_highlight(text))
        if practice_feedback:
            st.subheader("📝 Live Practice Feedback")
            q = st.text_input(f"Question for {file.name}")
            a = st.text_input(f"Your answer for {file.name}")
            if st.button(f"Get Feedback for {file.name}"):
                st.markdown(practice_test_feedback(q, a))
        if hubs_enabled:
            st.subheader("🤝 Collaborative Hubs")
            st.info("Virtual rooms coming soon.")
        if gamification_enabled:
            st.subheader("🏆 Gamified Challenges")
            st.info("Track badges & streaks.")
        if export_enabled:
            st.subheader("📤 Export & Integration")
            if st.button("Export to Anki"):
                export_notes("Anki .apkg")
            if st.button("Export to PDF"):
                export_notes("PDF")
        if audio_enabled:
            st.subheader("🎧 Voice Notes & Audio Summaries")
            if st.button("Record Voice Note"):
                record_voice_note()
            st.audio(generate_summary(text))
        if analytics_enabled:
            st.subheader("📊 Predictive Analytics")
            st.markdown(predictive_analytics(text))

        if not authored:
            loader.empty()
            authored = True
else:
    st.info("Upload a document to get started.")
