import streamlit as st
import cohere
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
from pptx import Presentation  # For .pptx support

# --- Page Config ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.text("After the uploaded material is all processed, you can ask your doubts in the panel below.")

# --- Load API Clients ---
co = cohere.Client(st.secrets["cohere_api_key"])
SERP_API_KEY = st.secrets["serp_api_key"]

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
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text

    elif ext.endswith(".docx"):
        doc_obj = docx.Document(file)
        return "\n".join([p.text for p in doc_obj.paragraphs])

    elif ext.endswith(".pptx"):
        prs = Presentation(file)
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text

    elif ext.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()

    elif ext.endswith((".jpg", ".jpeg", ".png")):
        image = Image.open(file)
        return pytesseract.image_to_string(image)

    return ""

# --- Cohere API: Get Concept Map JSON ---
def get_concept_map(text):
    prompt = f"""You are an AI that converts text into a JSON concept map.

Follow exactly this structure:
{{
  "topic": {{
    "title": "Main Topic",
    "description": "Short overview"
  }},
  "subtopics": [
    {{
      "title": "Subtopic A",
      "description": "Explanation",
      "children": [
        {{
          "title": "Child 1",
          "description": "Explanation"
        }}
      ]
    }}
  ]
}}

Text:
{text}
"""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.5
    )

    raw_output = response.generations[0].text.strip()

    # Attempt to extract JSON-like content
    try:
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not match:
            raise ValueError("No JSON-like content found.")

        json_str = match.group(0)

        # Fix common formatting issues
        json_str = re.sub(r",\s*}", "}", json_str)  # trailing commas before }
        json_str = re.sub(r",\s*]", "]", json_str)  # trailing commas before ]
        json_str = re.sub(r'“|”', '"', json_str)    # smart quotes to normal quotes

        data = json.loads(json_str)

        if "topic" not in data or "title" not in data["topic"]:
            raise ValueError("Missing 'topic' in concept map.")

        return data

    except Exception as e:
        st.error(f"Concept map generation failed: {e}")
        st.code(raw_output)
        return None

# --- Build and Plot Graph ---
def build_igraph_graph(concept_json):
    vertices = []
    edges = []

    def walk(node, parent_id=None):
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        description = node.get("description", "")
        vertices.append({"id": node_id, "label": node["title"], "description": description})
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
        textposition="top center",
        marker=dict(size=20, color='#00cc96', line_width=2),
        hoverinfo='text', hovertext=texts
    )

    return go.Figure(data=[edge_trace, node_trace],
                     layout=go.Layout(title="Interactive Mind Map", hovermode='closest',
                                      xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                                      yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)))

# --- Other Features ---
def generate_summary(text):
    prompt = f"Summarize this in 5-7 bullet points:\n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=1000).generations[0].text.strip()

def generate_questions(text):
    prompt = f"Generate 15 educational quiz questions from the following text:\n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=1000).generations[0].text.strip()

# --- Main Logic ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing: {file.name}"):
            text = extract_text(file)
            concept_json = get_concept_map(text)
            summary = generate_summary(text)
            questions = generate_questions(text)

            st.markdown(f"---\n## Document: {file.name}")

            if concept_json:
                g = build_igraph_graph(concept_json)
                fig = plot_igraph_graph(g)
                st.subheader("🧠 Interactive Mind Map")
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("🧾 Concept Map JSON"):
                    st.json(concept_json)

            st.subheader("📌 Summary")
            st.markdown(summary)

            st.subheader("📝 Quiz Questions")
            st.markdown(questions)
