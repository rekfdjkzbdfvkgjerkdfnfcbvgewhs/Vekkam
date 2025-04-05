import streamlit as st
import cohere
import fitz  # PyMuPDF for PDFs
import docx
import json
from io import StringIO
import igraph as ig
import plotly.graph_objects as go
import requests

# --- Page Config ---
st.set_page_config(page_title="KnowMap AI", layout="wide")
st.title("📘 KnowMap – AI-Powered Interactive Mind Maps & Doubt Solver")

# --- Load API Clients ---
co = cohere.Client(st.secrets["cohere_api_key"])
SERP_API_KEY = st.secrets["serp_api_key"]

# --- Upload Files ---
uploaded_files = st.file_uploader("Upload documents (PDF, DOCX, TXT)", 
                                  type=["pdf", "docx", "txt"], 
                                  accept_multiple_files=True)

# --- Helper Functions ---
def extract_text(file):
    if file.name.endswith(".pdf"):
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text
    elif file.name.endswith(".docx"):
        doc_obj = docx.Document(file)
        return "\n".join([p.text for p in doc_obj.paragraphs])
    elif file.name.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    return ""

def get_concept_map(text):
    prompt = f"""You are an AI that converts text into a concept map in JSON. 
Each node in the concept map should include a "title" and a "description" summarizing that part of the text.
Output should be in the following format:
{{
  "topic": {{
      "title": "Main Topic",
      "description": "Description of the main topic."
  }},
  "subtopics": [
    {{
      "title": "Subtopic A",
      "description": "Description
