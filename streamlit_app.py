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

# --- Mind Map ---
def get_mind_map(text):
    prompt = f"""
You are an assistant that creates a JSON mind map from the text below.

Structure:
{{
  "nodes": [{{"id": "1", "label": "Label", "description": "Short definition"}}],
  "edges": [{{"source": "1", "target": "2"}}]
}}

IMPORTANT:
- Output only valid JSON.
- Do NOT include markdown, explanation, or commentary.
- Ensure both "nodes" and "edges" are present.
- Include a short definition/description as applicable for each of the bubbles in the mind map.
- Keep it short and sweet so that it looks clean.
- Generate 5 children each from 7 total nodes.
- It's for a test I have tomorrow.
- If there's any formulae you see, give a few questions on that as well.

Output only the questions.
Text:
{text}
"""
    response = call_gemini(prompt, temperature=0.5)
    try:
        json_data = re.search(r'\{.*\}', response, re.DOTALL)
        if not json_data:
            raise ValueError("No JSON block found.")
        cleaned = re.sub(r",\s*([}\]])", r"\\1", json_data.group(0))
        parsed = json.loads(cleaned)
        if "nodes" not in parsed or "edges" not in parsed:
            raise ValueError("Response missing 'nodes' or 'edges'.")
        return parsed
    except Exception as e:
        st.error(f"Mind map JSON parsing failed: {e}")
        st.code(response)
        return None

# --- Plot Mind Map ---
def plot_mind_map(nodes, edges):
    if len(nodes) < 2:
        st.warning("Mind map needs at least 2 nodes.")
        return
    id_to_index = {node['id']: i for i, node in enumerate(nodes)}
    g = ig.Graph(directed=True)
    g.add_vertices(len(nodes))
    valid_edges = []
    for e in edges:
        src = e['source']
        tgt = e['target']
        if src in id_to_index and tgt in id_to_index:
            valid_edges.append((id_to_index[src], id_to_index[tgt]))
    g.add_edges(valid_edges)
    try:
        layout = g.layout("kk")
    except:
        layout = g.layout("fr")
    scale = 3
    edge_x, edge_y = [], []
    for e in g.es:
        x0, y0 = layout[e.source]
        x1, y1 = layout[e.target]
        edge_x += [x0 * scale, x1 * scale, None]
        edge_y += [y0 * scale, y1 * scale, None]
    node_x, node_y, hover_labels = [], [], []
    for i, node in enumerate(nodes):
        x, y = layout[i]
        node_x.append(x * scale)
        node_y.append(y * scale)
        label = node['label']
        desc = node.get('description', 'No description.')
        hover_labels.append(f"<b>{label}</b><br>{desc}")
    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none')
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers+text',
        text=[node['label'] for node in nodes],
        textposition="top center",
        marker=dict(size=20, color='#00cc96', line_width=2),
        hoverinfo='text',
        hovertext=hover_labels
    )
    fig = go.Figure(data=[edge_trace, node_trace], layout=go.Layout(
        title="🧠 Mind Map (ChatGPT can't do this)",
        width=1200, height=800,
        hovermode='closest',
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    ))
    components.html(fig.to_html(full_html=False, include_plotlyjs='cdn'), height=900, scrolling=True)

# --- AI Learning Aids ---
def generate_summary(text): 
    return call_gemini(f"Summarize this for an exam and separately list any formulae that are mentioned in the text. If there aren't any, skip this section:\n\n{text}", temperature=0.5)
def generate_questions(text): 
    return call_gemini(f"Generate 15 quiz questions for an exam (ignore authors, ISSN, etc.):\n\n{text}")
def generate_flashcards(text): 
    return call_gemini(f"Create flashcards (Q&A):\n\n{text}")
def generate_mnemonics(text): 
    return call_gemini(f"Generate mnemonics:\n\n{text}")
def generate_key_terms(text): 
    return call_gemini(f"List 10 key terms with definitions:\n\n{text}")
def generate_cheatsheet(text): 
    return call_gemini(f"Create a cheat sheet for exams from the following text:\n\n{text}")

# --- Sidebar for Selections ---
st.sidebar.title("Choose Actions")
summary = st.sidebar.checkbox("Summary")
flashcards = st.sidebar.checkbox("Flashcards")
questions = st.sidebar.checkbox("Questions")
key_terms = st.sidebar.checkbox("Key Terms")
mnemonics = st.sidebar.checkbox("Mnemonics")
cheatsheet = st.sidebar.checkbox("Cheat Sheet")
mind_map = st.sidebar.checkbox("Mind Map")

# --- File Text Processing ---
if uploaded_files:
    for file in uploaded_files:
        with st.expander(f"📄 {file.name}", expanded=False):
            text = extract_text(file)
            st.text_area("Extracted Text", text, height=200)
            
            # Display selected actions
            if summary:
                st.markdown(generate_summary(text), unsafe_allow_html=True)
            if flashcards:
                st.markdown(generate_flashcards(text), unsafe_allow_html=True)
            if questions:
                st.markdown(generate_questions(text), unsafe_allow_html=True)
            if key_terms:
                st.markdown(generate_key_terms(text), unsafe_allow_html=True)
            if mnemonics:
                st.markdown(generate_mnemonics(text), unsafe_allow_html=True)
            if cheatsheet:
                st.markdown(generate_cheatsheet(text), unsafe_allow_html=True)
            if mind_map:
                map_data = get_mind_map(text)
                if map_data:
                    plot_mind_map(map_data["nodes"], map_data["edges"])
