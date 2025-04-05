import streamlit as st
import cohere
import fitz  # PyMuPDF for PDFs
import docx
import json
from io import StringIO
import igraph as ig
import plotly.graph_objects as go

# --- Page Config ---
st.set_page_config(page_title="KnowMap AI", layout="wide")
st.title("📘 KnowMap – AI-Powered Interactive Mind Maps (Using igraph)")

# --- Load Cohere ---
co = cohere.Client(st.secrets["cohere_api_key"])

# --- Upload Files ---
uploaded_files = st.file_uploader("Upload documents (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True)

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
    prompt = f"""You are an AI that converts text into a concept map in JSON. Output should be like:
{{
  "topic": "Main Topic",
  "subtopics": [
    {{
      "title": "Subtopic A",
      "children": [{{"title": "Point A1"}}, {{"title": "Point A2"}}]
    }},
    {{
      "title": "Subtopic B",
      "children": [{{"title": "Point B1"}}, {{"title": "Point B2"}}]
    }}
  ]
}}

Text:
{text[:4000]}
"""
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=800,
        temperature=0.5
    )
    try:
        json_text = response.generations[0].text.strip("`").strip()
        return json.loads(json_text)
    except Exception as e:
        st.error("❌ Could not parse concept map JSON.")
        st.code(response.generations[0].text)
        return None

def build_igraph_graph(concept_json):
    """
    Build an igraph Graph from the hierarchical concept JSON.
    Returns the igraph Graph object.
    """
    vertices = []
    edges = []
    
    def walk(node, parent_id=None):
        # Create a unique id for each node (using the title and current length)
        node_id = f"{node['title'].replace(' ', '_')}_{len(vertices)}"
        vertices.append({"id": node_id, "label": node["title"]})
        if parent_id is not None:
            edges.append((parent_id, node_id))
        for child in node.get("children", []):
            walk(child, node_id)
    
    # Root node from the top-level "topic" and its children (from "subtopics")
    root = {"title": concept_json["topic"], "children": concept_json["subtopics"]}
    walk(root)
    
    # Create the igraph Graph
    g = ig.Graph(directed=True)
    g.add_vertices([v["id"] for v in vertices])
    g.vs["label"] = [v["label"] for v in vertices]
    if edges:
        g.add_edges(edges)
    return g

def plot_igraph_graph(g):
    """
    Compute a layout for the graph using igraph and create an interactive Plotly figure.
    """
    layout = g.layout("fr")  # Fruchterman-Reingold layout
    coords = layout.coords  # list of (x, y) tuples
    
    # Build edge traces
    edge_x = []
    edge_y = []
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
    
    # Build node traces
    node_x = []
    node_y = []
    node_text = []
    for i, vertex in enumerate(g.vs):
        x, y = coords[i]
        node_x.append(x)
        node_y.append(y)
        node_text.append(vertex["label"])
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=node_text,
        textposition="top center",
        marker=dict(
            showscale=False,
            color='#00cc96',
            size=20,
            line_width=2
        ),
        hoverinfo='text'
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
        max_tokens=400,
        temperature=0.7
    )
    return response.generations[0].text.strip()

def generate_summary(text):
    prompt = f"Summarize the following in 5-7 bullet points:\n\n{text[:4000]}"
    response = co.generate(
        model="command",
        prompt=prompt,
        max_tokens=300,
        temperature=0.5
    )
    return response.generations[0].text.strip()

# --- Main Logic ---
if uploaded_files:
    combined_text = ""
    for file in uploaded_files:
        st.success(f"✅ Loaded: {file.name}")
        combined_text += extract_text(file) + "\n"
    
    with st.spinner("🧠 Generating concept map using Cohere..."):
        concept_json = get_concept_map(combined_text)
    
    if concept_json:
        # Build igraph graph from the concept JSON
        g = build_igraph_graph(concept_json)
        with st.spinner("🖼️ Computing interactive layout..."):
            fig = plot_igraph_graph(g)
        st.subheader("🌐 Interactive Mind Map (igraph + Plotly)")
        st.plotly_chart(fig, use_container_width=True)
        
        with st.expander("📌 Concept Map JSON"):
            st.json(concept_json)
        
        with st.spinner("📚 Generating summary..."):
            summary = generate_summary(combined_text)
        st.subheader("📝 Summary")
        st.markdown(summary)
        
        with st.spinner("🧪 Generating quiz questions..."):
            questions = generate_questions(combined_text)
        st.subheader("🧠 Quiz Questions")
        st.markdown(questions)
else:
    st.info("Upload documents above to begin.")
