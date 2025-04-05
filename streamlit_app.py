import streamlit as st
import cohere
import fitz  # PyMuPDF for PDFs
import docx
import json
import re
from io import StringIO
import igraph as ig
import plotly.graph_objects as go
import requests

# --- Page Config ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.caption("Upload materials to generate a concept map, summary, and quiz. Ask your doubts below!")

# --- Load API Clients ---
co = cohere.Client(st.secrets["cohere_api_key"])
SERP_API_KEY = st.secrets["serp_api_key"]

# --- Upload Files ---
uploaded_files = st.file_uploader(
    "📤 Upload documents (PDF, DOCX, TXT)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)

# --- Text Extraction ---
def extract_text(file):
    if file.name.endswith(".pdf"):
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            return "".join([page.get_text() for page in doc])
    elif file.name.endswith(".docx"):
        doc_obj = docx.Document(file)
        return "\n".join(p.text for p in doc_obj.paragraphs)
    elif file.name.endswith(".txt"):
        return StringIO(file.getvalue().decode("utf-8")).read()
    return ""

# --- Cohere Prompt Functions ---
def cohere_generate(prompt, temperature=0.5):
    return co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=temperature
    ).generations[0].text.strip()

def get_concept_map(text):
    prompt = f"""
You are an AI that converts text into a concept map in JSON format.
Each node should include a "title" and a "description".

Format:
{{
  "topic": {{
    "title": "Main Topic",
    "description": "Description of the main topic."
  }},
  "subtopics": [
    {{
      "title": "Subtopic A",
      "description": "Description for Subtopic A.",
      "children": [
        {{
          "title": "Point A1",
          "description": "Description for Point A1."
        }}
      ]
    }}
  ]
}}

Text:
{text}
"""
    try:
        raw_output = cohere_generate(prompt)
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        st.error("❌ Could not extract valid JSON.")
        st.code(raw_output)
    except Exception as e:
        st.error("❌ Failed to parse concept map.")
    return None

def generate_summary(text):
    return cohere_generate(f"Summarize this in 5-7 bullet points:\n\n{text[:4000]}")

def generate_questions(text):
    return cohere_generate(f"Generate 5 educational quiz questions based on this content:\n\n{text[:4000]}", temperature=0.7)

# --- Concept Map Visualization ---
def build_igraph_graph(concept_json):
    vertices, edges = [], []

    def walk(node, parent_id=None):
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        vertices.append({
            "id": node_id,
            "label": node["title"],
            "description": node.get("description", "No description.")
        })
        if parent_id:
            edges.append((parent_id, node_id))
        for child in node.get("children", []):
            walk(child, node_id)

    root = {
        "title": concept_json["topic"]["title"],
        "description": concept_json["topic"]["description"],
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
    coords = layout.coords

    edge_x, edge_y = [], []
    for src, tgt in g.get_edgelist():
        x0, y0 = coords[src]
        x1, y1 = coords[tgt]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]

    node_x, node_y, hover_texts = [], [], []
    for i, v in enumerate(g.vs):
        x, y = coords[i]
        node_x.append(x)
        node_y.append(y)
        hover_texts.append(f"<b>{v['label']}</b><br>{v['description']}")

    fig = go.Figure(data=[
        go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none'),
        go.Scatter(x=node_x, y=node_y, mode='markers+text', text=g.vs["label"],
                   textposition="top center", hovertext=hover_texts, hoverinfo='text',
                   marker=dict(color='#00cc96', size=20, line_width=2))
    ], layout=go.Layout(
        title=dict(text='Interactive Mind Map', font=dict(size=16)),
        hovermode='closest',
        margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    ))

    return fig

# --- Doubt Solving ---
def search_serp(query):
    res = requests.get("https://serpapi.com/search", params={
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "en",
        "gl": "us"
    })
    if res.ok:
        return " ".join(result.get("snippet", "") for result in res.json().get("organic_results", [])[:3])
    return ""

def answer_doubt(question):
    context = search_serp(question)
    prompt = f"""
You are a math tutor. Explain the answer to this question step-by-step.

Question: {question}
Context: {context}

Give a clear and rigorous answer with examples.
"""
    return cohere_generate(prompt)

# --- Main Processing ---
def process_file(file):
    text = extract_text(file)
    return {
        "filename": file.name,
        "text": text,
        "concept_map": get_concept_map(text),
        "summary": generate_summary(text),
        "quiz": generate_questions(text)
    }

# --- Display Results ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"🔍 Processing: {file.name}"):
            result = process_file(file)
            st.markdown(f"---\n## 📄 Document: {result['filename']}")

            if result["concept_map"]:
                graph = build_igraph_graph(result["concept_map"])
                fig = plot_igraph_graph(graph)
                st.subheader("🧠 Concept Map")
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("📌 Raw JSON"):
                    st.json(result["concept_map"])
            else:
                st.error("❌ Concept map generation failed.")

            st.subheader("📝 Summary")
            st.markdown(result["summary"])

            st.subheader("🧪 Quiz Questions")
            st.markdown(result["quiz"])
else:
    st.info("📂 Upload documents above to get started.")

# --- Doubt Section ---
st.markdown("---")
st.header("❓ Ask a Doubt")
question = st.text_input("💬 Enter your math or learning question here:")
if st.button("🧠 Get Answer") and question:
    with st.spinner("🔍 Getting your answer..."):
        answer = answer_doubt(question)
    st.subheader("📘 Answer")
    st.markdown(answer)
