import streamlit as st
import requests
from urllib.parse import urlencode

# --- CONFIGURATION from st.secrets.toml ---
CLIENT_ID     = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI  = st.secrets["google"]["redirect_uri"]
SCOPES        = ["openid", "email", "profile"]

# Verify these values match exactly what’s in Google Cloud:
st.write("🔑 Client ID:", CLIENT_ID)
st.write("🔒 Redirect URI:", REDIRECT_URI)

# --- SESSION STATE INIT ---
for key in ("token", "user"):
    if key not in st.session_state:
        st.session_state[key] = None

def login_ui():
    st.title("Vekkam 📘 — Login")
    # Build auth URL (v2 endpoint)
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(params)
    )
    st.markdown(f"[👉 Login with Google]({auth_url})")
    
    code = st.text_input("Paste authorization code here:")
    if st.button("Authenticate") and code:
        token_endpoint = "https://oauth2.googleapis.com/token"
        payload = {
            "code": code.strip(),
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        resp = requests.post(token_endpoint, data=payload)
        if resp.status_code != 200:
            st.error(
                f"🚨 Token exchange failed ({resp.status_code}): "
                f"{resp.json().get('error_description', resp.text)}"
            )
            return
        st.session_state.token = resp.json()  # contains access_token, refresh_token
        # Fetch userprofile
        userinfo = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {st.session_state.token['access_token']}"},
        )
        if userinfo.status_code != 200:
            st.error("🚨 Failed to fetch user info.")
            return
        st.session_state.user = userinfo.json()

# --- MAIN APP ---
if not st.session_state.user:
    login_ui()
else:
    user = st.session_state.user
    st.sidebar.image(user.get("picture", ""), width=48)
    st.sidebar.write(user.get("email", ""))
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.experimental_rerun()
    # Your actual app code here...
    st.write(f"👋 Welcome, {user.get('name', '')}!")
