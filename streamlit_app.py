import os
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
from fpdf import FPDF
import genanki
import pandas as pd
import speech_recognition as sr

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
exam_date = st.sidebar.date_input("Exam Date", datetime.today().date() + timedelta(days=7))
complexity = st.sidebar.selectbox("Syllabus Complexity", ["Low", "Medium", "High"], index=1)
hubs_enabled = st.sidebar.checkbox("Collaborative Study Hubs")
export_enabled = st.sidebar.checkbox("One-Click Export & Integration")
audio_enabled = st.sidebar.checkbox("Voice Notes & Audio Summaries")
enable_planner = st.sidebar.checkbox("Auto Study Plan by Chapters (AI)", value=True)

# --- Exam Mode & Pomodoro ---
exam_mode = st.sidebar.checkbox("Distraction-Free Exam Mode")
if exam_mode:
    st.markdown("<style>header, footer, #MainMenu, .css-1d391kg {visibility: hidden;} </style>", unsafe_allow_html=True)
    st.write("### 🛑 Exam Mode Activated")
    if 'pomodoro_end' not in st.session_state:
        if st.button("Start Pomodoro (25 min)"):
            st.session_state.pomodoro_end = time.time() + 25*60
    else:
        remaining = int(st.session_state.pomodoro_end - time.time())
        if remaining > 0:
            st.info(f"Time remaining: {remaining//60}:{remaining%60:02d}")
            try:
                st.rerun()
            except AttributeError:
                try:
                    st.rerun()
                except AttributeError:
                    pass
        else:
            st.success("Pomodoro complete!")
            del st.session_state.pomodoro_end

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)",
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Rooms for Collaborative Hubs ---
if hubs_enabled:
    room_id = st.sidebar.text_input("Room ID (shared)")
    nickname = st.sidebar.text_input("Your Name")
    if room_id:
        os.makedirs("rooms", exist_ok=True)
        room_file = os.path.join("rooms", f"{room_id}.json")
        if not os.path.exists(room_file):
            with open(room_file, "w") as f: json.dump([], f)

# --- Utility Functions ---
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

# Detect chapters by heading patterns
def extract_chapters(text):
    lines = text.splitlines()
    chapters = []
    pattern = re.compile(r'^(?:Chapter|CHAPTER)\s*\d+[:.\-]?\s*(.*)', re.IGNORECASE)
    for line in lines:
        m = pattern.match(line.strip())
        if m:
            title = m.group(1).strip() or "Chapter"
            chapters.append(title)
    # Fallback: first 10 paragraphs
    if not chapters:
        paras = [p for p in text.split('\n\n') if p.strip()]
        chapters = [paras[i][:50] + '...' for i in range(min(10, len(paras)))]
    return chapters

# AI call helper
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents":[{"parts":[{"text":prompt}]}], "generationConfig":{"temperature":temperature,"maxOutputTokens":max_tokens}}
    for _ in range(3):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json()['candidates'][0]['content']['parts'][0]['text']
        if res.status_code == 429:
            time.sleep(30)
    return f"<p>API Error: {res.status_code}</p>"

# --- Learning Aids ---
def generate_summary(text): return call_gemini(f"Summarize for exam with formulae: {text}", 0.5)
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions: {text}")

def generate_spaced_flashcards(text):
    fronts = extract_chapters(text)
    cards = [{'Front':c, 'Back':f'Description of {c}', 'Interval':[1,3,7]} for c in fronts]
    return pd.DataFrame(cards)

def smart_highlight(text):
    return extract_chapters(text)[:5]

def practice_test_feedback(q,a): return call_gemini(f"Explain why '{a}' is correct for question: {q}")

# Exporters
class PDFExporter:
    @staticmethod
    def to_pdf(text, filename):
        os.makedirs('exports', exist_ok=True)
        pdf = FPDF(); pdf.add_page(); pdf.set_font('Arial', size=12)
        for line in text.split('\n'): pdf.multi_cell(0,10,line)
        path = f"exports/{filename}.pdf"; pdf.output(path)
        return path

