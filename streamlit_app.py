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
import concurrent.futures

# --- Page Config ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.text("After the uploaded material is all processed, you can ask your doubts in the panel below.")

# --- Load API Clients ---
co = cohere.Client(st.secrets["cohere_api_key"])
SERP_API_KEY = st.secrets["serp_api_key"]

# --- Upload Files ---
uploaded_files = st.file_uploader(
    "Upload documents (PDF, DOCX, TXT)",
    type=["pdf", "docx", "txt"],
    accept_multiple_files=True
)

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
Each node in the concept map should include a \"title\" and a \"description\" summarizing that part of the text.
Output should be in the following format:
{{
  \"topic\": {{
      \"title\": \"Main Topic\",
      \"description\": \"Description of the main topic.\"
  }},
  \"subtopics\": [
    {{
      \"title\": \"Subtopic A\",
      \"description\": \"Description for Subtopic A.\",
      \"children\": [
         {{
           \"title\": \"Point A1\",
           \"description\": \"Description for Point A1.\"
         }},
         {{
           \"title\": \"Point A2\",
           \"description\": \"Description for Point A2.\"
         }}
      ]
    }},
    {{
      \"title\": \"Subtopic B\",
      \"description\": \"Description for Subtopic B.\",
      \"children\": [
         {{
           \"title\": \"Point B1\",
           \"description\": \"Description for Point B1.\"
         }},
         {{
           \"title\": \"Point B2\",
           \"description\": \"Description for Point B2.\"
         }}
      ]
    }}
  ]
}}

Touch upon every aspect of the document given.
Stick to the format and output only the json response

Text:
{text}
"""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.5
    )
    try:
        raw_text = response.generations[0].text.strip("`").strip()
        json_match = re.search(r'(\{.*\})', raw_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
            return json.loads(json_text)
        else:
            st.error("❌ Could not extract JSON from the response.")
            st.code(raw_text)
            return None
    except Exception as e:
        st.error("❌ Could not parse concept map JSON.")
        st.code(response.generations[0].text)
        return None

def build_igraph_graph(concept_json):
    vertices = []
    edges = []

    def walk(node, parent_id=None):
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        description = node.get("description", "No description provided.")
        vertices.append({"id": node_id, "label": node["title"], "description": description})
        if parent_id is not None:
            edges.append((parent_id, node_id))
        for child in node.get("children", []):
            walk(child, node_id)

    root = {
        "title": concept_json["topic"]["title"],
        "description": concept_json["topic"].get("description", "No description provided."),
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
        src, tgt = edge.tuple
        x0, y0 = coords[src]
        x1, y1 = coords[tgt]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=1, color='#888'),
        hoverinfo='none',
        mode='lines'
    )
    node_x, node_y, hover_texts = [], [], []
    for i, vertex in enumerate(g.vs):
        x, y = coords[i]
        node_x.append(x)
        node_y.append(y)
        hover_texts.append(f"<b>{vertex['label']}</b><br>{vertex['description']}")
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=[v for v in g.vs["label"]],
        textposition="top center",
        marker=dict(
            showscale=False,
            color='#00cc96',
            size=20,
            line_width=2
        ),
        hoverinfo='text',
        hovertext=hover_texts
    )
    fig = go.Figure(
        data=[edge_trace, node_trace],
        layout=go.Layout(
            title=dict(text='<br>Interactive Mind Map', font=dict(size=16)),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20, l=5, r=5, t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    )
    return fig

def generate_questions(text):
    prompt = f"""Generate 5 educational quiz questions based on this content:\n\n{text[:4000]}"""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.7
    )
    return response.generations[0].text.strip()

def generate_summary(text):
    prompt = f"Summarize the following in 5-7 bullet points:\n\n{text[:4000]}"
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.5
    )
    return response.generations[0].text.strip()

def search_serp(query):
    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": "en",
        "gl": "us"
    }
    res = requests.get("https://serpapi.com/search", params=params)
    if res.status_code == 200:
        data = res.json()
        snippets = []
        for result in data.get("organic_results", [])[:3]:
            snippet = result.get("snippet", "")
            if snippet:
                snippets.append(snippet)
        return " ".join(snippets)
    return ""

def answer_doubt(question):
    context = search_serp(question)
    prompt = f"""You are an expert math tutor. Answer the following question with a detailed explanation and step-by-step math reasoning.

Question: {question}

Context: {context}

Provide a clear, rigorous answer with examples if necessary."""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=2000,
        temperature=0.5
    )
    return response.generations[0].text.strip()

def process_file(file):
    text = extract_text(file)
    concept_json = get_concept_map(text)
    summary = generate_summary(text)
    quiz = generate_questions(text)
    return file.name, text, concept_json, summary, quiz

# --- Main App Logic ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing: {file.name}"):
            filename, text, concept_json, summary, quiz = process_file(file)

            st.markdown(f"---\n## Document: {filename}")
            if concept_json:
                g = build_igraph_graph(concept_json)
                fig = plot_igraph_graph(g)
                st.subheader("Interactive Mind Map")
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("📌 Concept Map JSON"):
                    st.json(concept_json)
            else:
                st.error("Concept map generation failed for this document.")

            st.subheader("Summary")
            st.markdown(summary)
            st.subheader("Quiz Questions")
            st.markdown(quiz)
else:
    st.info("Upload documents above to begin.")

# --- Doubt Solver Section ---
st.markdown("---")
st.header("❓ Ask a Doubt")
question = st.text_input("Enter your math or learning question here:")
if st.button("Get Answer") and question:
    with st.spinner("🔍 Searching for context and generating answer..."):
        answer = answer_doubt(question)
    st.subheader("Answer")
    st.markdown(answer)
