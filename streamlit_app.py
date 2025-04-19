import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
import pytesseract
import fitz  # PyMuPDF
import docx
from pptx import Presentation
import re
import json
import io
import time
import requests
import sqlite3
from deep_translator import GoogleTranslator
import speech_recognition as sr
from gtts import gTTS
import plotly.graph_objects as go
import igraph as ig

# --- Configuration & Page Banner ---
st.set_page_config(page_title="Vekkam", layout="wide")
st.markdown("""
<div style='background-color: #4CAF50; padding: 10px; text-align: center;'>
    <h1 style='color: white;'>Welcome to Vekkam - Your Study Buddy</h1>
</div>
""", unsafe_allow_html=True)

# --- Loader HTML ---
loader_html = '''
<div id="loader" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(255,255,255,0.9);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;">
  <div class="mascot" style="width:150px;height:150px;background:url('mascot.png') no-repeat center/contain;animation:bounce 2s infinite;"></div>
  <div id="progress" style="font-size:30px;color:#ff4500;margin-top:20px;">Loading... 0%</div>
</div>
<style>@keyframes bounce{0%,100%{transform:translateY(0);}50%{transform:translateY(-20px);}}</style>
<script>
let prog=0;let el=document.getElementById('progress');let iv=setInterval(()=>{prog++;if(prog>100)prog=100;el.textContent=`Loading... ${prog}%`;},200);
new MutationObserver((muts)=>{if(!document.body.contains(document.getElementById('loader'))){clearInterval(iv);}}).observe(document.body,{childList:true,subtree:true});
</script>
'''

# --- Gemini API Call (Mock) ---
def call_gemini(prompt, temperature=0.7, max_tokens=8192):
    # TODO: replace mock with real API call and key in st.secrets
    return f"[Gemini]: {prompt[:200]}..."

# --- Text Extraction ---
def extract_text(file):
    name = file.name.lower()
    if name.endswith('.pdf'):
        doc = fitz.open(stream=file.read(), filetype='pdf')
        return ''.join(page.get_text() for page in doc)
    if name.endswith('.docx'):
        return '\n'.join(p.text for p in docx.Document(file).paragraphs)
    if name.endswith('.pptx'):
        return '\n'.join(shape.text for slide in Presentation(file).slides for shape in slide.shapes if hasattr(shape,'text'))
    if name.endswith('.txt'):
        return io.StringIO(file.getvalue().decode('utf-8')).read()
    if name.endswith(('.jpg','.jpeg','.png')):
        return pytesseract.image_to_string(Image.open(file))
    return ''

# --- Translation ---
def translate_text(text, target_lang='hi'):
    if target_lang=='en': return text
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        return f"Translation error: {e}"

# --- Voice Input & TTS ---
def record_voice_input():
    r=sr.Recognizer()
    with sr.Microphone() as src:
        st.info("Listening... Speak now.")
        try: audio=r.listen(src,timeout=5); return r.recognize_google(audio)
        except Exception as e: return f"Error: {e}"

def play_tts(text, lang='en'):
    try:
        tmp=f"tts_{int(time.time())}.mp3"
        gTTS(text=text,lang=lang).save(tmp)
        return tmp
    except Exception as e:
        st.error(f"TTS Error: {e}")
        return None

# --- Mind Map JSON & Plot ---
def get_mind_map(text):
    prompt=f"Create JSON mind map from text:\n{text[:500]}"
    resp=call_gemini(prompt,temperature=0.5)
    try:
        js=re.search(r"\{.*\}",resp,re.DOTALL).group(0)
        data=json.loads(js)
        if 'nodes' in data and 'edges' in data: return data
    except:
        pass
    st.error("Mind map parsing failed.")
    return None

def plot_mind_map(nodes,edges):
    idx={n['id']:i for i,n in enumerate(nodes)}
    g=ig.Graph(directed=True)
    g.add_vertices(len(nodes)); edges_idx=[(idx[e['source']],idx[e['target']]) for e in edges if e['source'] in idx and e['target'] in idx]
    g.add_edges(edges_idx)
    layout=g.layout('kk') if len(nodes)>1 else g.layout('tree')
    scale=3; ex=[]; ey=[]
    for e in g.es:
        x0,y0=layout[e.tuple[0]]; x1,y1=layout[e.tuple[1]]
        ex+= [x0*scale,x1*scale,None]; ey+=[y0*scale,y1*scale,None]
    nx=[]; ny=[]; hl=[]
    for i,n in enumerate(nodes): x,y=layout[i]; nx.append(x*scale); ny.append(y*scale); hl.append(f"<b>{n['label']}</b><br>{n.get('description','')}")
    fig=go.Figure([go.Scatter(x=ex,y=ey,mode='lines',line=dict(width=1,color='#888')), 
                   go.Scatter(x=nx,y=ny,mode='markers+text',marker=dict(size=20,color='#00cc96'),text=[n['label'] for n in nodes],textposition='top center',hovertext=hl,hoverinfo='text')],
                  layout=go.Layout(title='🧠 Mind Map',width=1000,height=700,xaxis=dict(showgrid=False,zeroline=False,showticklabels=False),yaxis=dict(showgrid=False,zeroline=False,showticklabels=False)))
    components.html(fig.to_html(include_plotlyjs='cdn'),height=750)

