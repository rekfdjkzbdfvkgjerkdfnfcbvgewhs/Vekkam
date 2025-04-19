import streamlit as st
import fitz  # PyMuPDF
import docx
import json
import re
from io import StringIO
from PIL import Image
import pytesseract
import plotly.graph_objects as go
import igraph as ig
import requests
import streamlit.components.v1 as components
import time
from pptx import Presentation
from datetime import datetime, timedelta

# --- Page Config & Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown("""
    <div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
        <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
    </div>
""", unsafe_allow_html=True)

st.title("Vekkam - the Study Buddy of Your Dreams")
st.info("Upload files to generate summaries, mind maps, flashcards, and more. We do what ChatGPT and NotebookLM by Google can't do.")

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)",
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Interactive Loader HTML ---
loader_html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Brainrot Loader</title>
  <style>
    body {
      margin: 0;
      font-family: 'Comic Sans MS', cursive, sans-serif;
      background: linear-gradient(135deg, #ff9a9e 0%, #fad0c4 100%);
      overflow: hidden;
      text-align: center;
    }
    #loader {
      width: 100%;
      height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    #progress {
      font-size: 30px;
      margin-top: 30px;
      color: #ff4500;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(1); }
      50% { transform: scale(1.1); }
      100% { transform: scale(1); }
    }
    .mascot {
      width: 150px;
      height: 150px;
      background: url('mascot.png') no-repeat center center;
      background-size: contain;
      animation: bounce 2s infinite;
    }
    @keyframes bounce {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-20px); }
    }
  </style>
</head>
<body>
  <div id="loader">
    <div class="mascot"></div>
    <div id="progress">Loading... 0%</div>
  </div>
  <script>
    let progress = 0;
    const progressText = document.getElementById('progress');
    const interval = setInterval(() => {
      progress = (progress + 1) % 101;
      progressText.textContent = `Loading... ${progress}%`;
    }, 550);
    
    const observer = new MutationObserver(mutations => {
      mutations.forEach(mutation => {
        if (!document.body.contains(document.getElementById("loader"))) {
          clearInterval(interval);
        }
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  </script>
</body>
</html>
"""

# --- Text Extraction ---
def extract_text(file):
    ext = file.name.lower()
    if ext.endswith(".pdf"):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            return "".join([page.get_text() for page in doc])
    elif ext.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(file))
    elif ext.endswith(".pptx"):
        prs = Presentation(file)
        return "\n".join([slide.shapes[0].text for slide in prs.slides if slide.shapes])
    elif ext.endswith(".txt"):
        return StringIO(file.read().decode("utf-8")).getvalue()
    elif ext.endswith((".jpg", ".jpeg", ".png")):
        image = Image.open(file)
        return pytesseract.image_to_string(image)
    return ""

# --- Mind Map Generation ---
def get_mind_map(text):
    # This function will generate a mind map from the provided text
    # For simplicity, let's assume it creates a basic structure
    topics = re.split(r'\n+', text.strip())
    mind_map = {topic: [] for topic in topics if topic}
    return mind_map

# --- Main Logic ---
if uploaded_files:
    for uploaded_file in uploaded_files:
        text = extract_text(uploaded_file)
        mind_map = get_mind_map(text)
        st.write(mind_map)

# --- Study Schedule Generation ---
def generate_study_schedule(exam_date, syllabus):
    schedule = {}
    exam_date_datetime = datetime.combine(exam_date, datetime.min.time())
    days_until_exam = (exam_date_datetime - datetime.now()).days
    topics_per_day = len(syllabus) // days_until_exam if days_until_exam > 0 else 1
    for i in range(days_until_exam):
        schedule[(datetime.now() + timedelta(days=i)).date()] = syllabus[i * topics_per_day:(i + 1) * topics_per_day]
    return schedule

# --- User Input for Exam Date ---
exam_date_input = st.date_input("Select your exam date")
if st.button("Generate Study Schedule"):
    syllabus = list(mind_map.keys())  # Assuming mind_map is generated
    study_schedule = generate_study_schedule(exam_date_input, syllabus)
    st.write(study_schedule)
