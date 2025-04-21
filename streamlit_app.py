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
  <!-- Loader Screen -->
  <div id="loader">
    <div class="mascot"></div>
    <div id="progress">Loading... 0%</div>
  </div>
  <script>
    let progress = 0;
    const progressText = document.getElementById('progress');
    // Update interval set to 550ms for a total of ~55 seconds to reach 100%
    const interval = setInterval(() => {
      progress = (progress + 1) % 101;  // Loop progress from 0 to 100 repeatedly
      progressText.textContent = `Loading... ${progress}%`;
    }, 550);
    
    // Clear the interval when loader is removed
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

# --- Generate Mind Map JSON ---
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
        cleaned = re.sub(r",\s*([}\]])", r"\1", json_data.group(0))
        parsed = json.loads(cleaned)
        if "nodes" not in parsed or "edges" not in parsed:
            raise ValueError("Response missing 'nodes' or 'edges'.")
        return parsed
    except Exception as e:
        st.error(f"Mind map JSON parsing failed: {e}")
        st.code(response)
        return None

# --- Plot Mind Map with Plotly Export ---
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
    return call_gemini(f"Summarize this for an exam and separately list all the formulae that are mentioned in the text and define the terms therein. If there aren't any, skip this section:\n\n{text}", temperature=0.5)
def generate_questions(text): 
    return call_gemini(f"Generate 15 quiz questions for an exam (ignore authors, ISSN, etc.):\n\n{text}")
def generate_flashcards(text): 
    return call_gemini(f"Create flashcards (Q&A):\n\n{text}")
def generate_mnemonics(text): 
    return call_gemini(f"Generate mnemonics:\n\n{text}")
def generate_key_terms(text): 
    return call_gemini(f"List all key terms in the text, with definitions:\n\n{text}")
def generate_cheatsheet(text): 
    return call_gemini(f"Create a cheat sheet:\n\n{text}")
def generate_highlights(text): 
    return call_gemini(f"List key facts and highlights:\n\n{text}")
def critical_concepts(text):
        return call_gemini(f"Dumb down the critical concepts in the text so that I am ready for questions in the exam:\n\n{text}")

# --- Display Helper ---
def render_section(title, content):
    st.subheader(title)
    if content.strip().startswith("<"):
        components.html(content, height=600, scrolling=True)
    else:
        st.markdown(content, unsafe_allow_html=True)

# --- Main Logic ---
if uploaded_files:
    # Create a placeholder for the interactive loader, visible until first file processing completes.
    loader_placeholder = st.empty()
    with loader_placeholder:
        components.html(loader_html, height=600)
    
    first_file_processed = False  # track if the first file's output has been displayed

    for file in uploaded_files:
        st.markdown(f"---\n## 📄 {file.name}")
        text = extract_text(file)
        mind_map = get_mind_map(text)
        summary = generate_summary(text)
        questions = generate_questions(text)
        flashcards = generate_flashcards(text)
        mnemonics = generate_mnemonics(text)
        key_terms = generate_key_terms(text)
        cheatsheet = generate_cheatsheet(text)
        highlights = generate_highlights(text)
        critical_concepts = critical_concepts(text)

        if mind_map:
            st.subheader("🧠 Mind Map (ChatGPT can't do this)")
            plot_mind_map(mind_map["nodes"], mind_map["edges"])
        else:
            st.error("Mind map generation failed.")

        render_section("📌 Summary", summary)
        render_section("📝 Quiz Questions (You gotta ask ChatGPT for this, we do it anyways)", questions)
        with st.expander("📚 Flashcards (Wonder what this is? ChatGPT don't do it, do they?)"):
            render_section("Flashcards", flashcards)
        with st.expander("🧠 Mnemonics (Still working on this)"):
            render_section("Mnemonics", mnemonics)
        with st.expander("🔑 Key Terms (We'll let ChatGPT come at par with us for this one)"):
            render_section("Key Terms", key_terms)
        with st.expander("📋 Cheat Sheet (Chug a coffee and run through this, you're golden for the exam!)"):
            render_section("Cheat Sheet", cheatsheet)
        with st.expander("⭐ Highlights (everything important in a single place, just for you <3)"):
            render_section("Highlights", highlights)
        with st.expander("All the critical concepts in a crisp bite for you"):
            render_section("Critical Concepts", critical_concepts)
        
        # Remove the loader after processing the first file.
        if not first_file_processed:
            loader_placeholder.empty()
            first_file_processed = True
else:
    st.info("Upload a document to get started.")
