import streamlit as st
import cohere
import fitz  # PyMuPDF
import docx
import json
from io import StringIO
from streamlit_cytoscapejs import cytoscape

# --- Page Config ---
st.set_page_config(page_title="KnowMap AI", layout="wide")
st.title("📘 KnowMap – AI-Powered Interactive Mind Maps")

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
    ...
  ]
}}

Text:
{text[:4000]}
"""
    response = co.generate(
        model="command-r",
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

def build_cytoscape_elements(concept_json):
    nodes, edges = [], []
    def walk(node, parent=None):
        node_id = node["title"].replace(" ", "_") + str(len(nodes))
        nodes.append({"data": {"id": node_id, "label": node["title"]}})
        if parent:
            edges.append({"data": {"source": parent, "target": node_id}})
        for child in node.get("children", []):
            walk(child, node_id)
    walk({"title": concept_json["topic"], "children": concept_json["subtopics"]})
    return nodes, edges

def generate_questions(text):
    prompt = f"""Generate 5 educational questions based on this content:\n\n{text[:4000]}"""
    response = co.generate(
        model="command-r",
        prompt=prompt,
        max_tokens=400,
        temperature=0.7
    )
    return response.generations[0].text.strip()

def generate_summary(text):
    prompt = f"Summarize the following in 5-7 bullet points:\n\n{text[:4000]}"
    response = co.generate(
        model="command-r",
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
        nodes, edges = build_cytoscape_elements(concept_json)
        st.subheader("🌐 Interactive Mind Map")
        cytoscape(
            elements=nodes + edges,
            layout={"name": "breadthfirst"},
            style={"width": "100%", "height": "600px"},
        )

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
