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
import threading

# Calendar & OAuth imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Caching imports
import redis
import hashlib

# --- Configuration & Secrets ---
st.set_page_config(page_title="Vekkam", layout="wide")

# Initialize Redis cache (replace with your Redis URL)
REDIS_URL = st.secrets.get('redis_url', 'redis://localhost:6379')
cache = redis.from_url(REDIS_URL)
CACHE_TTL = 3600  # seconds

SCOPES = ['https://www.googleapis.com/auth/calendar.events']
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_KEY = 'google_calendar_token'

# --- Helper Functions ---

def cache_get(key):
    val = cache.get(key)
    return json.loads(val) if val else None

def cache_set(key, value):
    cache.setex(key, CACHE_TTL, json.dumps(value))

# OAuth: stores credentials in session_state
if 'credentials' not in st.session_state:
    st.session_state['credentials'] = None

# Initialize Google Calendar service
def get_calendar_service():
    creds = st.session_state['credentials']
    if not creds:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        st.markdown(f"[Authorize with Google Calendar]({auth_url})")
        code = st.text_input('Enter the authorization code:')
        if code:
            flow.fetch_token(code=code)
            creds = flow.credentials
            st.session_state['credentials'] = creds
    service = build('calendar', 'v3', credentials=st.session_state['credentials'])
    return service

# Schedule events in calendar
def schedule_study_sessions(plan):
    service = get_calendar_service()
    for session in plan['sessions']:
        event = {
            'summary': session['topic'],
            'start': {'dateTime': session['start'], 'timeZone': 'Asia/Kolkata'},
            'end': {'dateTime': session['end'], 'timeZone': 'Asia/Kolkata'},
        }
        service.events().insert(calendarId='primary', body=event).execute()

# Progress bar wrapper for long tasks
def run_with_progress(func, *args, **kwargs):
    progress = st.progress(0)
    result = [None]
    def target():
        result[0] = func(*args, **kwargs)
    thread = threading.Thread(target=target)
    thread.start()
    while thread.is_alive():
        time.sleep(0.5)
        progress.progress(min(progress._value + 5, 100))
    progress.empty()
    return result[0]

# --- UI Styles ---
components.html("""
<style>
body { font-family: 'Segoe UI', sans-serif; }
.stButton button { border-radius: 12px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
.stTextInput>div>div>input { padding: 8px; border-radius: 6px; }
@media (max-width: 600px) {
  .main .block-container { padding: 1rem; }
}
</style>
""", height=0)

# --- App Layout ---
st.markdown("""
<div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
  <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
</div>
""", unsafe_allow_html=True)
st.title("Vekkam - Study Smarter, Not Harder")
st.info("Authenticate with Google to sync study sessions to your Calendar and enjoy cached AI-generated content for speed and cost efficiency.")

# --- Inputs ---
# Guide Book & Syllabus
st.header("📚 Guide-Book & Syllabus Setup")
book_input = st.text_input("Enter Guide-Book Title or ISBN for lookup:")
syllabus_input = st.text_area("Paste or enter your exam syllabus (one topic per line):")

# Cached book lookup
def fetch_book_data(query):
    key = hashlib.sha256(query.encode()).hexdigest()
    cached = cache_get(key)
    if cached:
        return cached
    res = requests.get('https://www.googleapis.com/books/v1/volumes', params={'q': query, 'maxResults':1})
    data = res.json().get('items', [None])[0]
    cache_set(key, data)
    return data

book_data = fetch_book_data(book_input) if book_input else None
if book_data:
    info = book_data['volumeInfo']
    st.subheader(info.get('title', 'Title not available'))
    st.write(f"**Authors:** {', '.join(info.get('authors', []))}")
    if info.get('description'):
        st.write(info['description'])

# Parse syllabus
syllabus_json = None
if syllabus_input:
    topics = [line.strip() for line in syllabus_input.splitlines() if line.strip()]
    syllabus_json = {'topics': topics}
    st.write("**Structured Syllabus:**")
    st.json(syllabus_json)

# --- Core AI Calls with caching ---

def call_cached_gemini(prompt):
    key = hashlib.sha256(prompt.encode()).hexdigest()
    cached = cache_get(key)
    if cached:
        return cached
    response = call_gemini(prompt)
    cache_set(key, response)
    return response

# Study Plan Generation
if book_data and syllabus_json:
    if st.button("Generate 6-Hour Study Plan"):
        plan = run_with_progress(lambda: json.loads(call_cached_gemini(
            f"Generate a 6-hour study plan from Book: {json.dumps(book_data['volumeInfo'])} and Syllabus: {json.dumps(syllabus_json)}"
        )))
        st.subheader("🗓️ Your 6-Hour Study Plan")
        st.json(plan)
        if st.button("Sync to Google Calendar"):
            schedule_study_sessions(plan)
            st.success("Study sessions added to your Google Calendar!")

# File Upload for supplemental materials
st.header("📄 Upload Study Materials")
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)",
    type=["pdf","docx","pptx","txt","jpg","jpeg","png"], accept_multiple_files=True
)

# Processing uploads
if uploaded_files:
    loader = st.empty()
    loader.components.html(loader_html, height=400)
    for file in uploaded_files:
        text = extract_text(file)
        # Mind map
        mind_map = run_with_progress(lambda: get_mind_map(text))
        if mind_map:
            plot_mind_map(mind_map['nodes'], mind_map['edges'])
        # Other aids
        for title, fn in [
            ("📌 Summary", lambda t=text: generate_summary(t)),
            ("📝 Quiz Questions", lambda t=text: generate_questions(t)),
            ("🃏 Flashcards", lambda t=text: generate_flashcards(t)),
            ("🔤 Mnemonics", lambda t=text: generate_mnemonics(t)),
            ("🔑 Key Terms", lambda t=text: generate_key_terms(t)),
            ("📋 Cheat Sheet", lambda t=text: generate_cheatsheet(t)),
            ("⭐ Highlights", lambda t=text: generate_highlights(t))
        ]:
            with st.expander(title):
                content = run_with_progress(fn)
                render_section(title, content)
    loader.empty()
else:
    st.info("Input your guide-book & syllabus or upload materials to begin.")
