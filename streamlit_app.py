import streamlit as st
import requests
from datetime import datetime
import time
from streamlit_lottie import st_lottie

# Function to load Lottie animation from a URL
def load_lottie_url(url: str):
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()
    else:
        return None

# Set page configuration
st.set_page_config(
    page_title="Vekkam",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for styling
page_css = """
<style>
body {
    background: radial-gradient(circle at center, #000000, #141414);
    color: #FFFFFF;
    overflow: hidden;
}
#timer {
    font-size: 6rem;
    font-weight: 700;
    text-align: center;
    margin-top: -50px;
    letter-spacing: -2px;
}
#container {
    position: relative;
    width: 100%;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
}
</style>
"""
st.markdown(page_css, unsafe_allow_html=True)

# Load Lottie animation
lottie_url = "https://assets2.lottiefiles.com/packages/lf20_mDnmhAgZkb.json"  # Replace with your chosen Lottie JSON URL
lottie_json = load_lottie_url(lottie_url)

# Display Lottie animation
if lottie_json:
    st_lottie(lottie_json, height=250, key="premiere_intro")
else:
    st.error("Failed to load Lottie animation.")

# Countdown logic
target_date = datetime(2025, 6, 30, 0, 0, 0)
timer_placeholder = st.empty()

while True:
    now = datetime.now()
    remaining = target_date - now
    secs = int(remaining.total_seconds())
    if secs <= 0:
        timer_placeholder.markdown("<div id='timer'>🎉 PREMIERE NOW! 🎉</div>", unsafe_allow_html=True)
        break
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    timer_str = f"<div id='timer'>{days}d {hours:02}h {minutes:02}m {seconds:02}s</div>"
    timer_placeholder.markdown(timer_str, unsafe_allow_html=True)
    time.sleep(1)
