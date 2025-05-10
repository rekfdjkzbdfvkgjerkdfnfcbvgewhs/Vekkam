import streamlit as st
import requests
import tempfile
from urllib.parse import urlencode
from PyPDF2 import PdfReader
import fitz
from io import StringIO
from PIL import Image
import pytesseract
import json
import igraph as ig
import plotly.graph_objects as go
import re

# --- Configuration using st.secrets ---
CLIENT_ID = st.secrets["google"]["client_id"]
CLIENT_SECRET = st.secrets["google"]["client_secret"]
REDIRECT_URI = st.secrets["google"]["redirect_uri"]
SCOPES = ["openid", "email", "profile"]
GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
CSE_API_KEY = st.secrets["google_search"]["api_key"]
CSE_ID = st.secrets["google_search"]["cse_id"]
CACHE_TTL = 3600

# --- Session State ---
for key in ['token', 'user', 'plan']:
    if key not in st.session_state:
        st.session_state[key] = None

# --- OAuth Login ---
def login_ui():
    st.title("Vekkam 📘")
    params = {
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent'
    }
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"
    st.markdown(f"[Login with Google]({auth_url})")
    code = st.text_input("Authorization code:")
    if st.button("Authenticate") and code:
        data = {
            'code': code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code'
        }
        res = requests.post('https://oauth2.googleapis.com/token', data=data).json()
        st.session_state['token'] = res
        userinfo = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f"Bearer {res['access_token']}"}
        ).json()
        st.session_state['user'] = userinfo

# --- Gemini Call ---
def call_gemini(prompt, temp=0.7, max_tokens=2048):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':temp,'maxOutputTokens':max_tokens}}
    res = requests.post(url, json=payload).json()
    return res['candidates'][0]['content']['parts'][0]['text']

