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
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    elif ext.endswith(".pptx"):
        return "\n".join(shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape, "text"))
    elif ext.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    elif ext.endswith((".jpg", ".jpeg", ".png")):
        return pytesseract.image_to_string(Image.open(file))
    return ""

# --- Gemini API Call ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['GEMINI_API_KEY']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }
    max_retries = 3
    retry_delay = 30  # seconds
    for attempt in range(max_retries):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            try:
                return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                return f"<p>Error parsing response: {e}</p>"
        elif res.status_code == 429:
            if attempt < max_retries - 1:
                st.warning("Rate limit reached. Retrying in 30 seconds...")
                time.sleep(retry_delay)
            else:
                return "<p>API rate limit reached. Please try again later.</p>"
        else:
            break
    return f"<p>Gemini API error {res.status_code}: {res.text}</p>"

# --- Generate Study Schedule ---
def generate_study_schedule(exam_date, syllabus):
    schedule = {}
    days_until_exam = (exam_date - datetime.now()).days
    topics_per_day = len(syllabus) // days_until_exam if days_until_exam > 0 else 1
    for i in range(days_until_exam):
        schedule[(datetime.now() + timedelta(days=i)).date()] = syllabus[i * topics_per_day:(i + 1) * topics_per_day]
    return schedule

# --- AI Learning Aids ---
def generate_summary(text): 
    return call_gemini(f"Summarize this for an exam:\n\n{text}", temperature=0.5)
def generate_questions(text): 
    return call_gemini(f"Generate 15 quiz questions for an exam:\n\n{text}")
def generate_flashcards(text): 
    return call_gemini(f"Create flashcards (Q&A):\n\n{text}")
def generate_mnemonics(text): 
    return call_gemini(f"Generate mnemonics:\n\n{text}")
def generate_key_terms(text): 
    return call_gemini(f"List 10 key terms with definitions:\n\n{text}")
def generate_cheatsheet(text): 
    return call_gemini(f"Create a cheat sheet:\n\n{text}")
def generate_highlights(text): 
    return call_gemini(f"List key facts and highlights:\n\n{text}")

# --- Display Helper ---
def render_section(title, content):
    st.subheader(title)
    if content.strip().startswith("<"):
        components.html(content, height=600, scrolling=True)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
if uploaded_files:
    loader_placeholder = st.empty()
    with loader_placeholder:
        components.html(loader_html, height=600)
    
    first_file_processed = False

    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)
        syllabus = text.splitlines()  # Assuming each line is a topic for the study schedule
        exam_date = st.date_input("Select Exam Date", datetime.now())

        if st.button("Generate Study Schedule"):
            schedule = generate_study_schedule(exam_date, syllabus)
            st.write("Your Study Schedule:")
            for date, topics in schedule.items():
                st.write(f"{date}: {', '.join(topics)}")

        mind_map = get_mind_map(text)
        summary = generate_summary(text)
        questions = generate_questions(text)
        flashcards = generate_flashcards(text)
        mnemonics = generate_mnemonics(text)
        key_terms = generate_key_terms(text)
        cheatsheet = generate_cheatsheet(text)
        highlights = generate_highlights(text)

        if mind_map:
            st.subheader("🧠 Mind Map (ChatGPT can't do this)")
            plot_mind_map(mind_map["nodes"], mind_map["edges"])
        else:
            st.error("Mind map generation failed.")

        render_section("📌 Summary", summary)
        render_section("📝 Quiz Questions", questions)
        with st.expander("📚 Flashcards"):
            render_section("Flashcards", flashcards)
        with st.expander("🧠 Mnemonics"):
            render_section("Mnemonics", mnemonics)
        with st.expander("🔑 Key Terms"):
            render_section("Key Terms", key_terms)
        with st.expander("📋 Cheat Sheet"):
            render_section("Cheat Sheet", cheatsheet)
        with st.expander("⭐ Highlights"):
            render_section("Highlights", highlights)
        
        if not first_file_processed:
            loader_placeholder.empty()
            first_file_processed = True
else:
    st.info("Upload a document to get started.")
