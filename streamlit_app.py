import streamlit as st
import requests
import tempfile
from urllib.parse import urlencode
from PyPDF2 import PdfReader
import fitz
from io import StringIO
from PIL import Image
import pytesseract
import json
import igraph as ig
import plotly.graph_objects as go
import re

# --- Configuration using st.secrets ---
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]
SCOPES = ["openid", "email", "profile"]
GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
CSE_API_KEY = st.secrets["google_search"]["api_key"]
CSE_ID = st.secrets["google_search"]["cse_id"]
CACHE_TTL = 3600

# --- Session State ---
for key in ['token','user','plan']:
    if key not in st.session_state:
        st.session_state[key] = None

# --- OAuth Login ---
def login_ui():
    st.title("Vekkam 📘")
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent'
    }
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    st.markdown(f"[Login with Google]({auth_url})")
    code = st.text_input("Authorization code:")
    if st.button("Authenticate") and code:
        data = {
            'code': code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        res = requests.post('https://oauth2.googleapis.com/token', data=data).json()
        st.session_state['token'] = res
        userinfo = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f"Bearer {res['access_token']}"}
        ).json()
        st.session_state['user'] = userinfo

# --- Gemini Call ---
def call_gemini(prompt, temp=0.7, max_tokens=2048):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':temp,'maxOutputTokens':max_tokens}}
    res = requests.post(url, json=payload).json()
    return res['candidates'][0]['content']['parts'][0]['text']

# --- PDF Extraction ---
def extract_pages_from_url(pdf_url):
    resp = requests.get(pdf_url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    tmp.write(resp.content); tmp.flush()
    reader = PdfReader(tmp.name)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_pages_from_file(file):
    reader = PdfReader(file)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_text(file):
    ext = file.name.lower().split('.')[-1]
    if ext == 'pdf': return "\n".join(extract_pages_from_file(file).values())
    if ext in ['jpg','jpeg','png']: return pytesseract.image_to_string(Image.open(file))
    return StringIO(file.getvalue().decode()).read()

# --- Guide Book Search ---
def fetch_pdf_url(title, author, edition):
    q = ' '.join(filter(None, [title, author, edition]))
    params = {'key': CSE_API_KEY, 'cx': CSE_ID, 'q': q, 'fileType': 'pdf', 'num': 1}
    items = requests.get('https://www.googleapis.com/customsearch/v1', params=params).json().get('items', [])
    return items[0]['link'] if items else None

# --- Concept Q&A ---
def find_concept_pages(pages, concept):
    cl = concept.lower()
    return {p: t for p, t in pages.items() if cl in (t or '').lower()}

def ask_concept(pages, concept):
    found = find_concept_pages(pages, concept)
    if not found: return f"Couldn’t find '{concept}'."
    combined = "\n---\n".join(f"Page {p}: {t}" for p, t in found.items())
    prompt = f"Concept: '{concept}'. Sections:\n{combined}\nExplain with context and examples."
    return call_gemini(prompt)

# --- Learning Aids Functions ---
def generate_summary(text): return call_gemini(f"Summarize for exam, list formulae:\n{text}")
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions:\n{text}")
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A):\n{text}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics:\n{text}")
def generate_key_terms(text): return call_gemini(f"List key terms with definitions:\n{text}")
def generate_cheatsheet(text): return call_gemini(f"Create a cheat sheet:\n{text}")
def generate_highlights(text): return call_gemini(f"List key facts and highlights:\n{text}")
def generate_critical_points(text): return call_gemini(f"Detailed but concise run-through:\n{text}")

def plot_mind_map(text):
    # simple placeholder
    st.write("[Mind map visualization]")

# --- UI ---
if not st.session_state['user']:
    login_ui()
else:
    user = st.session_state['user']
    st.sidebar.image(user.get('picture',''), width=50)
    st.sidebar.write(user.get('email',''))
    if st.sidebar.button('Logout'):
        st.session_state.clear()
    tab = st.sidebar.selectbox('Feature', ['Guide Book Chat', 'Document Q&A'])
    if tab == 'Guide Book Chat':
        st.header('Guide Book Chat')
        t = st.text_input('Title'); a = st.text_input('Author'); e = st.text_input('Edition')
        concept = st.text_input('Ask about concept:')
        if st.button('Chat') and concept:
            url = fetch_pdf_url(t, a, e)
            if not url: st.error('PDF not found')
            else:
                pages = extract_pages_from_url(url)
                ans = ask_concept(pages, concept); st.write(ans)
    else:
        st.header('Document Q&A')
        f = st.file_uploader('Upload PDF/Image/TXT', type=['pdf', 'jpg', 'png', 'txt'])
        if f:
            text = extract_text(f)
            st.subheader('Learning Aids')
            render = st.selectbox('Pick a function', [
                'Summary', 'Questions', 'Flashcards', 'Mnemonics',
                'Key Terms', 'Cheat Sheet', 'Highlights',
                'Critical Points', 'Concept Chat', 'Mind Map'
            ])
            if st.button('Run'):
                if render == 'Summary': res = generate_summary(text)
                if render == 'Questions': res = generate_questions(text)
                if render == 'Flashcards': res = generate_flashcards(text)
                if render == 'Mnemonics': res = generate_mnemonics(text)
                if render == 'Key Terms': res = generate_key_terms(text)
                if render == 'Cheat Sheet': res = generate_cheatsheet(text)
                if render == 'Highlights': res = generate_highlights(text)
                if render == 'Critical Points': res = generate_critical_points(text)
                if render == 'Concept Chat':
                    concept = st.text_input('Concept to explain:')
                    if concept: res = ask_concept(extract_pages_from_file(f), concept)
                    else: res = 'Enter concept.'
                if render == 'Mind Map': res = call_gemini(f"Create JSON mind map from text:\n{text}")
                st.write(res)