class AnkiExporter:
    @staticmethod
    def to_anki(df):
        model = genanki.Model(1607392319, 'SimpleModel', fields=[{'name':'Front'},{'name':'Back'}],
            templates=[{'name':'Card 1','qfmt':'{{Front}}','afmt':'{{FrontSide}}<hr>{{Back}}'}])
        deck = genanki.Deck(2059400110, 'VekkamDeck')
        for _,row in df.iterrows(): deck.add_note(genanki.Note(model=model, fields=[row['Front'],row['Back']]))
        os.makedirs('exports', exist_ok=True)
        path = 'exports/vekkam.apkg'; genanki.Package(deck).write_to_file(path)
        return path

 def record_and_summarize():
    audio = st.file_uploader("Upload WAV/MP3 voice note:", type=["wav","mp3"])
    if audio:
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio) as source:
            data = recognizer.record(source)
            text = recognizer.recognize_google(data)
            summary = generate_summary(text)
            st.write("**Transcript:**", text)
            st.write("**Summary:**", summary)

def predictive_analytics(text): return call_gemini(f"Predict exam topics & readiness: {text}")

def render_section(title, content):
    st.subheader(title)
    if isinstance(content, pd.DataFrame): st.dataframe(content)
    elif isinstance(content, list): st.write(content)
    else: st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
if uploaded_files:
    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)

        if enable_planner:
            chapters = extract_chapters(text)
            st.subheader("📚 Chapters Detected")
            st.write(chapters)
            # AI-powered scheduling
            prompt = (
                f"Create a JSON study schedule assigning each chapter to dates between "
                f"{datetime.today().date().isoformat()} and {exam_date.isoformat()} "
                f"based on syllabus complexity '{complexity}'. "
                f"Output as a JSON list of {{\"Date\": \"YYYY-MM-DD\", \"Chapter\": \"...\"}}. "
                f"Chapters: {chapters}."
            )
            sched_text = call_gemini(prompt)
            try:
                sched = json.loads(sched_text)
                df_plan = pd.DataFrame(sched)
            except Exception:
                # Fallback to even split
                days_total = (exam_date - datetime.today().date()).days or 1
                interval = days_total // len(chapters)
                plan = []
                for i,chap in enumerate(chapters):
                    day = datetime.today().date() + timedelta(days=i*interval)
                    plan.append({'Date': day.isoformat(), 'Chapter': chap})
                df_plan = pd.DataFrame(plan)
            st.subheader("📅 AI-Generated Study Plan by Chapter")
            st.dataframe(df_plan)

        render_section("📌 Summary", generate_summary(text))
        render_section("📝 Quiz Questions", generate_questions(text))
        df_cards = generate_spaced_flashcards(text)
        st.subheader("🎴 Spaced Repetition Flashcards")
        st.dataframe(df_cards)
        st.subheader("✨ Smart Highlights")
        st.write(smart_highlight(text))
        st.subheader("📝 Live Practice Feedback")
        q = st.text_input(f"Question for {file.name}")
        a = st.text_input(f"Answer for {file.name}")
        if st.button(f"Get Feedback for {file.name}"):
            st.write(practice_test_feedback(q,a))
        if hubs_enabled and room_id:
            st.subheader("🤝 Collaborative Hubs")
            new_msg = st.text_input("Type a message...")
            if st.button("Send"):
                msgs = json.load(open(room_file))
                msgs.append({'name':nickname,'msg':new_msg})
                json.dump(msgs, open(room_file,'w'))
            st.write("**Chat:**")
            for m in json.load(open(room_file)): st.write(f"**{m['name']}:** {m['msg']}")
        days = st.session_state.get('days',0)
        if st.button("Log Study Session"):
            days+=1; st.session_state['days']=days
        st.write(f"Study sessions logged: {days}")
        if days>=3: st.success("🏅 Badge earned: 3-day streak!")
        if export_enabled:
            st.subheader("📤 Export & Integration")
            if st.button("Export Notes to PDF"):
                path = PDFExporter.to_pdf(text,file.name)
                st.write(f"Saved to {path}")
            if st.button("Export Flashcards to Anki"):
                path = AnkiExporter.to_anki(df_cards)
                st.write(f"Saved to {path}")
        if audio_enabled:
            st.subheader("🎧 Voice Notes & Audio Summaries")
            record_and_summarize()
        st.subheader("📊 Predictive Analytics")
        st.write(predictive_analytics(text))
else:
    st.info("Upload documents or images to start generating your study plan an
