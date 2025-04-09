import streamlit as st
import fitz  # PyMuPDF
import docx
import json
import re
import html
from io import StringIO
from PIL import Image
import pytesseract
import plotly.graph_objects as go
import igraph as ig
import requests
from pptx import Presentation
import streamlit.components.v1 as components

# --- Page Config & Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.html("""
<div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
    <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
</div>
""")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.text("Review summaries, flashcards, cheat sheets, and more to reinforce your learning.")

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
            return "".join(page.get_text() for page in doc)
    elif ext.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    elif ext.endswith(".pptx"):
        prs = Presentation(file)
        return "\n".join(shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text"))
    elif ext.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    elif ext.endswith((".jpg", ".jpeg", ".png")):
        return pytesseract.image_to_string(Image.open(file))
    return ""

# --- Gemini API Call (via Vekkam Endpoint) ---
def call_gemini(prompt, temperature=0.7, max_tokens=2048):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        try:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"<p>Parsing error: {e}</p>"
    else:
        return f"<p>Gemini API error {response.status_code}: {html.escape(response.text)}</p>"

# --- Smart Display ---
def render_response(response):
    response = response.strip()
    if response.lower().startswith("<!doctype html") or response.lower().startswith("<html"):
        components.html(response, height=800, scrolling=True)
    else:
        st.markdown(response, unsafe_allow_html=True)

# --- Concept Map via Gemini ---
def get_concept_map(text):
    prompt = f"""You are an AI that creates a concept map in HTML format.
The HTML should contain:
- A main title for the topic
- Sections for each subtopic with their own children listed
- Use <h2>, <h3>, <ul>, <li> etc. for structure
- Avoid inline styles; use clean semantic HTML
- Do not include JSON or markdown

Text:
{text}
"""
    raw_output = call_gemini(prompt, temperature=0.4)

    if not raw_output:
        st.error("Concept map generation failed: No response from Gemini.")
        return None

    return raw_output.strip()

# --- Build and Plot Mind Map ---
def build_igraph_graph(concept_json):
    vertices, edges = [], []

    def walk(node, parent_id=None):
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        vertices.append({"id": node_id, "label": node["title"], "description": node.get("description", "")})
        if parent_id:
            edges.append((parent_id, node_id))
        for child in node.get("children", []):
            walk(child, node_id)

    root = {
        "title": concept_json["topic"]["title"],
        "description": concept_json["topic"].get("description", ""),
        "children": concept_json.get("subtopics", [])
    }
    walk(root)
    g = ig.Graph(directed=True)
    g.add_vertices([v["id"] for v in vertices])
    g.vs["label"] = [v["label"] for v in vertices]
    g.vs["description"] = [v["description"] for v in vertices]
    if edges:
        g.add_edges(edges)
    return g

def plot_igraph_graph(g):
    layout = g.layout("fr")
    edge_x, edge_y = [], []
    for e in g.es:
        x0, y0 = layout[e.source]
        x1, y1 = layout[e.target]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none')
    node_x, node_y, texts = [], [], []
    for i, v in enumerate(g.vs):
        x, y = layout[i]
        node_x.append(x)
        node_y.append(y)
        texts.append(f"<b>{v['label']}</b><br>{v['description']}")
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers+text', text=g.vs["label"],
        textposition="top center", marker=dict(size=20, color='#00cc96', line_width=2),
        hoverinfo='text', hovertext=texts
    )
    return go.Figure(data=[edge_trace, node_trace],
                     layout=go.Layout(title="Interactive Mind Map", hovermode='closest',
                                      xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                      yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)))

# --- Study Aids ---
def generate_summary(text): return call_gemini(f"Summarize this for an exam:\n\n{text[:4000]}", temperature=0.5)
def generate_questions(text): return call_gemini(f"Generate 15 educational quiz questions:\n\n{text[:4000]}", temperature=0.5)
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A):\n\n{text[:4000]}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics:\n\n{text[:4000]}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms with definitions:\n\n{text[:4000]}", temperature=0.6)
def generate_cheatsheet(text): return call_gemini(f"Create a bullet-point cheat sheet:\n\n{text[:4000]}", temperature=0.7)
def generate_highlights(text): return call_gemini(f"List key points and important facts:\n\n{text[:4000]}")

# --- File Processor ---
def process_file(file):
    text = extract_text(file)
    return {
        "name": file.name,
        "text": text,
        "concept_map": get_concept_map(text),
        "summary": generate_summary(text),
        "questions": generate_questions(text),
        "flashcards": generate_flashcards(text),
        "mnemonics": generate_mnemonics(text),
        "key_terms": generate_key_terms(text),
        "cheatsheet": generate_cheatsheet(text),
        "highlights": generate_highlights(text)
    }

# --- Main App Logic ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing: {file.name}"):
            result = process_file(file)
            st.markdown(f"---\n## Document: {result['name']}")

            if result["concept_map"]:
                st.subheader("🧠 Concept Map")
                render_response(result["concept_map"])
            else:
                st.error("Concept map generation failed.")


            st.subheader("📌 Summary")
            render_response(result["summary"])

            st.subheader("📝 Quiz Questions")
            render_response(result["questions"])

            with st.expander("Flashcards"):
                render_response(result["flashcards"])
            with st.expander("Mnemonics"):
                render_response(result["mnemonics"])
            with st.expander("Key Terms"):
                render_response(result["key_terms"])
            with st.expander("Cheat Sheet"):
                render_response(result["cheatsheet"])
            with st.expander("Highlighted Key Points"):
                render_response(result["highlights"])
else:
    st.info("Upload documents above to begin.")