# --- AI Learning Aids ---
def generate_summary(text): return call_gemini(f"Summarize for exam and list formulae:\n{text[:300]}")
def generate_questions(text): return call_gemini(f"Generate 15 quiz questions:\n{text[:300]}")
def generate_flashcards(text): return call_gemini(f"Create flashcards Q&A:\n{text[:300]}")
def generate_mnemonics(text): return call_gemini(f"Generate mnemonics:\n{text[:300]}")
def generate_key_terms(text): return call_gemini(f"List 10 key terms:\n{text[:300]}")
def generate_cheatsheet(text): return call_gemini(f"Create cheat sheet:\n{text[:300]}")
def generate_highlights(text): return call_gemini(f"Key facts and highlights:\n{text[:300]}")

def render_section(title,content):
    st.subheader(title)
    if isinstance(content,str) and content.strip().startswith('<'):
        components.html(content,scrolling=True)
    else:
        st.write(content)

# --- Main Logic ---
menu = st.sidebar.selectbox("Feature", ["Document Analyzer","Translator","AI Tutor","Gamification","Dashboard","Image Compress","Offline Sync","Collaborative Hub","LMS Import","Sponsor Zone"])

if menu=="Document Analyzer":
    files=st.file_uploader("Upload files",type=['pdf','docx','pptx','txt','jpg','png'],accept_multiple_files=True)
    if files:
        placeholder=st.empty(); placeholder.markdown(loader_html,unsafe_allow_html=True)
        for i,f in enumerate(files):
            st.markdown(f"---\n## 📄 {f.name}")
            text=extract_text(f)
            mind=get_mind_map(text)
            if mind: plot_mind_map(mind['nodes'],mind['edges'])
            render_section("📌 Summary",generate_summary(text)); render_section("📝 Questions",generate_questions(text))
            with st.expander("📚 Flashcards"): render_section("Flashcards",generate_flashcards(text))
            with st.expander("🧠 Mnemonics"): render_section("Mnemonics",generate_mnemonics(text))
            with st.expander("🔑 Key Terms"): render_section("Key Terms",generate_key_terms(text))
            with st.expander("📋 Cheat Sheet"): render_section("Cheat Sheet",generate_cheatsheet(text))
            with st.expander("⭐ Highlights"): render_section("Highlights",generate_highlights(text))
            if i==0: placeholder.empty()

elif menu=="Translator":
    txt=st.text_area("Text to translate")
    lang=st.selectbox("Language",['hi','es','fr','en'])
    if st.button("Translate"): st.write(translate_text(txt,lang))

elif menu=="AI Tutor":
    st.title("AI Tutor Chatbot")
    mode=st.radio("Mode",['Text','Voice'])
    if mode=='Text': q=st.text_input("Question")
    else: q=record_voice_input() if st.button("Record") else None
    if q:
        ans=call_gemini(f"Tutor: {q}"); st.write(ans)
        audio=play_tts(ans); audio and st.audio(audio)

elif menu=="Gamification":
    st.write("", sqlite3.version)
    st.write("User XP:","+"+str({'quiz':10,'review':5}.get('quiz')))
    st.success("Badge: Flashcard Hero")

elif menu=="Dashboard":
    st.title("Institution Dashboard")
    st.line_chart([10,30,50,70])

elif menu=="Image Compress":
    img=st.file_uploader("Image",type=['png','jpg','jpeg'])
    if img: st.image(compress_images(img))

elif menu=="Offline Sync":
    cards=[{'q':'Define ML','a':'Machine Learning'}]
    st.write(save_offline_cache(cards))

elif menu=="Collaborative Hub": start_collab_hub()
elif menu=="LMS Import": st.write(import_from_google_classroom())
elif menu=="Sponsor Zone":
    reg=st.selectbox("Region",['Northeast India','Kibera','Other'])
    st.write(f"Sponsor: {get_impact_zone_sponsor(reg)}")
