import streamlit as st
import cohere
import fitz  # PyMuPDF
import docx
import json
import re
from io import StringIO
import igraph as ig
import plotly.graph_objects as go
import requests
from PIL import Image
import pytesseract
from pptx import Presentation  # For PPTX support

# --- Page Config ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.caption("After the uploaded material is all processed, you can ask your doubts in the panel below.")

# --- Load API Clients ---
co = cohere.Client(st.secrets["cohere_api_key"])
SERP_API_KEY = st.secrets["serp_api_key"]

# --- Upload Files ---
uploaded_files = st.file_uploader(
    "Upload documents or images (PDF, DOCX, TXT, PPTX, JPG, PNG)",
    type=["pdf", "docx", "txt", "pptx", "jpg", "jpeg", "png"],
    accept_multiple_files=True
)

# --- Extract Text Function ---
def extract_text(file):
    extension = file.name.lower().split('.')[-1]

    if extension == "pdf":
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            return "\n".join(page.get_text() for page in doc)

    elif extension == "docx":
        return "\n".join(p.text for p in docx.Document(file).paragraphs)

    elif extension == "txt":
        return StringIO(file.getvalue().decode("utf-8")).read()

    elif extension == "pptx":
        prs = Presentation(file)
        slides_text = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    slides_text.append(shape.text)
        return "\n".join(slides_text)

    elif extension in ["jpg", "jpeg", "png"]:
        image = Image.open(file)
        return pytesseract.image_to_string(image)

    return ""

# --- Concept Map Generation ---
def get_concept_map(text):
    prompt = f"""You are an AI that converts text into a concept map in JSON... [Prompt continues as original]"""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.5
    )
    try:
        raw_text = response.generations[0].text.strip()
        json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        else:
            st.error("Error detected, please stand by...")
    except Exception:
        st.error("❌ Failed to parse concept map.")
        st.code(response.generations[0].text)
    return None

# --- Graph Construction & Plotting ---
def build_igraph_graph(concept_json):
    vertices, edges = [], []
    def walk(node, parent=None):
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        vertices.append({"id": node_id, "label": node['title'], "description": node.get('description', '')})
        if parent:
            edges.append((parent, node_id))
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
    coords = layout.coords
    edge_x, edge_y = [], []
    for edge in g.es:
        x0, y0 = coords[edge.source]
        x1, y1 = coords[edge.target]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines', line=dict(width=1, color='#888'), hoverinfo='none')
    node_x, node_y, hover_texts = [], [], []
    for i, v in enumerate(g.vs):
        x, y = coords[i]
        node_x.append(x)
        node_y.append(y)
        hover_texts.append(f"<b>{v['label']}</b><br>{v['description']}")
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers+text', text=g.vs["label"],
        textposition="top center",
        marker=dict(size=20, color='#00cc96', line_width=2),
        hoverinfo='text', hovertext=hover_texts
    )
    return go.Figure(data=[edge_trace, node_trace], layout=go.Layout(
        title=dict(text='📌 Interactive Mind Map', font=dict(size=16)),
        hovermode='closest', showlegend=False,
        margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
    ))

# --- Summary, Questions, Search, and Doubt Answering ---
def generate_summary(text):
    prompt = f"Summarize the following in 5-7 bullet points:\n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=2000).generations[0].text.strip()

def generate_questions(text):
    prompt = f"Generate 15 educational quiz questions based on this content:\n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=2000).generations[0].text.strip()

def search_serp(query):
    params = {"engine": "google", "q": query, "api_key": SERP_API_KEY, "hl": "en", "gl": "us"}
    res = requests.get("https://serpapi.com/search", params=params)
    if res.status_code == 200:
        return " ".join(result.get("snippet", "") for result in res.json().get("organic_results", [])[:3])
    return ""

def answer_doubt(question):
    context = search_serp(question)
    prompt = f"""You are an expert tutor. Answer the following question... [Prompt continues as original]"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000).generations[0].text.strip()

def display_answer(answer):
    try:
        st.json(json.loads(answer))
        return
    except json.JSONDecodeError:
        pass
    if re.search(r'<[^>]+>', answer):
        st.markdown(answer, unsafe_allow_html=True)
    elif answer.strip().startswith(r"\min"):
        st.latex(answer.strip())
    elif (matrix := re.search(r"(\\left\(.*?\\right\))", answer, re.DOTALL)):
        st.markdown(answer.replace(matrix.group(1), ""))
        st.latex(matrix.group(1))
    else:
        st.markdown(answer)

# --- Process and Render Each File ---
def process_file(file):
    text = extract_text(file)
    concept_json = get_concept_map(text)
    summary = generate_summary(text)
    quiz = generate_questions(text)
    return file.name, text, concept_json, summary, quiz

# --- Main Logic ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing: {file.name}"):
            name, text, concept_json, summary, quiz = process_file(file)
            st.markdown(f"---\n## Document: {name}")
            if concept_json:
                graph = build_igraph_graph(concept_json)
                st.plotly_chart(plot_igraph_graph(graph), use_container_width=True)
                with st.expander("📌 Concept Map JSON"):
                    st.json(concept_json)
            else:
                st.error("Concept map generation failed.")
            st.subheader("📄 Summary")
            st.markdown(summary)
            st.subheader("❓ Quiz Questions")
            st.markdown(quiz)

# --- Doubt Panel ---
st.markdown("---")
st.subheader("❓ Ask a Doubt")
query = st.text_input("Type your question here")
if query:
    with st.spinner("Thinking..."):
        answer = answer_doubt(query)
        display_answer(answer)
