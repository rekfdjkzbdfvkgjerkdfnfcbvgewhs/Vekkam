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
from gtts import gTTS
import tempfile
import base64

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
    name = file.name.lower()
    if name.endswith(".pdf"):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            return "".join(page.get_text() for page in doc)
    elif name.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(file).paragraphs)
    elif name.endswith(".pptx"):
        return "\n".join(shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape, "text"))
    elif name.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    elif name.endswith((".jpg", ".jpeg", ".png")):
        return pytesseract.image_to_string(Image.open(file))
    return ""

# --- Gemini API Call ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.secrets['gemini_api_key']}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
    }

    for attempt in range(3):
        res = requests.post(url, headers=headers, json=payload)
        if res.status_code == 200:
            try:
                return res.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                return f"<p>Error parsing response: {e}</p>"
        elif res.status_code == 429 and attempt < 2:
            st.warning("Rate limit hit. Retrying in 30s...")
            time.sleep(30)
        else:
            break
    return f"<p>Gemini API error {res.status_code}: {res.text}</p>"

# --- Audio Generation ---
def generate_podcast_audio(text, lang="en", slow=False):
    try:
        tts = gTTS(text=text, lang=lang, slow=slow)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts.save(fp.name)
            return fp.name
    except Exception as e:
        st.error(f"Podcast generation failed: {e}")
        return None

# --- Mind Map Generation ---
def get_mind_map(text):
    prompt = f"""
You are an assistant that creates a JSON mind map from the text below.

Structure:
{{
  "nodes": [{{"id": "1", "label": "Label", "description": "Short definition"}}],
  "edges": [{{"source": "1", "target": "2"}}]
}}

- Output valid JSON only.
- No markdown or commentary.
- Include short definitions.
- Keep it minimal and test-ready.
- Generate 7 nodes, 5 children each.
- Add quiz questions for any formulas.

Text:
{text}
"""
    response = call_gemini(prompt, temperature=0.5)
    try:
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if not match:
            raise ValueError("No JSON block found.")
        cleaned = re.sub(r",\s*([}\]])", r"\1", match.group(0))
        parsed = json.loads(cleaned)
        if "nodes" not in parsed or "edges" not in parsed:
            raise ValueError("Missing 'nodes' or 'edges'")
        return parsed
    except Exception as e:
        st.error(f"Mind map JSON parsing failed: {e}")
        st.code(response)
        return None

# --- Render Podcast Section ---
def render_podcast_section(text):
    st.subheader("🎙️ AI Podcast")
    st.caption("Your study notes, as a podcast. Shareable, listenable, repeatable.")
    if st.button("Generate Podcast"):
        with st.spinner("Creating your audio..."):
            path = generate_podcast_audio(text)
            if path:
                audio_bytes = open(path, "rb").read()
                b64 = base64.b64encode(audio_bytes).decode()
                st.markdown(f"""
                    <audio controls autoplay>
                        <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
                        Your browser does not support the audio element.
                    </audio>
                    <br><a download="vekkam_podcast.mp3" href="data:audio/mp3;base64,{b64}">📥 Download Podcast</a>
                """, unsafe_allow_html=True)

# --- Plot Mind Map ---
def plot_mind_map(nodes, edges):
    if len(nodes) < 2:
        st.warning("Mind map needs at least 2 nodes.")
        return

    id_to_index = {n['id']: i for i, n in enumerate(nodes)}
    g = ig.Graph(directed=True)
    g.add_vertices(len(nodes))
    valid_edges = [(id_to_index[e['source']], id_to_index[e['target']]) for e in edges if e['source'] in id_to_index and e['target'] in id_to_index]
    g.add_edges(valid_edges)
    layout = g.layout("kk") if g.layout("kk") else g.layout("fr")

    scale = 3
    edge_x, edge_y = [], []
    for e in g.es:
        x0, y0 = layout[e.source]
        x1, y1 = layout[e.target]
        edge_x += [x0 * scale, x1 * scale, None]
        edge_y += [y0 * scale, y1 * scale, None]

    node_x, node_y, labels = [], [], []
    for i, node in enumerate(nodes):
        x, y = layout[i]
        node_x.append(x * scale)
        node_y.append(y * scale)
        labels.append(f"<b>{node['label']}</b><br>{node.get('description', '')}")

    fig = go.Figure(data=[
        go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none'),
        go.Scatter(
            x=node_x, y=node_y, mode='markers+text',
            text=[n['label'] for n in nodes], textposition="top center",
            marker=dict(size=20, color='#00cc96', line_width=2),
            hoverinfo='text', hovertext=labels
        )
    ])
    fig.update_layout(
        title="🧠 Mind Map (ChatGPT can't do this)",
        width=1200, height=800, hovermode='closest',
        xaxis=dict(showgrid=False, zeroline=False), yaxis=dict(showgrid=False, zeroline=False)
    )
    components.html(fig.to_html(full_html=False, include_plotlyjs='cdn'), height=900, scrolling=True)

# --- Learning Aids ---
def generate_summary(text): return call_gemini(f"Summarize for exams. Also list formulae if any:\n\n{text}", 0.5)
def generate_questions(text): return call_gemini(f"Create 15 quiz questions (ignore citations, ISSN, etc.):\n\n{text}")
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A):\n\n{text}")
def generate_mnemonics(text): return call_gemini(f"Create mnemonics:\n\n{text}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms with definitions:\n\n{text}")
def generate_cheatsheet(text): return call_gemini(f"Make a cheat sheet:\n\n{text}")
def generate_highlights(text): return call_gemini(f"List highlights and key facts:\n\n{text}")
def generate_podcast(text): return call_gemini(f"You're a podcaster. Deep dive this in story tone. Use headers. Make it fun:\n\n{text}")

# --- Display Helper ---
def render_section(title, content):
    st.subheader(title)
    if content.strip().startswith("<"):
        components.html(content, height=600, scrolling=True)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
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
            render_podcast_section(text)

        st.markdown(f"---\n## 📄 {file.name}")
        if mind_map:
            st.subheader("🧠 Mind Map (ChatGPT can't do this)")
            plot_mind_map(mind_map["nodes"], mind_map["edges"])
        else:
            st.error("Mind map generation failed.")

        render_section("📌 Summary", summary)
        render_section("📝 Quiz Questions (You gotta ask ChatGPT for this, we do it anyways)", questions)
        with st.expander("📚 Flashcards (Wonder what this is? ChatGPT don’t do it, do they?)"):
            render_section("Flashcards", flashcards)
        with st.expander("🧠 Mnemonics (Still working on this)"):
            render_section("Mnemonics", mnemonics)
        with st.expander("🔑 Key Terms (We'll let ChatGPT come at par with us for this one)"):
            render_section("Key Terms", key_terms)
        with st.expander("📋 Cheat Sheet (Chug a coffee and run through this, you're golden for the exam!)"):
            render_section("Cheat Sheet", cheatsheet)
        with st.expander("⭐ Highlights (Everything important in a single place, just for you <3)"):
            render_section("Highlights", highlights)
