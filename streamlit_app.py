import streamlit as st
import requests
import tempfile
from urllib.parse import urlencode
from PyPDF2 import PdfReader
from io import StringIO
from PIL import Image
import pytesseract
import igraph as ig
import plotly.graph_objects as go
import re

# --- Configuration (from st.secrets) ---
CLIENT_ID     = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI  = st.secrets["google"]["redirect_uri"]
SCOPES        = ["openid", "email", "profile"]

GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
CSE_API_KEY    = st.secrets["google_search"]["api_key"]
CSE_ID         = st.secrets["google_search"]["cse_id"]
CACHE_TTL      = 3600

# --- Initialize Session State ---
for key in ("token", "user"):
    if key not in st.session_state:
        st.session_state[key] = None

def login_ui():
    st.title("Vekkam 📘 — Login")
    # show redirect URI so you can confirm it exactly matches your Google Console
    st.write("Redirect URI (must match in Google Cloud):", REDIRECT_URI)
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    st.markdown(f"[👉 Login with Google]({auth_url})")
    code = st.text_input("Paste the authorization code here:")
    if st.button("Authenticate") and code:
        exchange_token(code)

def exchange_token(code: str):
    """Exchange auth code for tokens; handle errors."""
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    token_res = requests.post(
        "https://oauth2.googleapis.com/token", data=data
    ).json()
    if "error" in token_res:
        st.error(f"⚠️ Token exchange failed: {token_res.get('error_description', token_res['error'])}")
        return
    st.session_state.token = token_res
    # fetch userinfo
    userinfo = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token_res['access_token']}"},
    ).json()
    st.session_state.user = userinfo

def call_gemini(prompt, temp=0.7, max_tokens=2048):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent"
        f"?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [ { "parts": [ { "text": prompt } ] } ],
        "generationConfig": { "temperature": temp, "maxOutputTokens": max_tokens }
    }
    res = requests.post(url, json=payload).json()
    return res["candidates"][0]["content"]["parts"][0]["text"]

def extract_pages_from_url(pdf_url: str):
    resp = requests.get(pdf_url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(resp.content)
    tmp.flush()
    reader = PdfReader(tmp.name)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_pages_from_file(file):
    reader = PdfReader(file)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_text(file):
    ext = file.name.lower().split(".")[-1]
    if ext == "pdf":
        return "\n".join(extract_pages_from_file(file).values())
    if ext in ("jpg", "jpeg", "png"):
        return pytesseract.image_to_string(Image.open(file))
    # txt or other
    return StringIO(file.getvalue().decode()).read()

def fetch_pdf_url(title, author, edition):
    q = " ".join(filter(None, [title, author, edition]))
    params = {
        "key": CSE_API_KEY,
        "cx": CSE_ID,
        "q": q,
        "fileType": "pdf",
        "num": 1,
    }
    items = requests.get("https://www.googleapis.com/customsearch/v1", params=params)\
                   .json().get("items", [])
    return items[0]["link"] if items else None

def find_concept_pages(pages, concept):
    cl = concept.lower()
    return {p: t for p, t in pages.items() if cl in (t or "").lower()}

def ask_concept(pages, concept):
    found = find_concept_pages(pages, concept)
    if not found:
        return f"Couldn’t find any pages containing the concept '{concept}'."
    combined = "\n---\n".join(f"Page {p}: {t}" for p, t in found.items())
    prompt = f"Concept: '{concept}'.\n\nSections:\n{combined}\n\nExplain with context and examples."
    return call_gemini(prompt)

# Learning-aid wrappers
def generate_summary(text):          return call_gemini(f"Summarize for exam, list formulae:\n\n{text}")
def generate_questions(text):        return call_gemini(f"Generate 15 quiz questions:\n\n{text}")
def generate_flashcards(text):       return call_gemini(f"Create flashcards (Q&A):\n\n{text}")
def generate_mnemonics(text):        return call_gemini(f"Generate mnemonics:\n\n{text}")
def generate_key_terms(text):        return call_gemini(f"List key terms with definitions:\n\n{text}")
def generate_cheatsheet(text):       return call_gemini(f"Create a cheat sheet:\n\n{text}")
def generate_highlights(text):       return call_gemini(f"List key facts and highlights:\n\n{text}")
def generate_critical_points(text):  return call_gemini(f"Detailed but concise run-through:\n\n{text}")
def plot_mind_map(text):             st.write("[Mind map visualization placeholder]")

# --- Main UI Flow ---
if not st.session_state.user:
    login_ui()

else:
    user = st.session_state.user
    st.sidebar.image(user.get("picture", ""), width=48)
    st.sidebar.write(user.get("email", ""))
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

    choice = st.sidebar.selectbox("Feature", ["Guide Book Chat", "Document Q&A"])

    if choice == "Guide Book Chat":
        st.header("📚 Guide Book Chat")
        title   = st.text_input("Title")
        author  = st.text_input("Author")
        edition = st.text_input("Edition")
        concept = st.text_input("Ask about concept")
        if st.button("Chat") and concept:
            url = fetch_pdf_url(title, author, edition)
            if not url:
                st.error("No PDF found for that query.")
            else:
                pages = extract_pages_from_url(url)
                answer = ask_concept(pages, concept)
                st.markdown(answer)

    else:
        st.header("📝 Document Q&A")
        uploaded = st.file_uploader(
            "Upload PDF / Image / TXT", type=["pdf","jpg","jpeg","png","txt"]
        )
        if uploaded:
            text = extract_text(uploaded)
            st.subheader("Learning Aids")
            tool = st.selectbox("Pick a function", [
                "Summary", "Questions", "Flashcards", "Mnemonics",
                "Key Terms", "Cheat Sheet", "Highlights",
                "Critical Points", "Concept Chat", "Mind Map"
            ])
            if st.button("Run"):
                if tool == "Summary":        result = generate_summary(text)
                elif tool == "Questions":    result = generate_questions(text)
                elif tool == "Flashcards":   result = generate_flashcards(text)
                elif tool == "Mnemonics":    result = generate_mnemonics(text)
                elif tool == "Key Terms":    result = generate_key_terms(text)
                elif tool == "Cheat Sheet":  result = generate_cheatsheet(text)
                elif tool == "Highlights":   result = generate_highlights(text)
                elif tool == "Critical Points":
                    result = generate_critical_points(text)
                elif tool == "Concept Chat":
                    c = st.text_input("Concept to explain")
                    result = ask_concept(extract_pages_from_file(uploaded), c) if c else "Enter a concept above."
                else:  # Mind Map
                    result = call_gemini(f"Create JSON mind map from text:\n\n{text}")
                st.markdown(result)
