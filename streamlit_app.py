import streamlit as st
from datetime import datetime
import time

st.set_page_config(page_title="🎬 Premiere Countdown", layout="wide")

# Title and headers
st.markdown("<h1 style='text-align: center;'>🎬 Premiere Countdown</h1>", unsafe_allow_html=True)
st.header("Get Ready for the Big Event!")
st.subheader("Counting down to June 30, 2025")

# Countdown logic
target_date = datetime(2025, 6, 30, 0, 0, 0)
timer_placeholder = st.empty()

while True:
    now = datetime.now()
    remaining = target_date - now
    if remaining.total_seconds() <= 0:
        timer_placeholder.markdown("<h2 style='text-align: center;'>🎉 PREMIERE NOW! 🎉</h2>", unsafe_allow_html=True)
        break
    days = remaining.days
    hours, rem = divmod(remaining.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    timer_str = f"<h2 style='text-align: center;'>{days}d {hours:02}h {minutes:02}m {seconds:02}s</h2>"
    timer_placeholder.markdown(timer_str, unsafe_allow_html=True)
    time.sleep(1)

# Additional text
st.markdown("**Don't miss out!** The premiere starts in:")
st.text("Stay tuned for more updates.")
