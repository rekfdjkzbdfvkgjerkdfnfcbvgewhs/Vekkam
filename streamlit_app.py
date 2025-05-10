import streamlit as st
import requests
from urllib.parse import urlencode
from PyPDF2 import PdfReader
from io import StringIO
from PIL import Image
import pytesseract

# --- CONFIGURATION from st.secrets ---
CLIENT_ID     = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI  = st.secrets["google"]["redirect_uri"]
SCOPES        = ["openid", "email", "profile"]

# (Other API keys...)
GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
CSE_API_KEY    = st.secrets["google_search"]["api_key"]
CSE_ID         = st.secrets["google_search"]["cse_id"]

# --- SESSION STATE INITIALIZATION ---
for key in ("token", "user"):
    if key not in st.session_state:
        st.session_state[key] = None

# --- LOGIN UI ---
def login_ui():
    st.title("Vekkam 📘 — Login")
    # Print the redirect URI for exact matching
    st.write("Redirect URI:", REDIRECT_URI)
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    st.markdown(f"[Login with Google]({auth_url})")

    code = st.text_input("Paste authorization code here:")
    if st.button("Authenticate") and code:
        token_endpoint = "https://oauth2.googleapis.com/token"
        payload = {
            "code": code.strip(),
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        res = requests.post(token_endpoint, data=payload)
        if res.status_code != 200:
            st.error(f"Token exchange failed ({res.status_code}): {res.text}")
            return
        st.session_state.token = res.json()

        # Fetch user info
        usr = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {st.session_state.token['access_token']}"}
        )
        if usr.status_code != 200:
            st.error("Failed to fetch user info.")
            return
        st.session_state.user = usr.json()

# --- MAIN APP ---
if not st.session_state.user:
    login_ui()
else:
    user = st.session_state.user
    st.sidebar.image(user.get("picture", ""), width=50)
    st.sidebar.write(user.get("email", ""))
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()

    tab = st.sidebar.selectbox("Feature", ["Guide Book Chat", "Document Q&A"])
    if tab == "Guide Book Chat":
        st.header("Guide Book Chat")
        title   = st.text_input("Title")
        author  = st.text_input("Author")
        edition = st.text_input("Edition")
        concept = st.text_input("Ask about concept:")
        if st.button("Chat") and concept:
            # ... your existing fetch_pdf_url, extract_pages_from_url, ask_concept ...
            st.write("Answer would go here.")
    else:
        st.header("Document Q&A")
        uploaded = st.file_uploader("Upload PDF/Image/TXT", type=["pdf", "jpg", "png", "txt"])
        if uploaded:
            # ... your existing extract_text and learning‐aid functions ...
            st.write("Learning aids would go here.")
