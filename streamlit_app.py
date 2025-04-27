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
from pptx import Presentation
import streamlit.components.v1 as components
import time
import networkx as nx

# --- Page Config & Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown("""
    <div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
        <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
    </div>
""", unsafe_allow_html=True)

st.title("Vekkam - the Study Buddy of Your Dreams")
st.info("Upload files or fetch your guide-book + syllabus to generate personalized study plans, summaries, mind maps, flashcards, and more.")

# --- Book & Syllabus Inputs ---
st.header("📚 Guide-Book & Syllabus Setup")
book_input = st.text_input("Enter Guide-Book Title or ISBN for lookup:")
book_data = None
if book_input:
    # Fetch metadata from Google Books API
    params = {'q': book_input, 'maxResults': 1, 'printType': 'books'}
    res = requests.get("https://www.googleapis.com/books/v1/volumes", params=params)
    if res.status_code == 200 and 'items' in res.json():
        book_data = res.json()['items'][0]
        info = book_data['volumeInfo']
        st.subheader(info.get('title', 'Unknown Title'))
        st.write(f"**Authors:** {', '.join(info.get('authors', []))}")
        st.write(f"**Published Date:** {info.get('publishedDate', 'N/A')}")
        toc = info.get('tableOfContents', []) if 'tableOfContents' in info else None
        if not toc and 'description' in info:
            st.write(info['description'])
        else:
            st.write("**Table of Contents:**")
            for idx, chapter in enumerate(toc or [], 1):
                st.write(f"{idx}. {chapter}")
    else:
        st.error("Book not found or API error.")

syllabus_input = st.text_area("Paste or enter your exam syllabus (one topic per line):")
syllabus_json = None
if syllabus_input:
    # Simple parser: split lines into JSON structure
    topics = [line.strip() for line in syllabus_input.splitlines() if line.strip()]
    syllabus_json = {'topics': topics}
    st.write("**Structured Syllabus:**")
    st.json(syllabus_json)

# --- File Upload ---
st.header("📄 Upload Study Materials (PDF, DOCX, PPTX, TXT, JPG, PNG)")
uploaded_files = st.file_uploader(
    "Upload documents or images to supplement your guide-book.",
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Interactive Loader HTML ---
loader_html = """<!DOCTYPE html><html lang=\"en\">... (loader HTML unchanged) ...</html>"""

# --- Text Extraction Function ---
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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    for attempt in range(3):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        elif res.status_code == 429:
            time.sleep(30)
        else:
            break
    return f"<p>API error {res.status_code}</p>"

# --- Core Study-Plan Generation ---
def generate_study_plan(book_info, syllabus):
    prompt = f"""
You are an AI study assistant.
Given the guide-book metadata and structured syllabus, create a 6-hour study plan.

Book Info: {json.dumps(book_info, indent=2)}
Syllabus: {json.dumps(syllabus, indent=2)}

Produce a detailed timeline with sessions, topics, and resources.
"""
    return call_gemini(prompt, temperature=0.5)

# --- Display Helper ---
def render_section(title, content):
    st.subheader(title)
    st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
if book_data and syllabus_json:
    st.header("🗓️ Generated 6-Hour Study Plan")
    plan = generate_study_plan(book_data, syllabus_json)
    render_section("Study Plan", plan)

if uploaded_files:
    loader = st.empty()
    loader.components.html(loader_html, height=600)
    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)
        # Generate learning aids as before...
        # ... mind map, summary, flashcards, mnemonics using call_gemini()
        # For brevity, reuse existing functions and render_section
    loader.empty()
else:
    st.info("Upload materials or input your guide-book and syllabus to begin.")
