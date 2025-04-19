import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import pytesseract
import fitz  # PyMuPDF
import docx
from pptx import Presentation
import re
import json
import io
import time
import requests
import sqlite3
from deep_translator import GoogleTranslator
import speech_recognition as sr
from gtts import gTTS

# --- Configuration ---
st.set_page_config(page_title="Vekkam", layout="wide")

# --- LLM Call (Mock or replace with real Gemini API) ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    # Replace with actual Gemini API integration
    return f"[Gemini]: {prompt[:100]}..."

# --- Text Extraction ---
def extract_text(file):
    name = file.name.lower()
    if name.endswith('.pdf'):
        doc = fitz.open(stream=file.read(), filetype='pdf')
        return "".join(page.get_text() for page in doc)
    elif name.endswith('.docx'):
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    elif name.endswith('.pptx'):
        return "\n".join(shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape, 'text'))
    elif name.endswith('.txt'):
        return io.StringIO(file.getvalue().decode('utf-8')).read()
    elif name.endswith(('.jpg', '.jpeg', '.png')):
        return pytesseract.image_to_string(Image.open(file))
    return ""

# --- Translation ---
def translate_text(text, target_lang='hi'):
    if target_lang == 'en':
        return text
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        return f"Translation error: {e}"

# --- Text-to-Speech and Voice Input ---
def record_voice_input():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.info("Listening... Speak now.")
        try:
            audio = recognizer.listen(source, timeout=5)
            return recognizer.recognize_google(audio)
        except Exception as e:
            return f"Error: {e}"

def play_tts(text, lang='en'):
    try:
        tts = gTTS(text=text, lang=lang)
        tmp = f"tts_{int(time.time())}.mp3"
        tts.save(tmp)
        return tmp
    except Exception as e:
        st.error(f"TTS Error: {e}")
        return None

# --- Mind Map Generation ---
def get_mind_map(text):
    prompt = f"Create JSON mind map from:\n{text[:500]}"
    resp = call_gemini(prompt, temperature=0.5)
    try:
        js = re.search(r"\{.*\}", resp, re.DOTALL).group(0)
        return json.loads(js)
    except:
        st.error("Mind map parsing failed.")
        return None

# --- Spaced Repetition Scheduler ---
def schedule_flashcards(user, cards):
    # Simple SM-2 stub
    return [dict(card=c, interval=1) for c in cards]

# --- Collaborative Hub ---
def start_collab_hub():
    st.info("Beta: Real-time collaborative hubs at akshara-collab.app")
    components.iframe("https://akshara-collab.app", height=600)

# --- Offline Cache ---
def save_offline_cache(items, db_path='cache.db'):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS flashcards(q TEXT, a TEXT)")
    for c in items:
        cur.execute("INSERT INTO flashcards VALUES(?,?)", (c['q'], c['a']))
    conn.commit(); conn.close()
    return "Offline cache saved."

# --- AI Tutor Chatbot ---
def chatbot_response(query):
    return call_gemini(f"Tutor question: {query}")

def show_chatbot_ui():
    st.subheader("AI Tutor Chatbot")
    mode = st.radio("Input Mode", ['Text', 'Voice'])
    if mode == 'Text':
        q = st.text_input("Your question")
    else:
        if st.button("Record Voice"): q = record_voice_input()
        else: q = None
    if q:
        ans = chatbot_response(q)
        st.write(ans)
        audio = play_tts(ans)
        if audio: st.audio(audio)

# --- Gamification ---
def update_user_xp(user, action):
    xp = {'quiz':10,'review':5}.get(action,0)
    return f"User {user} gained {xp} XP"

def show_badges(user):
    st.success(f"Congrats {user}, you've earned the Flashcard Hero badge!")

# --- Institutional Dashboard ---
def show_institutional_dashboard():
    st.subheader("Institution Dashboard")
    st.line_chart([20,40,60,80])

# --- Image Compression ---
def compress_images(f):
    img = Image.open(f)
    out = 'compressed_'+f.name
    img.save(out, optimize=True, quality=40)
    return out

# --- LMS Integration ---
def import_from_google_classroom():
    return "(Mock) Imported from Google Classroom"

# --- Sponsor Impact Zones ---
def get_impact_zone_sponsor(region):
    return {'Northeast India':'McKinsey','Kibera':'Google.org'}.get(region, 'Local NGO')

# --- Summary, Q, Flashcards, etc. ---
def generate_summary(text): return call_gemini(f"Summarize for exam: {text[:300]}")
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions: {text[:300]}")
def generate_flashcards(text): return call_gemini(f"Create flashcards Q&A: {text[:300]}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics: {text[:300]}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms: {text[:300]}")
def generate_cheatsheet(text): return call_gemini(f"Create cheat sheet: {text[:300]}")
def generate_highlights(text): return call_gemini(f"Key facts and highlights: {text[:300]}")

def render_section(title, content):
    st.subheader(title)
    if content.strip().startswith('<'):
        components.html(content)
    else:
        st.write(content)

# --- Main App ---
menu = st.sidebar.selectbox("Choose Feature", [
    "Document Analyzer", "Flashcard Scheduler", "Collaborative Hub", "Offline Sync", "Translator",
    "AI Tutor Chatbot", "Gamification", "Institution Dashboard", "Image Compression", "LMS Integration", "Sponsor Zone"
])

if menu == "Document Analyzer":
    files = st.file_uploader("Upload files", type=['pdf','docx','pptx','txt','jpg','png'], accept_multiple_files=True)
    if files:
        for f in files:
            st.markdown(f"### {f.name}")
            text = extract_text(f)
            mind = get_mind_map(text)
            if mind: st.write(mind)
            render_section("Summary", generate_summary(text))
            render_section("Questions", generate_questions(text))
            with st.expander("Flashcards"): render_section("Flashcards", generate_flashcards(text))
            with st.expander("Mnemonics"): render_section("Mnemonics", generate_mnemonics(text))
            with st.expander("Key Terms"): render_section("Key Terms", generate_key_terms(text))
            with st.expander("Cheat Sheet"): render_section("Cheat Sheet", generate_cheatsheet(text))
            with st.expander("Highlights"): render_section("Highlights", generate_highlights(text))

elif menu == "Flashcard Scheduler":
    cards = [{'q':'What is AI?','a':'Artificial Intelligence'}]
    st.write(schedule_flashcards('user1', cards))

elif menu == "Collaborative Hub":
    start_collab_hub()

elif menu == "Offline Sync":
    cards = [{'q':'Define ML','a':'Machine Learning'}]
    st.write(save_offline_cache(cards))

elif menu == "Translator":
    txt = st.text_input("Text to translate")
    tgt = st.selectbox("Language", ['hi','es','fr','en'])
    if txt: st.write(translate_text(txt, tgt))

elif menu == "AI Tutor Chatbot":
    show_chatbot_ui()

elif menu == "Gamification":
    st.write(update_user_xp('user1','quiz'))
    show_badges('user1')

elif menu == "Institution Dashboard":
    show_institutional_dashboard()

elif menu == "Image Compression":
    img = st.file_uploader("Image", type=['png','jpg','jpeg'])
    if img: st.image(compress_images(img))

elif menu == "LMS Integration":
    st.write(import_from_google_classroom())

elif menu == "Sponsor Zone":
    reg = st.selectbox("Region", ['Northeast India','Kibera','Other'])
    st.write(f"Sponsor: {get_impact_zone_sponsor(reg)}")

# Note: For mass deployment, add Dockerfile and requirements.txt as needed (not shown here).
