import streamlit as st
import sqlite3
import json
import re
import time
import uuid
from io import BytesIO
from urllib.parse import urlencode
from threading import Thread
from PIL import Image
import pytesseract
import plotly.graph_objects as go
import altair as alt
import pandas as pd
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import streamlit_authenticator as stauth

# --- Configuration ---
APP_TITLE = "Vekkam"
THEME = {
    "primaryColor": "#4CAF50",
    "backgroundColor": "#F0F2F6",
    "secondaryBackgroundColor": "#FFFFFF",
    "textColor": "#262730",
    "font": "sans serif"
}
st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="📚")
st.markdown(f"<style>.stApp {{background-color: {THEME['backgroundColor']}; color: {THEME['textColor']};}}</style>", unsafe_allow_html=True)
st.markdown(f"<h1 style='text-align: center; color: {THEME['primaryColor']}'>Welcome to {APP_TITLE} — Your Study Companion</h1>", unsafe_allow_html=True)

# --- Database Setup (SQLite free & local) ---
conn = sqlite3.connect('vekkam.db', check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS users(
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT,
    hashed_pw TEXT,
    created INTEGER
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS decks(
    id TEXT PRIMARY KEY,
    name TEXT,
    user_id TEXT,
    rating INTEGER,
    created INTEGER
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS shares(
    deck_id TEXT,
    user_id TEXT,
    timestamp INTEGER
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS ai_cache(
    prompt TEXT,
    type TEXT,
    response TEXT,
    timestamp INTEGER
)
""")
conn.commit()

# --- Authentication Setup ---
users = {
    'user1': {'name': 'Alice', 'email': 'alice@example.com', 'password': 'password123'},
    'user2': {'name': 'Bob', 'email': 'bob@example.com', 'password': 'password456'}
}
hashed_passwords = stauth.Hasher([u['password'] for u in users.values()]).generate()
credentials = {
    'usernames': {u_id: {'name': data['name'], 'email': data['email'], 'password': hashed_passwords[i]} for i,(u_id,data) in enumerate(users.items())}
}
authenticator = stauth.Authenticate(credentials, 'vekkam_cookie', 'vekkam_signature', 30)
name, authentication_status, username = authenticator.login('Login', 'main')
if authentication_status is False:
    st.error('Username/password is incorrect')
    st.stop()
elif authentication_status is None:
    st.warning('Please enter your username and password')
    st.stop()
else:
    st.success(f'Welcome {name}!')

# --- Utility Functions ---
def get_transcript(url):
    vid = re.search(r'(?:v=|youtu\.be/)([\w-]+)', url)
    if not vid: return ''
    vid = vid.group(1)
    return "\n".join([t['text'] for t in YouTubeTranscriptApi.get_transcript(vid)])

def cache_ai(prompt, label, fn):
    row = c.execute("SELECT response FROM ai_cache WHERE prompt=? AND type=?", (prompt,label)).fetchone()
    if row:
        return row[0]
    resp = fn(prompt)
    c.execute("INSERT INTO ai_cache(prompt,type,response,timestamp) VALUES(?,?,?,?)", (prompt,label,resp,int(time.time())))
    conn.commit()
    return resp

# Simulated AI functions (replace with OpenAI/Gemini calls)
def get_mind_map(text):
    # stub: return nodes and edges
    return {'nodes':[{'id':'1','label':'Root'}],'edges':[]}

def generate_summary(text):
    return text[:500] + '...'

# --- Multipage Navigation ---
page = st.sidebar.selectbox('Menu', ['Home','My Decks','Analytics','Settings','Logout'])

def async_process(text, did, user):
    summary = cache_ai(text, 'sum', generate_summary)
    # store deck
    c.execute("INSERT INTO decks(id,name,user_id,rating,created) VALUES(?,?,?,?,?)", (did, text[:30], user, None, int(time.time())))
    conn.commit()

if page == 'Logout':
    authenticator.logout('Logout', 'sidebar')
    st.stop()

# --- Home Page ---
if page == 'Home':
    st.header('Create a New Deck')
    col1, col2 = st.columns([2,1])
    with col1:
        uploaded = st.file_uploader('File Upload', type=['pdf','docx','pptx','txt','jpg','png'])
        yt_url = st.text_input('Or YouTube URL')
    with col2:
        st.button('Dark Mode Toggle')  # placeholder for theming
    text = ''
    if yt_url:
        text = get_transcript(yt_url)
    elif uploaded:
        img = Image.open(uploaded)
        text = pytesseract.image_to_string(img) if uploaded.name.lower().endswith(('jpg','png')) else uploaded.getvalue().decode('utf-8')
    if text:
        did = uuid.uuid4().hex[:8]
        st.info('Processing...')
        thread = Thread(target=async_process, args=(text, did, username), daemon=True)
        thread.start()
        st.success(f'Deck {did} queued for processing.')

# --- My Decks Page ---
elif page == 'My Decks':
    st.header('Your Decks')
    df = pd.read_sql_query("SELECT * FROM decks WHERE user_id=?", conn, params=(username,))
    if df.empty:
        st.info('No decks created yet.')
    else:
        st.dataframe(df[['id','name','rating','created']])
        sel = st.selectbox('Select Deck', df['id'])
        if st.button('Display Details'):
            st.write(df[df['id']==sel].iloc[0].to_dict())

# --- Analytics Page ---
elif page == 'Analytics':
    st.header('Usage Analytics')
    df = pd.read_sql_query("SELECT rating, COUNT(*) as count FROM decks WHERE user_id=? GROUP BY rating", conn, params=(username,))
    if not df.empty:
        chart = alt.Chart(df).mark_bar().encode(x='rating:O', y='count:Q')
        st.altair_chart(chart, use_container_width=True)
        heatmap = pd.read_sql_query(
            "SELECT date(created, 'unixepoch') as day, COUNT(*) as cnt FROM decks GROUP BY day", conn)
        hm = alt.Chart(heatmap).mark_rect().encode(x='day:O', y='cnt:Q', color='cnt:Q')
        st.altair_chart(hm, use_container_width=True)
        if st.button('Export PDF Report'):
            records = df.to_dict('records')
            buf = BytesIO()
            doc = SimpleDocTemplate(buf)
            styles = getSampleStyleSheet()
            elems = [Paragraph('Analytics Report', styles['Title']), Spacer(1,12)]
            for r in records:
                elems.append(Paragraph(f"Rating {r['rating']}: {r['count']}", styles['Normal']))
            doc.build(elems)
            buf.seek(0)
            st.download_button('Download Report', buf, file_name='analytics.pdf')
    else:
        st.info('Not enough data for analytics yet.')

# --- Settings Page ---
elif page == 'Settings':
    st.header('Settings & Preferences')
    st.subheader('Account')
    st.write('Username:', username)
    if st.button('Delete Account'):
        c.execute("DELETE FROM users WHERE id=?", (username,))
        conn.commit()
        st.warning('Account deleted. Please refresh.')
    st.subheader('App Theme')
    theme = st.selectbox('Choose Theme', ['Light','Dark'])
    st.info('Theme setting saved.')

# --- The End ---
st.sidebar.markdown('---')
st.sidebar.write('Vekkam © 2025')
