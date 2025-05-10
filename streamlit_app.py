import streamlit as st
from datetime import datetime
from streamlit_lottie import st_lottie
from streamlit_autorefresh import st_autorefresh
import json

# ---------------------------
# Page configuration
# ---------------------------
st.set_page_config(
    page_title="Vekkam Premiere Countdown",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------
# Auto-refresh every second
# ---------------------------
st_autorefresh(interval=1000, key="countdown_refresh")

# ---------------------------
# Custom CSS styling
# ---------------------------
st.markdown("""
<style>
body {
    background: radial-gradient(circle at center, #000000, #141414);
    color: #FFFFFF;
}
h1, h2, h3, h4, h5 {
    text-align: center;
    color: white;
}
#timer {
    font-size: 5rem;
    font-weight: bold;
    text-align: center;
    color: #FFD700;
    margin-top: 100px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Load Lottie animation from file
# ---------------------------
try:
    with open("Animation - 1746878176459.json", "r") as f:
        lottie_json = json.load(f)
except Exception as e:
    lottie_json = None
    st.error(f"⚠️ Could not load Lottie animation: {e}")

# ---------------------------
# Display Content
# ---------------------------
st.markdown("<h1>Vekkam Premier</h1>", unsafe_allow_html=True)
st.markdown("<h3>We're working on something big behind the scenes, so stay tuned for an unforgettable launch.</h3>", unsafe_allow_html=True)

st.markdown("""
<h5>
Running on caffeine and chaos before exams? Been there. That’s exactly why we built Vekkam — your AI-powered study partner that turns your notes into flashcards, cheat sheets, quizzes, and mind maps. In seconds. No more scrolling through 87-slide PPTs or pretending to “revise” — we do the heavy lifting so you can focus on actually learning. Built for Indian university students, Vekkam isn’t just another AI tool that solves math — we handle everything, from history to finance, and we get how you learn best. Think cognitive profiling, personalized study material, and a product that works harder than your toppers’ WhatsApp group. We’re here to flip the system. Studying? Sorted.
</h5>
""", unsafe_allow_html=True)

st.markdown("""
    <div style="text-align: center; margin-top: 30px;">
        <a href="https://vekkam.wordpress.com/home/" target="_blank">
            <button style="
                background-color: #FF3131;
                color: white;
                border: none;
                padding: 12px 24px;
                font-size: 16px;
                border-radius: 8px;
                cursor: pointer;
                transition: background-color 0.3s ease;
            ">
                Click to learn more
            </button>
        </a>
    </div>
""", unsafe_allow_html=True)

# ---------------------------
# Lottie animation
# ---------------------------
if lottie_json:
    st_lottie(lottie_json, height=500, key="premiere")

# ---------------------------
# Countdown Logic
# ---------------------------
target_date = datetime(2025, 5, 31, 0, 0, 0)
now = datetime.now()
remaining = target_date - now

if remaining.total_seconds() <= 0:
    st.markdown("<div id='timer'>🎉 PREMIERE NOW! 🎉</div>", unsafe_allow_html=True)
else:
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    countdown = f"<div id='timer'>{days}d {hours:02}h {minutes:02}m {seconds:02}s</div>"
    st.markdown(countdown, unsafe_allow_html=True)

# ---------------------------
# Footer Text
# ---------------------------
st.markdown("<br><h4 style='text-align: center;'>📅 Mark your calendars: May 31, 2025</h4>", unsafe_allow_html=True)