# --- PDF Extraction ---
def extract_pages_from_url(pdf_url):
    resp = requests.get(pdf_url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    tmp.write(resp.content); tmp.flush()
    reader = PdfReader(tmp.name)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_pages_from_file(file):
    reader = PdfReader(file)
    return {i+1: reader.pages[i].extract_text() for i in range(len(reader.pages))}

def extract_text(file):
    ext = file.name.lower().split('.')[-1]
    if ext == 'pdf': return "\n".join(extract_pages_from_file(file).values())
    if ext in ['jpg','jpeg','png']: return pytesseract.image_to_string(Image.open(file))
    return StringIO(file.getvalue().decode()).read()

# --- Guide Book Search ---
def fetch_pdf_url(title, author, edition):
    q = ' '.join(filter(None, [title, author, edition]))
    params = {'key': CSE_API_KEY, 'cx': CSE_ID, 'q': q, 'fileType': 'pdf', 'num': 1}
    items = requests.get('https://www.googleapis.com/customsearch/v1', params=params).json().get('items', [])
    return items[0]['link'] if items else None

# --- Concept Q&A ---
def find_concept_pages(pages, concept):
    cl = concept.lower()
    return {p: t for p, t in pages.items() if cl in (t or '').lower()}

def ask_concept(pages, concept):
    found = find_concept_pages(pages, concept)
    if not found: return f"Couldn’t find '{concept}'."
    combined = "\n---\n".join(f"Page {p}: {t}" for p, t in found.items())
    prompt = f"Concept: '{concept}'. Sections:\n{combined}\nExplain with context and examples."
    return call_gemini(prompt)

# --- Learning Aids ---
def generate_summary(text): return call_gemini(f"Summarize for exam, list formulae:\n{text}")
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions:\n{text}")
def generate_flashcards(text): return call_gemini(f"Create flashcards (Q&A):\n{text}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics:\n{text}")
def generate_key_terms(text): return call_gemini(f"List key terms with definitions:\n{text}")
def generate_cheatsheet(text): return call_gemini(f"Create a cheat sheet:\n{text}")
def generate_highlights(text): return call_gemini(f"List key facts and highlights:\n{text}")
def generate_critical_points(text): return call_gemini(f"Detailed but concise run-through:\n{text}")

def plot_mind_map(json_text):
    try:
        mind_map = json.loads(json_text)
    except json.JSONDecodeError:
        st.error("Mind map format is invalid.")
        return

    nodes, edges = [], []
    id_map = {}
    counter = [0]

    def add_node(node, parent_id=None):
        node_id = counter[0]
        id_map[id(node)] = node_id
        label = node.get("title") or node.get("label") or "Node"
        nodes.append((node_id, label))
        if parent_id is not None:
            edges.append((parent_id, node_id))
        counter[0] += 1
        for child in node.get("children", []):
            add_node(child, node_id)

    add_node(mind_map)

    g = ig.Graph(directed=True)
    g.add_vertices([str(n[0]) for n in nodes])
    g.vs["label"] = [n[1] for n in nodes]
    g.add_edges([(str(s), str(t)) for s, t in edges])
    layout = g.layout("tree")

    x, y = zip(*layout.coords)
    edge_x, edge_y = [], []
    for e in g.get_edgelist():
        edge_x += [x[e[0]], x[e[1]], None]
        edge_y += [y[e[0]], y[e[1]], None]

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, line=dict(width=1, color='#888'),
        hoverinfo='none', mode='lines'
    )

    node_trace = go.Scatter(
        x=x, y=y, text=g.vs["label"], mode='markers+text',
        hoverinfo='text',
        marker=dict(size=30, color='#00BFFF', line=dict(width=2, color='DarkSlateGrey')),
        textposition='top center'
    )

    fig = go.Figure(data=[edge_trace, node_trace],
        layout=go.Layout(
            showlegend=False, hovermode='closest',
            margin=dict(b=20,l=5,r=5,t=40),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
    )

    st.plotly_chart(fig, use_container_width=True)

# --- UI ---
if not st.session_state['user']:
    login_ui()
else:
    user = st.session_state['user']
    st.sidebar.image(user.get('picture',''), width=50)
    st.sidebar.write(user.get('email',''))
    if st.sidebar.button('Logout'):
        st.session_state.clear()
    tab = st.sidebar.selectbox('Feature', ['Guide Book Chat', 'Document Q&A'])
    if tab == 'Guide Book Chat':
        st.header('Guide Book Chat')
        t = st.text_input('Title'); a = st.text_input('Author'); e = st.text_input('Edition')
        concept = st.text_input('Ask about concept:')
        if st.button('Chat') and concept:
            url = fetch_pdf_url(t, a, e)
            if not url: st.error('PDF not found')
            else:
                pages = extract_pages_from_url(url)
                ans = ask_concept(pages, concept); st.write(ans)
    else:
        st.header('Document Q&A')
        f = st.file_uploader('Upload PDF/Image/TXT', type=['pdf', 'jpg', 'png', 'txt'])
        if f:
            text = extract_text(f)
            st.subheader('Learning Aids')
            render = st.selectbox('Pick a function', [
                'Summary', 'Questions', 'Flashcards', 'Mnemonics',
                'Key Terms', 'Cheat Sheet', 'Highlights',
                'Critical Points', 'Concept Chat', 'Mind Map'
            ])
            if st.button('Run'):
                if render == 'Summary': res = generate_summary(text); st.write(res)
                elif render == 'Questions': res = generate_questions(text); st.write(res)
                elif render == 'Flashcards': res = generate_flashcards(text); st.write(res)
                elif render == 'Mnemonics': res = generate_mnemonics(text); st.write(res)
                elif render == 'Key Terms': res = generate_key_terms(text); st.write(res)
                elif render == 'Cheat Sheet': res = generate_cheatsheet(text); st.write(res)
                elif render == 'Highlights': res = generate_highlights(text); st.write(res)
                elif render == 'Critical Points': res = generate_critical_points(text); st.write(res)
                elif render == 'Concept Chat':
                    concept = st.text_input('Concept to explain:')
                    if concept: res = ask_concept(extract_pages_from_file(f), concept)
                    else: res = 'Enter concept.'
                    st.write(res)
                elif render == 'Mind Map':
                    res = call_gemini(f"Create JSON mind map from text:\n{text}")
                    plot_mind_map(res)
