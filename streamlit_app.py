import streamlit as st
import cohere
import fitz  # PyMuPDF for PDFs
import docx
import json
import re
from io import StringIO
from PIL import Image
import pytesseract
import plotly.graph_objects as go
import igraph as ig
import requests
from pptx import Presentation  # For PPTX support

# --- Page Config ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.title("Vekkam - the Study Buddy of Your Dreams")
st.text("Review summaries, flashcards, cheat sheets, and more to reinforce your learning.")

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
Make the mind map as detailed as possible in terms of scope but keep the definitions concise. They're for an exam. Keep more branches and short definitons.
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

    try:
        match = re.search(r'\{.*\}', raw_output, re.DOTALL)
        if not match:
            raise ValueError("No JSON-like content found.")
        json_str = match.group(0)
        json_str = re.sub(r",\s*}", "}", json_str)  # Remove trailing commas
        json_str = re.sub(r",\s*]", "]", json_str)
        json_str = re.sub(r'“|”', '"', json_str)    # Replace smart quotes
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

    edge_trace = go.Scatter(x=edge_x, y=edge_y, mode='lines',
                            line=dict(width=1, color='#888'), hoverinfo='none')

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

# --- Additional Note-Taking and Memory Aid Features ---

def generate_summary(text):
    prompt = f"Summarize this for an exam I have: \n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=2000).generations[0].text.strip()

def generate_questions(text):
    prompt = f"Generate 15 educational quiz questions from the following text:\n\n{text[:4000]}"
    return co.generate(model="command", prompt=prompt, max_tokens=2000).generations[0].text.strip()

def generate_flashcards(text):
    prompt = f"""Create flashcards from the following content.
Each flashcard should have a "question" and an "answer".\n\n{text[:4000]}
Text:
"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000, temperature=0.7).generations[0].text.strip()

def generate_mnemonics(text):
    prompt = f"""Based on the following text, generate mnemonics to help remember the key points.\n\n{text[:4000]}
Text:
"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000, temperature=0.7).generations[0].text.strip()

def generate_key_terms(text):
    prompt = f"""Extract 10 key terms from the following text along with a brief definition for each.\n\n{text[:4000]}
Text:
{text[:4000]}
"""
    return co.generate(model="command", prompt=prompt, max_tokens=1500, temperature=0.7).generations[0].text.strip()

def generate_cheatsheet(text):
    prompt = f"""Generate a cheat sheet from the following content.
Include bullet points for essential facts, formulas, and definitions that a student should quickly review.\n\n{text[:4000]}
Text:
"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000, temperature=0.7).generations[0].text.strip()

def generate_highlights(text):
    prompt = f"""Identify and list key sentences or statements from the following text that best summarize the most important points.\n\n{text[:4000]}
Text:
"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000, temperature=0.7).generations[0].text.strip()

# --- Process Each File ---
def process_file(file):
    text = extract_text(file)
    concept_json = get_concept_map(text)
    summary = generate_summary(text)
    questions = generate_questions(text)
    flashcards = generate_flashcards(text)
    mnemonics = generate_mnemonics(text)
    key_terms = generate_key_terms(text)
    cheatsheet = generate_cheatsheet(text)
    highlights = generate_highlights(text)
    return file.name, text, concept_json, summary, questions, flashcards, mnemonics, key_terms, cheatsheet, highlights

# --- Main App Logic ---
if uploaded_files:
    for file in uploaded_files:
        with st.spinner(f"Processing: {file.name}"):
            (name, text, concept_json, summary, questions, flashcards,
             mnemonics, key_terms, cheatsheet, highlights) = process_file(file)
            st.markdown(f"---\n## Document: {name}")

            # Display Concept Map & Mind Map
            if concept_json:
                g = build_igraph_graph(concept_json)
                fig = plot_igraph_graph(g)
                st.subheader("🧠 Interactive Mind Map")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Concept map generation failed.")

            # Display Summary and Quiz Questions
            st.subheader("📌 Summary")
            st.markdown(summary)
            st.subheader("📝 Quiz Questions")
            st.markdown(questions)

            # Display Additional Memory Aids
            with st.expander("Flashcards"):
                st.markdown(flashcards)
            with st.expander("Mnemonics"):
                st.markdown(mnemonics)
            with st.expander("Key Terms"):
                st.markdown(key_terms)
            with st.expander("Cheat Sheet"):
                st.markdown(cheatsheet)
            with st.expander("Highlighted Key Points"):
                st.markdown(highlights)
else:
    st.info("Upload documents above to begin.")

# --- Doubt Solver Section ---
st.markdown("---")
st.header("Ask a Doubt")

doubt_mode = st.radio("How would you like to provide your doubt?", ["Type Doubt", "Upload Doubt"])
doubt_text = ""
if doubt_mode == "Type Doubt":
    doubt_text = st.text_area("Enter your doubt here:")
elif doubt_mode == "Upload Doubt":
    doubt_image = st.file_uploader("Upload an image file containing your doubt", type=["jpg", "jpeg", "png"], key="doubt_image")
    if doubt_image:
        doubt_text = extract_text(doubt_image)

def search_serp(query):
    params = {"engine": "google", "q": query, "api_key": SERP_API_KEY, "hl": "en", "gl": "us"}
    res = requests.get("https://serpapi.com/search", params=params)
    if res.status_code == 200:
        snippets = [result.get("snippet", "") for result in res.json().get("organic_results", [])[:3]]
        return " ".join(snippets)
    return ""

def answer_doubt(question):
    context = search_serp(question)
    prompt = f"""You are an expert tutor. Answer the following question with detailed explanations and step-by-step reasoning.

Question: {question}

Context: {context}

Include examples and, if needed, LaTeX for mathematical expressions.
"""
    return co.generate(model="command", prompt=prompt, max_tokens=2000, temperature=0.5).generations[0].text.strip()

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

if st.button("Get Answer") and doubt_text:
    with st.spinner("🔍 Searching for context and generating answer..."):
        answer = answer_doubt(doubt_text)
    st.subheader("Answer")
    display_answer(answer)
