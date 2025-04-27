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
from google_auth_oauthlib.flow import InstalledAppFlow

# Calendar & OAuth imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Caching imports
import redis
import hashlib

# --- Configuration & Secrets ---
st.set_page_config(page_title="Vekkam", layout="wide")

# Initialize Redis cache (replace with your Redis URL)
REDIS_URL = st.secrets.get('redis_url', 'redis://localhost:6379')
cache = redis.from_url(REDIS_URL)
CACHE_TTL = 3600  # seconds

# OAuth & Google API scopes
SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/calendar.events'
]

# CLIENT_CONFIG should be defined in Streamlit secrets as a dict matching OAuth2 client_secrets.json
CLIENT_CONFIG = st.secrets["oauth"]  # e.g. {"web": {...}}
TOKEN_KEY = 'google_credentials'
USER_KEY = 'google_user'

# --- Helper Functions ---

def cache_get(key):
    val = cache.get(key)
    return json.loads(val) if val else None

def cache_set(key, value):
    cache.setex(key, CACHE_TTL, json.dumps(value))

# --- OAuth / Google Login ---
if USER_KEY not in st.session_state:
    st.session_state[USER_KEY] = None

# Perform OAuth flow for login and calendar
def do_google_login():
    # Rebuild the client_config that Google expects
    client_config = {
        "installed": {
            "client_id": st.secrets["oauth"]["installed_client_id"],
            "client_secret": st.secrets["oauth"]["installed_client_secret"],
            "auth_uri": st.secrets["oauth"]["auth_uri"],
            "token_uri": st.secrets["oauth"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["oauth"]["auth_provider_x509_cert_url"],
            # redirect_uris isn’t needed for console flow
        }
    }

    # This will open the browser, prompt consent, then ask you to paste the code back
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_console()  
    # run_console() handles the code exchange using your Desktop client

    # Save creds & user info into session
    st.session_state[TOKEN_KEY] = creds_to_dict(creds)
    idinfo = id_token.verify_oauth2_token(
        creds.id_token, google_requests.Request(), st.secrets["google_client_id"]
    )
    st.session_state[USER_KEY] = {
        "email": idinfo["email"],
        "name":  idinfo["name"],
        "picture": idinfo.get("picture")
    }

# Convert credentials to dict and back
def creds_to_dict(creds):
    return {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }

def get_credentials():
    data = st.session_state.get(TOKEN_KEY)
    if not data:
        return None
    return Credentials(
        token=data['token'],
        refresh_token=data.get('refresh_token'),
        token_uri=data['token_uri'],
        client_id=data['client_id'],
        client_secret=data['client_secret'],
        scopes=data['scopes']
    )

# Google Calendar service
def get_calendar_service():
    creds = get_credentials()
    if not creds:
        do_google_login()
        return None
    return build('calendar', 'v3', credentials=creds)

# Schedule events in calendar
def schedule_study_sessions(plan):
    service = get_calendar_service()
    if not service:
        st.warning("Please log in first.")
        return
    for session in plan.get('sessions', []):
        event = {
            'summary': session['topic'],
            'start': {'dateTime': session['start'], 'timeZone': 'Asia/Kolkata'},
            'end': {'dateTime': session['end'], 'timeZone': 'Asia/Kolkata'},
        }
        service.events().insert(calendarId='primary', body=event).execute()
    st.success("Study sessions added to your Google Calendar!")

# Background threading & progress bar
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
if not st.session_state[USER_KEY]:
    st.title("Welcome to Vekkam")
    st.write("Authenticate to personalize your experience.")
    do_google_login()
    st.stop()

# User is logged in
user = st.session_state[USER_KEY]
st.sidebar.image(user.get('picture'), width=60)
st.sidebar.write(f"Logged in as {user.get('name')} \n({user.get('email')})")
st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())

st.title("Vekkam - Study Smarter, Not Harder")
st.info("Sync study sessions to your Google Calendar and enjoy cached AI-generated content for speed and cost efficiency.")

# --- Inputs ---
# Guide Book & Syllabus
st.header("📚 Guide-Book & Syllabus Setup")
book_input = st.text_input("Enter Guide-Book Title or ISBN for lookup:")
syllabus_input = st.text_area("Paste or enter your exam syllabus (one topic per line):")
