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

# --- Page Setup ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown("""
    <div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
        <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
    </div>
""", unsafe_allow_html=True)
st.title("Vekkam - the Study Buddy of Your Dreams")

# --- File Upload ---
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, PPTX, TXT, JPG, PNG)",
    type=["pdf", "docx", "pptx", "txt", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Extract Text from Uploaded File ---
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

# --- Call Gemini API ---
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
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code == 200:
        try:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"<p>Parsing error: {e}</p>"
    return f"<p>Gemini API error {res.status_code}: {res.text}</p>"

# --- Mind Map Generator from Gemini (with Descriptions) ---
def get_mind_map(text):
    prompt = f"""
You are a mind map generator AI.

Create a JSON object with:
- "nodes": each with "id", "label", and a short "description"
- "edges": each with "source" and "target" referencing node IDs

Only return raw valid JSON.

Text:
{text}
"""
    response = call_gemini(prompt, temperature=0.4)
    try:
        json_data = re.search(r'\{.*\}', response, re.DOTALL)
        if json_data:
            cleaned = re.sub(r",\s*([}\]])", r"\1", json_data.group(0))
            return json.loads(cleaned)
    except Exception as e:
        st.error(f"Failed to parse Gemini response: {e}")
        st.code(response)
    return None

# --- Plot Mind Map using Plotly ---
def plot_mind_map(nodes, edges):
    if len(nodes) < 2:
        st.warning("Mind map needs at least 2 nodes.")
        return

    id_to_index = {node['id']: i for i, node in enumerate(nodes)}
    g = ig.Graph(directed=True)
    g.add_vertices(len(nodes))
    g.add_edges([(id_to_index[e['source']], id_to_index[e['target']]) for e in edges])

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

    node_x, node_y, hover_text = [], [], []
    for i, v in enumerate(g.vs):
        x, y = layout[i]
        node_x.append(x * scale)
        node_y.append(y * scale)
        label = nodes[i]['label']
        desc = nodes[i].get('description', '')
        hover_text.append(f"<b>{label}</b><br>{desc}")

    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none')
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers+text',
        text=[n['label'] for n in nodes],
        textposition="top center", marker=dict(size=20, color='#00cc96', line_width=2),
        hoverinfo='text', hovertext=hover_text
    )

    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title="🧠 Gemini-Generated Mind Map",
            width=1200, height=800, hovermode='closest',
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    )

    components.html(fig.to_html(full_html=False, include_plotlyjs='cdn'), height=900, scrolling=True)

# --- AI Study Aids ---
def generate_summary(text): return call_gemini(f"Summarize this for an exam:\n\n{text[:4000]}", 0.5)
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions:\n\n{text[:4000]}", 0.5)
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A):\n\n{text[:4000]}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics:\n\n{text[:4000]}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms with definitions:\n\n{text[:4000]}", 0.6)
def generate_cheatsheet(text): return call_gemini(f"Create a cheat sheet:\n\n{text[:4000]}", 0.7)
def generate_highlights(text): return call_gemini(f"List key facts and highlights:\n\n{text[:4000]}")

# --- Smart Display ---
def render_response(response):
    if response.strip().startswith("<"):
        components.html(response, height=600, scrolling=True)
    else:
        st.markdown(response, unsafe_allow_html=True)

# --- App Execution ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing {file.name}..."):
            text = extract_text(file)
            mind_map = get_mind_map(text)
            summary = generate_summary(text)
            questions = generate_questions(text)
            flashcards = generate_flashcards(text)
            mnemonics = generate_mnemonics(text)
            key_terms = generate_key_terms(text)
            cheatsheet = generate_cheatsheet(text)
            highlights = generate_highlights(text)

        st.markdown(f"---\n## 📄 {file.name}")
        if mind_map:
            st.subheader("🧠 Mind Map")
            plot_mind_map(mind_map["nodes"], mind_map["edges"])
        else:
            st.error("Mind map generation failed.")

        st.subheader("📌 Summary")
        render_response(summary)

        st.subheader("📝 Quiz Questions")
        render_response(questions)

        with st.expander("📚 Flashcards"):
            render_response(flashcards)
        with st.expander("🧠 Mnemonics"):
            render_response(mnemonics)
        with st.expander("🔑 Key Terms"):
            render_response(key_terms)
        with st.expander("📋 Cheat Sheet"):
            render_response(cheatsheet)
        with st.expander("⭐ Highlights"):
            render_response(highlights)
else:
    st.info("Upload a document to get started.")
