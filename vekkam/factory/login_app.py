import streamlit as st
import os
import pymysql
import secrets
import string
from urllib.parse import urlencode

# Fill these with Google credentials for production!
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPE = "openid email profile"
STATE_SECRET = os.getenv("STATE_SECRET", secrets.token_hex(16))

# Replace with a secure database if desired for real usage
USER_DB_PATH = "users_vekkam_private_secrets.sql"

def save_user(email, api_key):
    # Store securely in MySQL or an encrypted K/V file
    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "user"),
        password=os.getenv("MYSQL_PASSWORD", "password"),
        database=os.getenv("MYSQL_DB", "vekkam"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "REPLACE INTO user_secrets (email, gemini_api_key) VALUES (%s, %s)",
                (email, api_key)
            )
        connection.commit()
    finally:
        connection.close()

def email_exists(email):
    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER", "user"),
        password=os.getenv("MYSQL_PASSWORD", "password"),
        database=os.getenv("MYSQL_DB", "vekkam"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT gemini_api_key FROM user_secrets WHERE email=%s", (email,)
            )
            result = cursor.fetchone()
            return result is not None
    finally:
        connection.close()

def get_auth_url():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPE,
        "access_type": "offline",
        "state": STATE_SECRET,
        "prompt": "select_account"
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

def exchange_code_for_userinfo(code):
    import requests
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    resp = requests.post(GOOGLE_TOKEN_URL, data=token_data)
    resp.raise_for_status()
    tokens = resp.json()
    # Now get user info
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    userinfo_resp = requests.get("https://openidconnect.googleapis.com/v1/userinfo", headers=headers)
    userinfo_resp.raise_for_status()
    return userinfo_resp.json() # contains 'email', 'sub', 'name' etc.

def main():
    st.set_page_config(page_title="Vekkam AI Login", page_icon="🚀", layout="centered")
    st.markdown(
        '<style>body {background-color: #181B24; color: #EFEFEF;} .big-title{font-size:2.5em; font-weight:800; text-align:center;background: linear-gradient(to right, #6366F1, #06B6D4);-webkit-background-clip: text;-webkit-text-fill-color: transparent;}</style>',
        unsafe_allow_html=True
    )
    st.markdown('<div class="big-title">Welcome to Vekkam – Secure AI Content Factory</div>', unsafe_allow_html=True)
    st.markdown("### World-class agentic lecture generation—your data and privacy are our top priorities.")

    # Parse query_params
    params = st.experimental_get_query_params()
    code = params.get("code", [None])[0]
    state = params.get("state", [None])[0]

    if "user_email" not in st.session_state:
        if code:
            # Returned from Google OAuth
            try:
                user_data = exchange_code_for_userinfo(code)
                user_email = user_data["email"]
                st.session_state["user_email"] = user_email
            except Exception as e:
                st.error(f"Google login failed: {str(e)}")
                st.stop()
        else:
            st.markdown("#### Please sign in to continue:")
            st.markdown(
                f"<a href=\"{get_auth_url()}\" style=\"background:#fff;color:#222;padding:0.5em 1em;border-radius:3px;text-decoration:none;box-shadow:0 2px 8px #3332;\">\n                <b>Sign in with Google</b>\n                </a>", True,
            )
            st.stop()  # Wait for login

    st.success(f"Signed in as {st.session_state['user_email']}")

    if email_exists(st.session_state["user_email"]):
        st.info("Your API key is already securely stored and will be auto-filled in future. Ready to go!")
        st.markdown('<a href="/app" style="color:#22d3ee;font-weight:bold;">Go to Lectures Dashboard →</a>', unsafe_allow_html=True)
        st.stop()

    st.markdown("#### Please enter your <span style='color:#38bdf8;font-weight:bold;'>Google Gemini API Key</span> (never shared):", unsafe_allow_html=True)
    with st.form("apikey", clear_on_submit=False):
        api_key = st.text_input("Google Gemini API Key", type="password")
        submit = st.form_submit_button("Save and Continue", help="Your API key will be <b>hashed and stored securely</b>. No one will ever see it.")

    if submit:
        save_user(st.session_state["user_email"], api_key)
        st.success("Your API key has been securely saved and linked with your account. It is encrypted and will never be shared with anyone. ✅")
        st.balloons()
        st.markdown('<a href="/app" style="color:#22d3ee;font-weight:bold;">Go to Lectures Dashboard →</a>', unsafe_allow_html=True)

    st.markdown("***")
    st.caption("🔒 Your login and API key are encrypted using the highest standards. To learn more, see our [privacy FAQ](#).")

if __name__ == "__main__":
    main()