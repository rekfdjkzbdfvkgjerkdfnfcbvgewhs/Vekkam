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
import tempfile
from gtts import gTTS
import os
from fpdf import FPDF  # To generate PDF for question papers

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
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
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

# --- Professor Mode - Question Paper Generation ---
def generate_question_paper(topics, difficulty, question_type):
    prompt = f"""
Generate a question paper on the following topics: {topics}. 
The difficulty level is {difficulty}. 
The type of questions is {question_type}.

Please provide the questions and their corresponding answers in a clear and organized format.
"""
    return call_gemini(prompt, temperature=0.8)

# --- Sidebar for Selections ---
st.sidebar.title("Choose Actions")
summary = st.sidebar.checkbox("Summary")
flashcards = st.sidebar.checkbox("Flashcards")
questions = st.sidebar.checkbox("Questions")
key_terms = st.sidebar.checkbox("Key Terms")
mnemonics = st.sidebar.checkbox("Mnemonics")
cheatsheet = st.sidebar.checkbox("Cheat Sheet")
mind_map = st.sidebar.checkbox("Mind Map")
generate_audio = st.sidebar.checkbox("Generate Podcast-Style Audio")
simplify = st.sidebar.checkbox("Dumb Down Concepts")
highlight = st.sidebar.checkbox("Highlight Important Topics")
professor_mode = st.sidebar.checkbox("Professor Mode")

# --- Professor Mode Inputs ---
if professor_mode:
    st.sidebar.header("Professor Mode - Create Your Own Question Paper")
    topics_input = st.sidebar.text_area("Enter Topics for the Question Paper", "e.g., Economics, Algebra, Physics")
    difficulty = st.sidebar.selectbox("Select Difficulty Level", ["Easy", "Medium", "Hard"])
    question_type = st.sidebar.selectbox("Select Question Type", ["Multiple Choice", "Short Answer", "Long Answer"])

# --- File Text Processing ---
if uploaded_files:
    for file in uploaded_files:
        with st.expander(f"📄 {file.name}", expanded=False):
            text = extract_text(file)

            # Display selected actions outside the text box
            output_text = ""

            if summary:
                output_text += generate_summary(text)
            if flashcards:
                output_text += generate_flashcards(text)
            if questions:
                output_text += generate_questions(text)
            if key_terms:
                output_text += generate_key_terms(text)
            if mnemonics:
                output_text += generate_mnemonics(text)
            if cheatsheet:
                output_text += generate_cheatsheet(text)
            if mind_map:
                map_data = get_mind_map(text)
                if map_data:
                    plot_mind_map(map_data["nodes"], map_data["edges"])

            # Simplify concepts if selected
            if simplify:
                if output_text:
                    output_text = simplify_concept(output_text)

            # Highlight important topics if selected
            if highlight:
                important_topics = highlight_important_topics(text)
                if important_topics:
                    output_text += "\n\n**Important Exam Topics:**\n" + important_topics

            # Generate podcast-style audio if selected
            if generate_audio:
                if output_text:
                    tts = gTTS(text=output_text, lang='en', slow=False)
                    audio_file_path = tempfile.mktemp(suffix=".mp3")
                    tts.save(audio_file_path)
                    audio_file = open(audio_file_path, "rb")
                    st.audio(audio_file, format="audio/mp3", caption="Podcast-Style Audio Output")
                    os.remove(audio_file_path)
                else:
                    st.warning("No output generated for audio. Please select one or more options.")
def generate_summary(text):
    prompt = f"Please provide a summary of the following text:\n\n{text}"
    return call_gemini(prompt)

def generate_flashcards(text):
    prompt = f"Generate flashcards based on the following text:\n\n{text}"
    return call_gemini(prompt)

def generate_questions(text):
    prompt = f"Create a set of questions based on the following text:\n\n{text}"
    return call_gemini(prompt)

def generate_key_terms(text):
    prompt = f"Extract the key terms from the following text:\n\n{text}"
    return call_gemini(prompt)

def generate_mnemonics(text):
    prompt = f"Generate mnemonics based on the following text:\n\n{text}"
    return call_gemini(prompt)

def generate_cheatsheet(text):
    prompt = f"Create a cheat sheet from the following text:\n\n{text}"
    return call_gemini(prompt)

def simplify_concept(text):
    prompt = f"Simplify the following concept for easier understanding:\n\n{text}"
    return call_gemini(prompt)

def highlight_important_topics(text):
    prompt = f"Highlight the important exam topics in the following text:\n\n{text}"
    return call_gemini(prompt)

# --- Generate Question Paper in Professor Mode ---
if professor_mode:
    if st.sidebar.button("Generate Question Paper"):
        if topics_input:
            question_paper = generate_question_paper(topics_input, difficulty, question_type)
            st.subheader("Generated Question Paper")
            st.write(question_paper)
            
            # Allow user to download the question paper as a PDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=f"Question Paper on {topics_input} - Difficulty: {difficulty} - Type: {question_type}", ln=True)
            pdf.multi_cell(200, 10, txt=question_paper)
            pdf_output = tempfile.mktemp(suffix=".pdf")
            pdf.output(pdf_output)

            with open(pdf_output, "rb") as f:
                st.download_button("Download Question Paper as PDF", f, file_name="question_paper.pdf")
        else:
            st.warning("Please enter topics for the question paper.")
