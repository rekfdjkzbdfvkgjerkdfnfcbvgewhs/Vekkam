import streamlit as st
from datetime import datetime
import time
import json
from streamlit_lottie import st_lottie

# ---------------------------
# Load Lottie animation from local file
# ---------------------------
def load_lottie_file(filepath: str):
    with open(filepath, "r") as f:
        return json.load(f)

# ---------------------------
# Page configuration
# ---------------------------
st.set_page_config(
    page_title="Vekkam Premiere Countdown",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------
# Custom CSS styling
# ---------------------------
st.markdown("""
<style>
body {
    background: radial-gradient(circle at center, #000000, #141414);
    color: #FFFFFF;
}
#main-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
h1, h2, h3 {
    text-align: center;
    color: white;
}
#timer {
    font-size: 5rem;
    font-weight: bold;
    text-align: center;
    color: #FFD700;
    margin-top: -30px;
}
</style>
""", unsafe_allow_html=True)

# Load the Lottie animation
try:
    lottie_json = load_lottie_file("Animation - 1746878176459.json")
    st_lottie(lottie_json, height=300, key="premiere")
except Exception as e:
    st.error(f"Could not load animation: {e}")

# ---------------------------
# Display Content
# ---------------------------
st.markdown("<h1>Vekkam Premier</h1>", unsafe_allow_html=True)
st.markdown("<h3>We're working on something big behind the scenes, so stay tuned for an unforgettable launch.</h3>", unsafe_allow_html=True)
st.write("Vekkam is an AI-driven educational platform designed to help students study more efficiently by generating personalized study plans. By leveraging neuroscience, behavioral science, and real-world exam performance data, Vekkam creates individualized 6-hour study schedules tailored to each student's unique learning style. This approach aims to optimize study time, enabling students to balance academic responsibilities with extracurricular activities effectively.")
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
                Click to Learn more!
            </button>
        </a>
    </div>
""", unsafe_allow_html=True)

# ---------------------------
# Countdown Logic
# ---------------------------
target_date = datetime(2025, 6, 30, 0, 0, 0)
timer_placeholder = st.empty()

while True:
    now = datetime.now()
    remaining = target_date - now
    if remaining.total_seconds() <= 0:
        timer_placeholder.markdown("<div id='timer'>🎉 PREMIERE NOW! 🎉</div>", unsafe_allow_html=True)
        break
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    countdown = f"<div id='timer'>{days}d {hours:02}h {minutes:02}m {seconds:02}s</div>"
    timer_placeholder.markdown(countdown, unsafe_allow_html=True)
    time.sleep(1)

# ---------------------------
# Footer
# ---------------------------
st.markdown("<br><h4 style='text-align: center;'>📅 Mark your calendars: June 30, 2025</h4>", unsafe_allow_html=True)
