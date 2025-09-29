import streamlit as st
import time
import os
import google.generativeai as genai
import fitz  # PyMuPDF
from PIL import Image
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import requests
import tempfile
from functools import wraps
from google.api_core import exceptions
from pathlib import Path
import uuid
import razorpay
from datetime import datetime

# --- GOOGLE OAUTH & API LIBRARIES ---
try:
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    st.error("Required Google libraries not found! Please run: pip install google-auth-oauthlib google-api-python-client")
    st.stop()

# --- CONFIGURATION & CONSTANTS ---
MAX_FILES = 20
MAX_TOTAL_SIZE_MB = 150
MAX_AUDIO_SIZE_MB = 1024
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_RETRIES = 3
DATA_DIR = Path("user_data")
DATA_DIR.mkdir(exist_ok=True)

# --- TIER LIMITS ---
FREE_TIER_LIMIT = 1
PAID_TIER_DAILY_LIMIT = 3
PAYMENT_AMOUNT = 99900 # Amount in paise (e.g., 999.00 INR)

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Vekkam Engine", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")

# --- MOCK KNOWLEDGE GENOME DATA (FOR GENESIS MODULE) ---
ECON_101_GENOME = {
    # ... (existing genome data remains unchanged)
 "subject": "Econ 101",
 "version": "1.0",
 "nodes": [
   {
     "gene_id": "ECON101_SCARCITY",
     "gene_name": "Scarcity",
     "difficulty": 1,
     "content_alleles": [
       {"type": "text", "content": "Scarcity refers to the basic economic problem, the gap between limited – that is, scarce – resources and theoretically limitless wants. This situation requires people to make decisions about how to allocate resources in an efficient way, in order to satisfy as many of their wants as possible."},
       {"type": "video", "url": "https://www.youtube.com/watch?v=yoVc_S_gd_0"}
     ]
   },
   {
     "gene_id": "ECON101_OPPCOST",
     "gene_name": "Opportunity Cost",
     "difficulty": 2,
     "content_alleles": [
         {"type": "text", "content": "Opportunity cost is the potential forgone profit from a missed opportunity—the result of choosing one alternative and forgoing another. In short, it’s what you give up when you make a decision. The formula is simply the difference between the expected return of each option. Expected Return = (Probability of Gain x Potential Gain) - (Probability of Loss x Potential Loss)."},
         {"type": "video", "url": "https://www.youtube.com/watch?v=PSU-SA-Fv_M"}
     ]
   },
   {
     "gene_id": "ECON101_SND",
     "gene_name": "Supply and Demand",
     "difficulty": 3,
     "content_alleles": [
         {"type": "text", "content": "Supply and demand is a model of microeconomics. It describes how a price is formed in a market economy. In a competitive market, the unit price for a particular good will vary until it settles at a point where the quantity demanded by consumers (at the current price) will equal the quantity supplied by producers (at the current price), resulting in an economic equilibrium for price and quantity."},
         {"type": "video", "url": "https://www.youtube.com/watch?v=9QSWLmyGpYc"}
     ]
   }
 ],
 "edges": [
   {"from": "ECON101_SCARCITY", "to": "ECON101_OPPCOST"},
   {"from": "ECON101_OPPCOST", "to": "ECON101_SND"}
 ]
}


# --- EXPONENTIAL BACKOFF DECORATOR ---
def gemini_api_call_with_retry(func):
    """Decorator to handle Gemini API rate limiting with exponential backoff."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        retries = 0
        delay = 1
        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except exceptions.ResourceExhausted as e:
                retries += 1
                if retries >= MAX_RETRIES:
                    st.error(f"API quota exceeded after multiple retries. Please check your Google Cloud billing plan. Error: {e}")
                    return None
                
                match = re.search(r'retry_delay {\s*seconds: (\d+)\s*}', str(e))
                if match:
                    wait_time = int(match.group(1)) + delay
                else:
                    wait_time = delay * (2 ** retries)

                st.warning(f"Rate limit hit. Retrying in {wait_time} seconds... (Attempt {retries}/{MAX_RETRIES})")
                time.sleep(wait_time)
            except Exception as e:
                st.error(f"An unexpected API error occurred in {func.__name__}: {e}")
                return None
        return None
    return wrapper

# --- PERSISTENT DATA STORAGE & USER MANAGEMENT ---
def get_user_data_path(user_id):
    """Generates a secure filepath for a user data."""
    safe_filename = hashlib.md5(user_id.encode()).hexdigest() + ".json"
    return DATA_DIR / safe_filename

def load_user_data(user_id):
    """Loads a user session history from a JSON file, initializing tier status if not present."""
    filepath = get_user_data_path(user_id)
    default_data = {
        "sessions": [],
        "user_tier": "free",
        "total_analyses": 0,
        "last_analysis_date": None,
        "daily_analyses_count": 0
    }
    if filepath.exists():
        with open(filepath, 'r') as f:
            try:
                data = json.load(f)
                # Ensure all keys exist for backward compatibility
                for key, value in default_data.items():
                    data.setdefault(key, value)
                return data
            except json.JSONDecodeError:
                return default_data
    return default_data

def save_user_data(user_id, data):
    """Saves a user session history to a JSON file."""
    filepath = get_user_data_path(user_id)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def update_user_usage(user_id):
    """Updates user's analysis count after a successful operation."""
    user_data = load_user_data(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if user_data['user_tier'] == 'free':
        user_data['total_analyses'] += 1
    elif user_data['user_tier'] == 'paid':
        if user_data['last_analysis_date'] == today_str:
            user_data['daily_analyses_count'] += 1
        else:
            user_data['last_analysis_date'] = today_str
            user_data['daily_analyses_count'] = 1
            
    save_user_data(user_id, user_data)

def save_session_to_history(user_id, final_notes):
    """Saves the full note content from a completed session for a user."""
    user_data = load_user_data(user_id)
    session_title = final_notes[0]['topic'] if final_notes else "Untitled Session"
    new_session = {
        "id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": session_title,
        "notes": final_notes
    }
    user_data["sessions"].insert(0, new_session)
    save_user_data(user_id, user_data)

# --- PAYWALL & ACCESS CONTROL ---
def get_razorpay_client():
    """Initializes and returns the Razorpay client."""
    try:
        key_id = st.secrets["Razorpay"]["key_id"]
        key_secret = st.secrets["Razorpay"]["key_secret"]
        return razorpay.Client(auth=(key_id, key_secret))
    except (KeyError, FileNotFoundError):
        st.error("Razorpay credentials are not configured correctly in st.secrets.")
        return None

def check_user_access(user_id):
    """Checks user access and returns status and a message, without printing."""
    user_data = load_user_data(user_id)
    tier = user_data.get('user_tier', 'free')
    today_str = datetime.now().strftime("%Y-%m-%d")

    if tier == 'free':
        if user_data.get('total_analyses', 0) >= FREE_TIER_LIMIT:
            message = "You have used your single free analysis. Please upgrade to add more files or start a new session."
            return False, 'limit_reached', message
    elif tier == 'paid':
        last_date = user_data.get('last_analysis_date')
        daily_count = user_data.get('daily_analyses_count', 0)
        if last_date == today_str and daily_count >= PAID_TIER_DAILY_LIMIT:
            message = f"You have reached your daily limit of {PAID_TIER_DAILY_LIMIT} analyses."
            return False, 'limit_reached', message
            
    return True, 'ok', "Access granted."

def show_paywall(user_id, user_info):
    """Displays the Razorpay payment button and handles the upgrade logic."""
    st.header("🚀 Upgrade to Premium")
    st.markdown("Unlock unlimited potential with 3 analyses per day, every day.")
    
    client = get_razorpay_client()
    if not client:
        return

    payment_data = {
        "amount": PAYMENT_AMOUNT,
        "currency": "INR",
        "receipt": f"receipt_{user_id}_{int(time.time())}",
        "notes": {
            "user_id": user_id,
            "email": user_info.get('email', 'N/A')
        }
    }
    try:
        order = client.order.create(data=payment_data)
        order_id = order['id']
        
        st.markdown(f"""
        <form>
            <script 
                src="https://checkout.razorpay.com/v1/checkout.js"
                data-key="{st.secrets['Razorpay']['key_id']}"
                data-amount="{PAYMENT_AMOUNT}"
                data-currency="INR"
                data-order_id="{order_id}"
                data-buttontext="Pay {PAYMENT_AMOUNT/100:.2f} INR with Razorpay"
                data-name="Vekkam Engine"
                data-description="Premium Access"
                data-prefill.name="{user_info.get('name', '')}"
                data-prefill.email="{user_info.get('email', '')}"
                data-theme.color="#007BFF">
            </script>
        </form>
        """, unsafe_allow_html=True)

        st.info("After successful payment, please click the button below to confirm your upgrade.")

        if st.button("I have paid! Verify and Upgrade my account."):
            # --- IMPORTANT ---
            # In a real-world production app, you MUST verify the payment signature from Razorpay 
            # using a webhook and a backend server. This client-side confirmation is for
            # demonstration purposes ONLY and is NOT secure.
            with st.spinner("Verifying..."):
                time.sleep(2) # Simulate verification delay
                user_data = load_user_data(user_id)
                user_data['user_tier'] = 'paid'
                save_user_data(user_id, user_data)
                st.success("Upgrade successful! Your account is now Premium.")
                st.balloons()
                time.sleep(2)
                st.rerun()

    except Exception as e:
        st.error(f"Could not initiate payment. Error: {e}")

# --- API SELF-DIAGNOSIS & UTILITIES ---
def check_gemini_api():
    try:
        genai.get_model('models/gemini-2.5-flash-lite')
        return "Valid"
    except Exception as e:
        st.sidebar.error(f"Gemini API Key in secrets is invalid: {e}")
        return "Invalid"

def resilient_json_parser(json_string):
    try:
        match = re.search(r'```(json)?\s*(\{.*?\})\s*```', json_string, re.DOTALL)
        if match:
            return json.loads(match.group(2))
        
        match = re.search(r'\{.*\}', json_string, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        
        return None
    except json.JSONDecodeError:
        st.error("Fatal Error: Could not parse a critical AI JSON response."); return None

def chunk_text(text, source_id, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    if not text: return []
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunk_hash = hashlib.md5(chunk_text.encode()).hexdigest()[:8]
        chunk_id = f"{source_id}::chunk_{i//(chunk_size-overlap)}_{chunk_hash}"
        chunks.append({"chunk_id": chunk_id, "text": chunk_text})
    return chunks

# --- CONTENT PROCESSING ---
def process_source(file, source_type):
    try:
        source_id = f"{source_type}:{file.name}"
        model_name = 'gemini-2.5-flash-lite-vision' if source_type in ['image', 'pdf'] else 'gemini-2.5-flash-lite'
        model = genai.GenerativeModel(model_name)
        if source_type == 'transcript':
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
                tmp.write(file.getvalue())
                tmp_path = tmp.name
            try:
                audio_file = genai.upload_file(path=tmp_path)
                response = model.generate_content(["Transcribe this noisy classroom audio recording. Prioritize capturing all speech, even if faint, over background noise and echo.", audio_file])
                chunks = chunk_text(response.text, source_id)
                return {"status": "success", "source_id": source_id, "chunks": chunks}
            finally:
                os.unlink(tmp_path)
        elif source_type == 'image':
            image = Image.open(file)
            response = model.generate_content(["Analyze this image...", image])
            return {"status": "success", "source_id": source_id, "chunks": [{"chunk_id": f"{source_id}::chunk_0", "text": response.text}]}
        elif source_type == 'pdf':
            pdf_bytes = file.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            chunks = chunk_text(text, source_id)
            return {"status": "success", "source_id": source_id, "chunks": chunks}
    except Exception as e:
        return {"status": "error", "source_id": f"{source_type}:{file.name}", "reason": str(e)}

# --- AGENTIC WORKFLOW FUNCTIONS ---
@gemini_api_call_with_retry
def generate_content_outline(all_chunks, existing_outline=None):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    prompt_chunks = [{"chunk_id": c['chunk_id'], "text_snippet": c['text'][:200] + "..."} for c in all_chunks if c.get('text') and len(c['text'].split()) > 10]
    
    if not prompt_chunks:
        st.error("Could not find enough content to generate an outline. Please check your uploaded files.")
        return None

    instruction = "Analyze the content chunks and create a structured, logical topic outline. The topics should flow from foundational concepts to more advanced ones."
    if existing_outline:
        instruction = "Analyze the NEW content chunks and suggest topics to ADD to the existing outline. Maintain a logical flow."
    
    prompt = f"""
    You are a master curriculum designer. Your task is to create a coherent and comprehensive study outline from fragmented pieces of text.
    {instruction}
    For each topic, you MUST list the `chunk_id`s that are most relevant to that topic. Ensure every chunk is used if possible, but prioritize relevance.
    Do not invent topics not supported by the text. Base the outline STRICTLY on the provided content.
    Output ONLY a valid JSON object with a root key "outline", which is a list of objects. Each object must have keys "topic" (string) and "relevant_chunks" (a list of string chunk_ids).

    **Existing Outline (for context):**
    {json.dumps(existing_outline, indent=2) if existing_outline else "None"}

    **Content Chunks:**
    ---
    {json.dumps(prompt_chunks, indent=2)}
    """
    response = model.generate_content(prompt)
    return resilient_json_parser(response.text)

@gemini_api_call_with_retry
def synthesize_note_block(topic, relevant_chunks_text, instructions):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    prompt = f"""
    You are a world-class note-taker. Synthesize a detailed, clear, and well-structured note block for a single topic: {topic}.
    Your entire response MUST be based STRICTLY and ONLY on the provided source text. Do not introduce any external information.
    Adhere to the user instructions for formatting and style. Format the output in Markdown.

    **User Instructions:** {instructions if instructions else "Default: Create clear, concise, well-structured notes."}

    **Source Text (Use only this):**
    ---
    {relevant_chunks_text}
    ---
    """
    response = model.generate_content(prompt)
    return response.text

@gemini_api_call_with_retry
def answer_from_context(query, context):
    """Answers a user query based ONLY on the provided context."""
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    prompt = f"""
    You are a helpful study assistant. Your task is to answer the user question based strictly and exclusively on the provided study material context.
    Do not use any external knowledge. If the answer is not in the context, clearly state that the information is not available in the provided materials.

    **User Question:**
    {query}

    **Study Material Context:**
    ---
    {context}
    ---
    """
    response = model.generate_content(prompt)
    return response.text

# --- AUTHENTICATION & SESSION MANAGEMENT ---
def get_google_flow():
    try:
        client_config = {
            "web": { "client_id": st.secrets["google"]["client_id"], "client_secret": st.secrets["google"]["client_secret"],
                     "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
                     "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                     "redirect_uris": [st.secrets["google"]["redirect_uri"]],
            }}
        scopes = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"]
        return Flow.from_client_config(client_config, scopes=scopes, redirect_uri=st.secrets["google"]["redirect_uri"])
    except (KeyError, FileNotFoundError):
        st.error("OAuth credentials are not configured correctly in st.secrets."); st.stop()

def reset_session():
    """
    Resets the state of the current tool by surgically removing tool-specific keys,
    preserving global state like user_info and all_chunks.
    """
    # Keys to preserve globally across all tools
    keys_to_preserve = ['user_info', 'all_chunks', 'tool_choice', 'last_tool_choice', 'landing_view']
    
    # Find all keys to delete (i.e., not in the preserve list)
    keys_to_delete = [key for key in st.session_state.keys() if key not in keys_to_preserve]
    
    # Delete the tool-specific keys
    for key in keys_to_delete:
        del st.session_state[key]


# --- LEGAL POLICIES VIEW ---
def show_policies_page(auth_url):
    """Displays the legal policies (ToS, Privacy, Return) in a dedicated view."""
    st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} [data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)

    # Header and Navigation
    st.markdown('<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center bg-white sticky top-0 z-50 shadow-sm">', unsafe_allow_html=True)
    st.markdown('<h1 class="text-3xl font-bold text-gray-900">Legal Disclosures</h1>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.button("← Back to Study Smarter", on_click=lambda: st.session_state.update(landing_view='marketing'))
    with col2:
        st.link_button("Log In / Try Free", auth_url, type="primary")
    st.markdown('</div>', unsafe_allow_html=True)
    st.divider()

    # Content Area
    st.markdown('<div class="max-w-4xl mx-auto px-4 py-8">', unsafe_allow_html=True)
    
    st.markdown("## Terms of Service (ToS)")
    st.markdown("""
        **Last Updated: September 29, 2025**
        
        By using the Vekkam Engine ("Service"), you agree to be bound by these Terms.
        
        1. **Acceptance of Terms:** Your access to and use of the Service is conditioned upon your acceptance of and compliance with these Terms.
        2. **User Conduct:** You agree to use the Service only for lawful study purposes. Any misuse, including unauthorized scraping, bulk downloading, or attempt to reverse-engineer our models, is strictly prohibited and will result in immediate account termination.
        3. **Intellectual Property:** All content generated by the Service from *your* uploaded materials remains your property. However, the models, interfaces, and underlying technology of Vekkam are the exclusive property of the Company.
        4. **Disclaimer:** We do not guarantee academic performance or score improvement. The Service is an assistive tool; results depend on individual effort and application.
    """)
    st.divider()

    st.markdown("## Privacy Policy")
    st.markdown("""
        **Last Updated: September 29, 2025**
        
        We prioritize your privacy.
        
        1. **Data Collection:** We collect user authentication data (via Google OAuth), payment information (handled securely by Razorpay), and your uploaded files/generated notes.
        2. **Data Usage (The Core Promise):** Your uploaded study materials and generated notes **are never used to train or improve our foundational AI models.** They are stored securely for your personal TA and session history only.
        3. **Security:** We use industry-standard encryption for data transfer and storage. Payment processing is handled by Razorpay, an external, secure gateway.
        4. **Retention:** You may delete your data at any time via account settings (once implemented). We retain basic usage data for billing and feature analysis.
    """)
    st.divider()

    st.markdown("## Return & Refund Policy")
    st.markdown("""
        **Effective Date: September 29, 2025**
        
        Due to the immediate and intangible nature of digital service access, our policy is as follows:
        
        1. **Subscription Purchases:** All sales for the monthly "Potential Unlocked" subscription (₹999.00 INR) are **final and non-refundable** immediately upon successful payment through Razorpay.
        2. **Exceptions:** Refunds will only be considered in cases of documented technical failure where the Service remains inaccessible for more than 48 consecutive hours after purchase.
        3. **Contact:** For refund inquiries, please contact team.vekkam@gmail.com with your Order ID and reason.
    """)
    st.divider()

    st.markdown("## Regulatory & Legal Disclosures")
    st.markdown("""
        1. **Governing Law:** These policies are governed by and construed in accordance with the laws of India, specifically the jurisdiction of Bhubaneswar, Odisha.
        2. **Payment Gateway Disclosure:** All transactions are processed by **Razorpay**, and we do not store your full card details.
        3. **Contact Information:** For all legal inquiries:
           - Email: team.vekkam@gmail.com
           - Phone: +91 91103 12834
    """)
    st.markdown('</div>', unsafe_allow_html=True)


# --- LANDING PAGE ---
def show_landing_page(auth_url):
    """Displays the AARRR-framework-based landing page with updated content."""
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
            .main { background-color: #FFFFFF; font-family: 'Inter', sans-serif; }
            .hero-container { padding: 4rem 1rem; text-align: center; }
            .hero-title { font-size: 3.5rem; font-weight: 800; background: -webkit-linear-gradient(45deg, #004080, #007BFF); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 1rem; line-height: 1.1; }
            .hero-subtitle { font-size: 1.25rem; color: #555; max-width: 700px; margin: 0 auto 2rem auto; line-height: 1.6; }
            .section-header { text-align: center; color: #004080; font-weight: 700; margin-top: 4rem; margin-bottom: 2rem; }
            
            /* Custom Cards for Feature/Pain Points */
            .custom-card { padding: 1.5rem; border-radius: 12px; border: 1px solid #E0E0E0; margin-bottom: 1.5rem; transition: all 0.2s; background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.02); }
            .custom-card:hover { border-color: #007BFF; box-shadow: 0 4px 12px rgba(0, 123, 255, 0.1); }
            .list-ai li { list-style-type: disc; margin-left: 20px; color: #4B5563; }
            
            /* Pricing Table */
            .pricing-card { background-color: #F8F9FA; border-radius: 12px; padding: 2rem; text-align: center; border: 2px solid #E0E0E0; }
            .pricing-card.primary { background-color: #E6F2FF; border-color: #007BFF; }
            .pricing-title { font-size: 1.5rem; font-weight: 700; color: #1F2937; }
            .price { font-size: 3rem; font-weight: 800; color: #004080; }
        </style>
    """, unsafe_allow_html=True)

    # --- HERO SECTION ---
    with st.container():
        st.markdown('<div class="hero-container">', unsafe_allow_html=True)
        st.markdown('<h1 class="hero-title">Study Smarter. Not Longer.</h1>', unsafe_allow_html=True)
        st.markdown('<p class="hero-subtitle">Crack the biggest syllabus in just 6 hours—with AI that knows how you learn. Vekkam is your personalized study plan generator, powered by neuroscience, behavioral science, and real-world exam performance data.</p>', unsafe_allow_html=True)
        st.link_button("Try us out (Instant Access)", auth_url, type="primary")
        # Added Policies Link
        st.button("View Policies & Legal", on_click=lambda: st.session_state.update(landing_view='policies'), key='policies_link')
        st.markdown('</div>', unsafe_allow_html=True)
    st.divider()

    # --- WHAT WE OFFER / ABOUT OUR PRODUCT (Section 1) ---
    st.markdown('<div class="max-w-6xl mx-auto px-4">', unsafe_allow_html=True)
    st.markdown('<h2 class="section-header">What We Offer: Built for the Real Student Panic</h2>', unsafe_allow_html=True)

    st.markdown("""
        <p class="text-lg text-gray-700 mb-6">
            Vekkam is a state-of-the-art study buddy app that helps students navigate the intricacies of covering a vast syllabus 6 hours before an exam, for the <strong>88% of students who sit down to study for exams at least 48 hours before the exam.</strong>
        </p>
    """, unsafe_allow_html=True)

    # --- AI Competitive Analysis ---
    st.markdown("""
        <div class="custom-card">
            <h3 class="text-xl font-semibold text-gray-800 mb-4">The Truth About Today's AI Study Tools</h3>
            <p class="text-gray-600 mb-3">Here’s what a student emailed us during our market research when we asked our respondents what AI they use to study:</p>
            <ul class="list-ai grid grid-cols-1 sm:grid-cols-2 gap-2">
                <li>Perplexity</li>
                <li>ChatGPT</li>
                <li>Claude by Anthropic (best outputs but limits for free user)</li>
                <li>Deepseek-r1</li>
                <li>Kimi (new but effective) — it has the highest upload limit to a free user like 50 docs of 100mb each.</li>
                <li>Gemini (launched good models recently in 2.0 series COT)</li>
                <li>Mistral (Le chat) also in Brave browser default AI</li>
                <li>Copilot MSFT</li>
            </ul>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
        <p class="text-xl italic text-gray-500 my-8 border-l-4 border-blue-500 pl-4">
            “You’re staring at midnight, coffee gone cold, and a stack of lecture notes that make zero sense. You know the exam’s looming—and generic PDFs and random YouTube videos aren’t cutting it. That’s exactly why we built Vekkam.”
        </p>
        <p class="text-lg text-gray-700 mb-8">
            You don’t have time to write prompts to an AI that doesn’t help anyways. You need high-impact revision—right now. <strong>Vekkam was born from the panic of real students who, like you, needed a game-changer one night before finals.</strong>
        </p>
    """, unsafe_allow_html=True)

    # --- THE PAIN YOU KNOW (Section 2) ---
    st.markdown('<h2 class="section-header">2. The Pain You Know</h2>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="custom-card bg-red-50 border-red-200"> <h3 class="text-lg font-semibold text-red-700">Last-Minute Overwhelm</h3> <p class="text-gray-700">Endless pages, zero focus. You feel guilty just looking at the pile of material.</p> </div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="custom-card bg-red-50 border-red-200"> <h3 class="text-lg font-semibold text-red-700">No Guided Path</h3> <p class="text-gray-700">You’re drowning in information but starving for clarity. Where do you even start?</p> </div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="custom-card bg-red-50 border-red-200"> <h3 class="text-lg font-semibold text-red-700">Exam Anxiety</h3> <p class="text-gray-700">Stress zaps your confidence. Your friend's notes? Too much effort to read them now.</p> </div>', unsafe_allow_html=True)

    # --- THE VEKKAM SOLUTION (Section 3) ---
    st.markdown('<h2 class="section-header">3. The Vekkam Solution</h2>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="custom-card bg-blue-50 border-blue-200"> <h3 class="text-lg font-semibold text-blue-700">Laser-Focused Summaries</h3> <p class="text-gray-700">We “inject” you with the must-know facts, distilled from any file you upload. <strong>No fluff.</strong></p> </div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="custom-card bg-blue-50 border-blue-200"> <h3 class="text-lg font-semibold text-blue-700">Student-Built, AI-Powered</h3> <p class="text-gray-700">We took NotebookLM, ChatGPT, DeepSeek—and upgraded them with student-tested tweaks.</p> </div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="custom-card bg-blue-50 border-blue-200"> <h3 class="text-lg font-semibold text-blue-700">Bite-Sized Knowledge Blasts</h3> <p class="text-gray-700">Just the core concepts you’ll be tested on. <strong>High-impact revision.</strong></p> </div>', unsafe_allow_html=True)

    # --- WHY IT WORKS (Section 4) ---
    st.markdown('<h2 class="section-header">4. Why It Works</h2>', unsafe_allow_html=True)
    st.markdown("""
        <ul class="space-y-4 text-lg text-gray-700">
            <li class="flex items-start">
                <span class="text-2xl mr-3 text-green-600">⚡</span>
                <p><strong>Superfast Workflow:</strong> As soon as you upload a document, you’re ready to master it in less than 10 seconds. Everything is handled by the AI; you focus only on understanding and solving questions.</p>
            </li>
            <li class="flex items-start">
                <span class="text-2xl mr-3 text-green-600">📈</span>
                <p><strong>Real Research, Real Results:</strong> Dozens of student testers slashed 5+ hours off their study time and locked in <strong>20–30% score improvements.</strong></p>
            </li>
            <li class="flex items-start">
                <span class="text-2xl mr-3 text-green-600">🧑‍🎓</span>
                <p><strong>Built by Students, for Students:</strong> We’ve been in your shoes. We know the struggle—and we engineered a direct solution.</p>
            </li>
        </ul>
    """, unsafe_allow_html=True)

    # --- OUR OFFER (Section 5 - New Pricing) ---
    st.markdown('<h2 class="section-header">5. Our Offer (which you can’t refuse)</h2>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
            <div class="pricing-card">
                <p class="pricing-title">Free Tier</p>
                <p class="price">₹0</p>
                <p class="text-sm text-gray-500 mb-4">/ month</p>
                <p class="text-sm font-bold text-green-600">No Credit Card Required</p>
                <p class="text-gray-600 mt-4">Unlimited uploads, until 31 December 2025.</p>
                <button onclick="window.location.href='{auth_url}'" class="mt-6 px-6 py-2 bg-green-500 text-white font-semibold rounded-lg hover:bg-green-600 transition">Try it out</button>
            </div>
        """.format(auth_url=auth_url), unsafe_allow_html=True)

    with col2:
        st.markdown("""
            <div class="pricing-card primary">
                <p class="pricing-title">Potential Unlocked</p>
                <p class="price">₹100</p>
                <p class="text-sm text-gray-500 mb-4">/ month</p>
                <p class="text-xs text-blue-700 font-semibold mb-4">Most Popular</p>
                <p class="text-gray-600 mt-4">Unlock daily analysis limits and exclusive features.</p>
                <p class="text-sm text-gray-500 mt-2">(Actual Razorpay button hidden here)</p>
                <button onclick="alert('This tier is handled by a separate in-app paywall logic.')" class="mt-6 px-6 py-2 bg-blue-500 text-white font-semibold rounded-lg hover:bg-blue-600 transition">Coming Soon</button>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
            <div class="pricing-card">
                <p class="pricing-title">Topper Mode</p>
                <p class="price">₹250</p>
                <p class="text-sm text-gray-500 mb-4">/ month</p>
                <p class="text-sm font-bold text-gray-400 mb-4">For the dedicated few</p>
                <p class="text-gray-600 mt-4">All-access pass to future Master tools.</p>
                <button disabled class="mt-6 px-6 py-2 bg-gray-400 text-white font-semibold rounded-lg cursor-not-allowed">Coming Soon</button>
            </div>
        """, unsafe_allow_html=True)

    # --- Discount Offer ---
    st.markdown('<div class="my-10 text-center max-w-4xl mx-auto p-6 bg-yellow-50 border-l-4 border-yellow-500 rounded-lg">', unsafe_allow_html=True)
    st.markdown("""
        <h3 class="text-2xl font-bold text-gray-800 mb-3">Too Expensive?</h3>
        <p class="text-lg text-gray-700">
            We get it—Any price is high enough to back out. But, what if we gave you the opportunity to score a discount of flat 75%, and it involved you telling your friends about us?
        </p>
        <p class="text-md text-gray-600 mt-3">
            As a part of Vekkam’s <strong>Student Affiliate program</strong>, get <strong>75% off</strong> for the first month of your subscription if your friend takes a subscription of the product, <strong>50% off</strong> for the second, and <strong>20% off</strong> for the next 4. Awesome, eh?
        </p>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # --- ABOUT US ---
    st.markdown('<h2 class="section-header">About Us</h2>', unsafe_allow_html=True)
    st.markdown("""
        <div class="max-w-4xl mx-auto text-gray-700 space-y-4 text-lg">
            <p><strong>Vekkam is a team of students building for students.</strong></p>
            <p>
                The idea for vekkam was sown a night before an end semester exam, when a lack of proper revision material was realized. Then came together a team of students to build the product based on extensive primary and secondary research and powerful AI models to ensure students got what they wanted, and just a little bit more.
            </p>
            <p>
                NotebookLM, ChatGPT, DeepSeek, and other AI models fall short in what we do because they’re simply <strong>models.</strong> They don’t know what you need. But what you need is tools that “inject” you with bites of knowledge so you know what’s important by the time you step into the exam hall.
            </p>
            <p>
                Now you’re thinking, as hundreds did before you, <strong>how is this different from ChatGPT?</strong> Where do we even begin?
            </p>
            <p>
                We’ve built a model that understands your syllabus like no other. Generating insights, arming it with <strong>your own</strong> content, and never losing context, even at its breakneck pace. Here are some ways you can use our platform (no pressure, just some really awesome ideas you can’t do with any other app):
            </p>
            <ul class="list-disc list-inside space-y-2 pl-4">
                <li>Audio-record your class and upload it here for the model to remember and answer on the basis of, forever.</li>
                <li>Upload your whole course content and tear through 50 questions designed to test you, from memory to analysis level questions. Once you’re through this gauntlet, you’re ready for anything.</li>
                <li>Diagnose your weak points, which you can then learn from your personal TA Module that has all the context of every material you’ve uploaded.</li>
            </ul>
        </div>
    """, unsafe_allow_html=True)

    # --- Skepticism & Final Pitch ---
    st.markdown('<div class="max-w-4xl mx-auto text-center mt-12 p-6">', unsafe_allow_html=True)
    st.markdown("""
        <h3 class="text-3xl font-bold text-gray-900 mb-4">Skeptical? Understood.</h3>
        <p class="text-xl text-gray-700 mb-6">
            We got a free tier that gives you unlimited uploads, until 31 December 2025. <strong>What have you got to lose?</strong>
        </p>
        <p class="text-xl text-gray-700 mb-4">
            So we ask, do we prioritize extracurriculars or curriculars? Well, <strong>now you can do both.</strong>
        </p>
        <p class="text-xl text-gray-700 mb-6">
            Your ideal time table can’t be dictated by a teacher who knows nothing about you. This is the age of AI, and we’re here to bring you the time table that unlocks your potential—you very own time table, your very own <strong>6-hour battle plan</strong>, that will fetch you as many marks as your friend who studied smart for a day or more. Surprising, right?
        </p>
        <h3 class="text-2xl font-bold text-blue-700 mt-8 mb-4">Be the first to outlearn your syllabus.</h3>
        <a href="{auth_url}" class="text-xl font-semibold px-8 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition duration-150 shadow-lg">Try Us Out Now</a>
        <p class="text-md text-gray-500 mt-8">
            <strong>Want to Learn More?</strong> Contact us at <strong>team.vekkam@gmail.com</strong> or hit us up at <strong>+91 91103 12834!</strong>
        </p>
    """.format(auth_url=auth_url), unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)
    
    # --- Existing Footer/Final divider ---
    st.markdown('<style>.section-header { text-align: center; color: #004080; font-weight: 700; margin-top: 4rem; margin-bottom: 2rem; }</style>', unsafe_allow_html=True)
    st.markdown('<div class="section-header" style="margin-top:2rem;"></div>', unsafe_allow_html=True)
    st.divider()


# --- UI STATE FUNCTIONS for NOTE & LESSON ENGINE ---
def show_upload_state():
    st.header("Note & Lesson Engine: Upload")
    
    user_id = st.session_state.user_info.get('id') or st.session_state.user_info.get('email')
    can_proceed, reason, message = check_user_access(user_id)

    if not can_proceed:
        st.warning(message)
        show_paywall(user_id, st.session_state.user_info)
        return

    uploaded_files = st.file_uploader("Select files", accept_multiple_files=True, type=['mp3', 'm4a', 'wav', 'png', 'jpg', 'pptx', 'pdf'])
    if st.button("Process Files", type="primary") and uploaded_files:
        st.session_state.initial_files = uploaded_files
        st.session_state.current_state = 'processing'
        st.rerun()

def show_processing_state():
    st.header("Initial Processing...")
    with st.spinner("Extracting content from all files..."):
        results = []
        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(process_source, f, 'transcript' if f.type.startswith('audio/') else 'image' if f.type.startswith('image/') else 'pdf'): f for f in st.session_state.initial_files}
            for future in as_completed(futures): results.append(future.result())
        
        st.session_state.all_chunks = []
        st.session_state.all_chunks.extend([c for r in results if r and r['status'] == 'success' for c in r['chunks']])
        st.session_state.extraction_failures = [r for r in results if r and r['status'] == 'error']

    # Only update usage if the processing was successful for at least one file
    if any(r['status'] == 'success' for r in results if r):
        user_id = st.session_state.user_info.get('id') or st.session_state.user_info.get('email')
        update_user_usage(user_id)

    st.session_state.current_state = 'workspace'
    st.rerun()

def show_workspace_state():
    st.header("Vekkam Workspace")
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Controls & Outline")
        if st.button("Generate / Regenerate Full Outline"):
            with st.spinner("AI is analyzing all content..."):
                outline_json = generate_content_outline(st.session_state.all_chunks)
                if outline_json and "outline" in outline_json: st.session_state.outline_data = outline_json["outline"]
                else: st.error("Failed to generate outline. The AI couldn't structure the provided content. Try adding more context-rich files.")
        
        if 'outline_data' in st.session_state and st.session_state.outline_data:
            initial_text = "\n".join([item.get('topic', '') for item in st.session_state.outline_data])
            st.session_state.editable_outline = st.text_area("Editable Outline:", value=initial_text, height=300)
            st.session_state.synthesis_instructions = st.text_area("Synthesis Instructions (Optional):", height=100, placeholder="e.g., 'Explain this like I'm 15' or 'Focus on key formulas'")
            if st.button("Synthesize Notes", type="primary"):
                st.session_state.current_state = 'synthesizing'
                st.rerun()
    with col2:
        st.subheader("Source Explorer")
        if st.session_state.get('extraction_failures'):
            with st.expander("⚠️ Processing Errors", expanded=True):
                for failure in st.session_state.extraction_failures:
                    st.error(f"**{failure['source_id']}**: {failure['reason']}")
        with st.expander("Add More Files"):
            user_id = st.session_state.user_info.get('id') or st.session_state.user_info.get('email')
            can_add_files, _, message = check_user_access(user_id)
            
            if not can_add_files:
                st.info(message)

            new_files = st.file_uploader(
                "Upload more files", 
                accept_multiple_files=True, 
                key=f"uploader_{int(time.time())}",
                disabled=not can_add_files
            )
            
            if new_files and can_add_files:
                # In a full implementation, you would process these new files
                # and add them to the session state's 'all_chunks'.
                st.info("File adding is disabled in this demo, but the rate limit check is active.")

def show_synthesizing_state():
    st.header("Synthesizing Note Blocks...")
    st.session_state.final_notes = []
    topics = [line.strip() for line in st.session_state.editable_outline.split('\n') if line.strip()]
    chunks_map = {c['chunk_id']: c['text'] for c in st.session_state.all_chunks}
    original_outline_map = {item['topic']: item.get('relevant_chunks', []) for item in st.session_state.outline_data}
    bar = st.progress(0, "Starting synthesis...")
    for i, topic in enumerate(topics):
        bar.progress((i + 1) / len(topics), f"Synthesizing: {topic}")
        matched_chunks = original_outline_map.get(topic, [])
        if not matched_chunks:
            for original_topic, chunk_ids in original_outline_map.items():
                if topic in original_topic:
                    matched_chunks = chunk_ids; break
        text_to_synthesize = "\n\n---\n\n".join([chunks_map.get(cid, "") for cid in matched_chunks if cid in chunks_map])
        content = "Could not find source text for this topic." if not text_to_synthesize.strip() else synthesize_note_block(topic, text_to_synthesize, st.session_state.synthesis_instructions)
        st.session_state.final_notes.append({"topic": topic, "content": content, "source_chunks": matched_chunks})
    if st.session_state.get('user_info') and st.session_state.final_notes:
        user_id = st.session_state.user_info.get('id') or st.session_state.user_info.get('email')
        save_session_to_history(user_id, st.session_state.final_notes)
    st.session_state.current_state = 'results'
    st.rerun()

def show_results_state():
    st.header("Your Unified Notes")
    col_actions1, col_actions2, _ = st.columns([1, 1, 3])
    with col_actions1:
        if st.button("Go to Workspace"): st.session_state.current_state = 'workspace'; st.rerun()
    with col_actions2:
        if st.button("Start New Session"): reset_session(); st.rerun()
    st.divider()
    if 'selected_note_index' not in st.session_state: st.session_state.selected_note_index = None
    col1, col2 = st.columns([1, 2], gap="large")
    with col1:
        st.subheader("Topics")
        for i, block in enumerate(st.session_state.final_notes):
            if st.button(block['topic'], key=f"topic_{i}", use_container_width=True):
                st.session_state.selected_note_index = i
    with col2:
        st.subheader("Content Viewer")
        if st.session_state.selected_note_index is not None:
            selected_note = st.session_state.final_notes[st.session_state.selected_note_index]
            tab1, tab2 = st.tabs(["Formatted Output", "Source Chunks"])
            with tab1:
                st.markdown(f"### {selected_note['topic']}")
                st.markdown(selected_note['content'])
            with tab2:
                st.markdown("These are the raw text chunks used to generate the note.")
                st.code('\n\n'.join(selected_note['source_chunks']))
        else:
            st.info("👆 Select a topic from the left to view its details.")
    st.divider()
    st.subheader("Communicate with these Notes")
    if "messages" not in st.session_state: st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]): st.markdown(message["content"])
    if prompt := st.chat_input("Ask a question about the notes you just generated..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                current_notes_context = "\n\n".join([note['content'] for note in st.session_state.final_notes])
                response = answer_from_context(prompt, current_notes_context)
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

# --- UI STATE FUNCTION for PERSONAL TA ---
def show_personal_ta_ui():
    st.header("🎓 Your Personal TA")
    st.markdown("Ask questions and get answers based on the knowledge from all your past study sessions.")
    user_id = st.session_state.user_info.get('id') or st.session_state.user_info.get('email')
    user_data = load_user_data(user_id)
    if not user_data or not user_data["sessions"]:
        st.warning("You don't have any saved study sessions yet. Create some notes first to power up your TA!")
        return
    if "ta_messages" not in st.session_state: st.session_state.ta_messages = []
    for message in st.session_state.ta_messages:
        with st.chat_message(message["role"]): st.markdown(message["content"])
    if prompt := st.chat_input("Ask your Personal TA..."):
        st.session_state.ta_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Consulting your past notes..."):
                full_context = [f"Topic: {note['topic']}\nContent: {note['content']}" for session in user_data["sessions"] for note in session["notes"]]
                context_str = "\n\n---\n\n".join(full_context)
                response = answer_from_context(prompt, context_str)
                st.markdown(response)
        st.session_state.ta_messages.append({"role": "assistant", "content": response})

# --- MOCK TEST GENERATOR (Code unchanged) ---
def show_mock_test_generator():
    st.header("📝 Mock Test Generator")
    st.info("The Mock Test Generator is available to all users without limits.")

    if 'test_stage' not in st.session_state: st.session_state.test_stage = 'start'
    # ... (rest of mock test code is identical) ...
    if 'syllabus' not in st.session_state: st.session_state.syllabus = ""
    if 'questions' not in st.session_state: st.session_state.questions = {}
    if 'user_answers' not in st.session_state: st.session_state.user_answers = {}
    if 'score' not in st.session_state: st.session_state.score = {}
    if 'feedback' not in st.session_state: st.session_state.feedback = {}

    stage = st.session_state.test_stage
    stage_map = {
        'start': render_syllabus_input,
        'mcq_generating': lambda: render_generating_questions('mcq', 'mcq_test', 10),
        'mcq_test': lambda: render_mcq_test('mcq_results'),
        'mcq_results': lambda: render_mcq_results(70, 'vsa_generating'),
        'vsa_generating': lambda: render_generating_questions('vsa', 'vsa_test', 10),
        'vsa_test': lambda: render_subjective_test('vsa', 'vsa_results'),
        'vsa_results': lambda: render_subjective_results('vsa', 75, 'sa_generating'),
        'sa_generating': lambda: render_generating_questions('sa', 'sa_test', 5),
        'sa_test': lambda: render_subjective_test('sa', 'sa_results'),
        'sa_results': lambda: render_subjective_results('sa', 80, 'la_generating'),
        'la_generating': lambda: render_generating_questions('la', 'la_test', 3),
        'la_test': lambda: render_subjective_test('la', 'la_results'),
        'la_results': lambda: render_subjective_results('la', 90, 'final_results'),
        'final_results': render_final_results
    }
    
    if stage in stage_map:
        stage_map[stage]()
    else:
        st.session_state.test_stage = 'start'
        st.rerun()

def render_syllabus_input():
    st.subheader("Step 1: Provide Your Syllabus")
    st.write("Paste the syllabus or topic outline you want to be tested on. The more detail you provide, the better the questions will be.")
    syllabus_text = st.text_area("Syllabus / Topics", height=250, key="syllabus_input_area")
    if st.button("Generate My Test", type="primary"):
        if len(syllabus_text) < 50:
            st.warning("Please provide a more detailed syllabus for best results.")
        else:
            st.session_state.syllabus = syllabus_text
            st.session_state.test_stage = 'mcq_generating'
            st.rerun()

def render_generating_questions(q_type, next_stage, q_count):
    type_map = {'mcq': 'Multiple Choice', 'vsa': 'Very Short Answer', 'sa': 'Short Answer', 'la': 'Long Answer'}
    with st.spinner(f"Generating {type_map[q_type]} questions..."):
        questions_json = generate_questions_from_syllabus(st.session_state.syllabus, q_type, q_count)
        if questions_json and "questions" in questions_json:
            st.session_state.questions[q_type] = questions_json["questions"]
            st.session_state.test_stage = next_stage
            st.rerun()
        else:
            st.error(f"Failed to generate {type_map[q_type]} questions. Please try again with a different syllabus.")
            st.session_state.test_stage = 'start'
            st.rerun()

def render_mcq_test(next_stage='mcq_results'):
    st.subheader("Stage 1: Multiple Choice Questions")
    st.write("Pass Mark: 70%")
    mcq_questions = st.session_state.questions.get('mcq', [])
    with st.form("mcq_form"):
        user_answers = {}
        for i, q in enumerate(mcq_questions):
            st.markdown(f"**{i+1}. {q['question_text']}**")
            options = sorted(q['options'].items())
            selected_option = st.radio("Select your answer:", [opt[1] for opt in options], key=q['question_id'], label_visibility="collapsed")
            if selected_option:
                user_answers[q['question_id']] = next(key for key, value in options if value == selected_option)
            st.divider()
        if st.form_submit_button("Submit Answers"):
            st.session_state.user_answers['mcq'] = user_answers
            score = sum(1 for q in mcq_questions if user_answers.get(q['question_id']) == q['answer'])
            st.session_state.score['mcq'] = score
            st.session_state.test_stage = next_stage
            st.rerun()

def render_mcq_results(pass_mark_percent, next_stage):
    score = st.session_state.score.get('mcq', 0)
    total = len(st.session_state.questions.get('mcq', []))
    st.subheader(f"MCQ Results: You scored {score} / {total}")

    if 'feedback' not in st.session_state or 'mcq' not in st.session_state.feedback:
        with st.spinner("Analyzing your performance..."):
            feedback_text = generate_feedback_on_performance(score, total, st.session_state.questions.get('mcq', []), st.session_state.user_answers.get('mcq', {}), st.session_state.syllabus)
            st.session_state.feedback['mcq'] = feedback_text
    
    with st.container(border=True):
        st.subheader("💡 Performance Feedback")
        st.write(st.session_state.feedback.get('mcq', "No feedback generated."))
        
    if (score / total * 100) >= pass_mark_percent:
        st.success("Congratulations! You've passed this stage.")
        if st.button("Proceed to Very Short Answers", type="primary"):
            st.session_state.test_stage = next_stage
            st.rerun()
    else:
        st.error(f"You need to score at least {pass_mark_percent}% to proceed. Please review the material and try again.")
        if st.button("Restart Test"):
            for key in ['test_stage', 'syllabus', 'questions', 'user_answers', 'score', 'feedback']:
                if key in st.session_state: del st.session_state[key]
            st.rerun()

def render_subjective_test(q_type, next_stage):
    type_map = {'vsa': 'Very Short Answer', 'sa': 'Short Answer', 'la': 'Long Answer'}
    pass_map = {'vsa': '75%', 'sa': '80%', 'la': '90%'}
    st.subheader(f"Stage: {type_map[q_type]} Questions")
    st.write(f"Pass Mark: {pass_map[q_type]}")
    
    questions = st.session_state.questions.get(q_type, [])
    with st.form(f"{q_type}_form"):
        user_answers = {}
        for i, q in enumerate(questions):
            st.markdown(f"**{i+1}. {q['question_text']}**")
            answer = st.text_area("Your Answer:", key=f"{q_type}_answer_{q['question_id']}", height=150 if q_type != 'la' else 300)
            is_approach = st.checkbox("This is an outline of my approach", key=f"{q_type}_approach_{q['question_id']}")
            user_answers[q['question_id']] = {"answer": answer, "is_approach": is_approach}
            st.divider()
        if st.form_submit_button("Submit Answers"):
            st.session_state.user_answers[q_type] = user_answers
            st.session_state.test_stage = next_stage
            st.rerun()

def render_subjective_results(q_type, pass_mark_percent, next_stage):
    type_map = {'vsa': 'Very Short Answer', 'sa': 'Short Answer', 'la': 'Long Answer'}
    next_stage_map = {'sa_generating': 'Short Answers', 'la_generating': 'Long Answers', 'final_results': 'Final Results'}
    
    with st.spinner(f"Grading your {type_map[q_type]} answers... This may take a moment."):
        if 'score' not in st.session_state or q_type not in st.session_state.score:
            grading_result = grade_subjective_answers(
                q_type,
                st.session_state.questions.get(q_type, []),
                st.session_state.user_answers.get(q_type, {})
            )
            if grading_result:
                st.session_state.score[q_type] = grading_result['total_score']
                st.session_state.feedback[q_type] = grading_result
            else:
                st.error("Could not grade answers. Please try again.")
                st.session_state.score[q_type] = 0
                st.session_state.feedback[q_type] = {}

    score = st.session_state.score.get(q_type, 0)
    total = len(st.session_state.questions.get(q_type, []))
    feedback = st.session_state.feedback.get(q_type, {})

    st.subheader(f"{type_map[q_type]} Results: You scored {score} / {total}")

    with st.container(border=True):
        st.subheader("💡 Detailed Feedback")
        for fb in feedback.get('feedback_per_question', []):
            q_text = next((q['question_text'] for q in st.session_state.questions.get(q_type, []) if q['question_id'] == fb['question_id']), "Unknown Question")
            st.markdown(f"**Question:** {q_text}")
            st.markdown(f"**Score:** {fb['score_awarded']}/{fb['max_score']}")
            st.markdown(f"**Reasoning:** {fb['reasoning']}")
            st.divider()

    if (score / total * 100) >= pass_mark_percent:
        st.success("Congratulations! You've passed this stage.")
        if st.button(f"Proceed to {next_stage_map[next_stage]}", type="primary"):
            st.session_state.test_stage = next_stage
            st.rerun()
    else:
        st.error(f"You need to score at least {pass_mark_percent}% to proceed. Please review the feedback and try again.")
        if st.button(f"Restart {type_map[q_type]} Test"):
            st.session_state.test_stage = f"{q_type}_generating"
            if q_type in st.session_state.user_answers: del st.session_state.user_answers[q_type]
            if q_type in st.session_state.score: del st.session_state.score[q_type]
            if q_type in st.session_state.feedback: del st.session_state.feedback[q_type]
            st.rerun()

def render_final_results():
    st.balloons()
    st.header("🎉 Congratulations! You have completed the test! 🎉")
    st.markdown("You have demonstrated a strong understanding of the material across multiple cognitive levels.")

    st.subheader("Final Score Summary")
    
    if st.button("Take a New Test", type="primary"):
        for key in ['test_stage', 'syllabus', 'questions', 'user_answers', 'score', 'feedback']:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

# --- AI & Utility Functions for Mock Test (Code unchanged) ---
def get_bloom_level_name(level):
    if level is None: return "N/A"
    levels = {1: "Remembering", 2: "Understanding", 3: "Applying", 4: "Analyzing", 5: "Evaluating"}
    return levels.get(level, "Unknown")

@gemini_api_call_with_retry
def generate_questions_from_syllabus(syllabus_text, question_type, question_count):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    type_instructions = {
        'mcq': """Generate {question_count} Multiple Choice Questions (MCQs). Each question object must have: `question_id`, `taxonomy_level`, `question_text`, `options` (an object with A,B,C,D), and `answer` (the correct key).""",
        'vsa': """Generate {question_count} Very Short Answer questions (1-2 sentences). Each question object must have: `question_id`, `taxonomy_level`, `question_text`, and a `grading_rubric` string detailing the key points for a correct answer.""",
        'sa': """Generate {question_count} Short Answer questions (1-2 paragraphs). Each question object must have: `question_id`, `taxonomy_level`, `question_text`, and a `grading_rubric` string explaining the concepts and structure of a good answer.""",
        'la': """Generate {question_count} Long Answer questions (multiple paragraphs). Each question object must have: `question_id`, `taxonomy_level`, `question_text`, and a `grading_rubric` string providing a detailed breakdown of marks for structure, arguments, and conclusion."""
    }

    prompt = f"""
    You are an expert Question Paper Setter. Your task is to create a high-quality assessment based STRICTLY on the provided syllabus.
    {type_instructions[question_type].format(question_count=question_count)}

    **Syllabus:**
    ---
    {syllabus_text}
    ---

    **General Instructions:**
    1.  **Strict Syllabus Adherence:** Do NOT include questions on topics outside the syllabus.
    2.  **Bloom's Taxonomy:** Distribute questions across cognitive levels (1-5).
    3.  **Output Format:** Your entire output must be a single, valid JSON object with a root key "questions", which is a list of question objects.

    Generate the JSON now.
    """
    response = model.generate_content(prompt)
    return resilient_json_parser(response.text)

@gemini_api_call_with_retry
def grade_subjective_answers(q_type, questions, user_answers):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    prompt = f"""
    You are a strict but fair AI examiner. Your task is to grade a student's answers based on a provided rubric. Some students may provide a full answer, while others may outline their approach; you must grade both fairly. An outlined approach that hits all the key points in the rubric should receive full marks.

    **Instructions:**
    1.  For each question, compare the student's answer to the `grading_rubric`.
    2.  If the student's response is an 'approach', evaluate if the outlined steps logically lead to the correct answer as per the rubric.
    3.  Award a score of 1 for a correct answer/approach, and 0 for an incorrect one. No partial marks.
    4.  Provide a concise, one-sentence reasoning for your grading decision.
    5.  Output a single valid JSON object with a root key "total_score" (integer) and "feedback_per_question" (a list of objects).
    6.  Each object in the feedback list must have: `question_id`, `score_awarded` (0 or 1), `max_score` (always 1), and `reasoning` (string).

    **Student's Test Paper:**
    ---
    {json.dumps({"questions": questions, "answers": user_answers}, indent=2)}
    ---

    Grade the paper and generate the JSON output now.
    """
    response = model.generate_content(prompt)
    return resilient_json_parser(response.text)

@gemini_api_call_with_retry
def generate_feedback_on_performance(score, total, questions, user_answers, syllabus):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    incorrect_questions = []
    for q in questions:
        q_id = q['question_id']
        if user_answers.get(q_id) != q['answer']:
            incorrect_questions.append({ "question": q['question_text'], "your_answer": user_answers.get(q_id), "correct_answer": q['answer'] })
    
    prompt = f"""
    You are an encouraging academic coach. A student scored {score}/{total} on a test covering: {syllabus}.
    Their incorrect answers were: {json.dumps(incorrect_questions, indent=2)}.
    Provide concise, actionable feedback in bullet points, identifying patterns and suggesting specific areas for improvement.
    """
    response = model.generate_content(prompt)
    return response.text

# --- MASTERY ENGINE (Code unchanged) ---
@st.cache_resource
def get_google_search_service():
    """Initializes and returns the Google Custom Search API service, cached for performance."""
    try:
        api_key = st.secrets["google_search"]["api_key"]
        return build('customsearch', 'v1', developerKey=api_key)
    except KeyError:
        st.error("Google Search API key ('api_key') not found in st.secrets.toml. Please add it.")
        return None
    except Exception as e:
        st.error(f"Failed to build Google Search service: {e}")
        return None

def generate_allele_from_query(user_topic, context_chunks=None):
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    gene_name_response = model.generate_content(f"Provide a concise, 3-5 word conceptual name for the topic: '{user_topic}'. Output only the name.")
    gene_name = gene_name_response.text.strip().replace('"', '') if gene_name_response.text else user_topic.title()
    gene_id = f"USER_{hashlib.md5(user_topic.encode()).hexdigest()[:8].upper()}"
    
    service = get_google_search_service();
    if not service: return None
    try: cse_id = st.secrets["google_search"]["cse_id"]
    except KeyError: st.error("Google Search CSE ID ('cse_id') not found in st.secrets.toml."); return None

    search_queries, synthesis_prompt_template = [], ""
    if context_chunks:
        st.info("Context detected. Generating contextual search queries...")
        full_context_text = " ".join([chunk.get('text', '') for chunk in context_chunks])
        summary_response = model.generate_content(f"Summarize the key topics from this material in 2-3 sentences: {full_context_text[:8000]}")
        context_summary = summary_response.text
        query_gen_prompt = f"""A student is studying: "{context_summary}". They now want to learn about: "{user_topic}". Generate 3 specific Google search queries to find information connecting their existing knowledge to this new topic. Output ONLY a valid JSON object with a key "queries" which is a list of 3 strings."""
        queries_response = model.generate_content(query_gen_prompt)
        queries_json = resilient_json_parser(queries_response.text)
        search_queries = queries_json['queries'] if queries_json and 'queries' in queries_json else [f"{user_topic} in context of {context_summary[:50]}"]
        synthesis_prompt_template = f"""You are an expert tutor. A student's study material is about: "{context_summary}". They want to understand "{user_topic}". Based ONLY on the provided web search results, synthesize a clear explanation of "{user_topic}", connecting it to their existing knowledge.\n\n**Web Search Results:**\n---\n{{search_snippets}}\n---"""
    else:
        search_queries = [f"{user_topic} explanation", f"youtube video tutorial {user_topic}"]
        synthesis_prompt_template = f"""Based ONLY on the web search results, provide a clear, comprehensive explanation of '{user_topic}'.\n\n**Web Search Results:**\n---\n{{search_snippets}}\n---"""

    text_content, video_url = [], None
    st.write("Performing targeted web search...")
    for query in search_queries:
        try:
            res = service.cse().list(q=query, cx=cse_id, num=3).execute()
            for item in res.get('items', []):
                if "youtube.com/watch" in item.get('link', '') and not video_url: video_url = item.get('link')
                if item.get('snippet'): text_content.append(item.get('snippet'))
        except HttpError as e: st.error(f"Google Search API error: {e}. Check key, CSE ID, and quota."); return None
        except Exception as e: st.warning(f"Search failed for query '{query}': {e}"); time.sleep(1)

    if not text_content: st.error(f"Could not find relevant text for '{user_topic}'."); return None
    
    with st.spinner("Synthesizing explanation from search results..."):
        synthesis_prompt = synthesis_prompt_template.format(search_snippets=" ".join(text_content))
        final_explanation = model.generate_content(synthesis_prompt).text

    content_alleles = []
    if final_explanation: content_alleles.append({"type": "text", "content": final_explanation})
    if video_url: content_alleles.append({"type": "video", "url": video_url})
    return {"gene_id": gene_id, "gene_name": gene_name, "difficulty": 0, "content_alleles": content_alleles}

def show_mastery_engine():
    st.header("🏆 Mastery Engine")
    st.info("The Mastery Engine is available to all users without limits.")

    if 'mastery_stage' not in st.session_state: st.session_state.mastery_stage = 'course_selection'
    # ... (rest of mastery engine code is identical) ...
    if 'user_progress' not in st.session_state: st.session_state.user_progress = {}
    if 'current_genome' not in st.session_state: st.session_state.current_genome = None

    stage = st.session_state.mastery_stage
    stage_map = {'course_selection': render_course_selection, 'skill_tree': render_skill_tree, 'content_viewer': render_content_viewer, 'boss_battle': render_boss_battle}
    if stage in stage_map: stage_map[stage]()

def render_course_selection():
    st.subheader("Select Your Course or Create a New Concept")
    st.markdown("### Pre-built Courses")
    if st.button("Econ 101", use_container_width=True, type="primary"):
        st.session_state.current_genome = json.loads(json.dumps(ECON_101_GENOME)) # Deep copy
        progress = {}
        all_node_ids = {node['gene_id'] for node in st.session_state.current_genome['nodes']}
        destination_nodes = {edge['to'] for edge in st.session_state.current_genome['edges']}
        root_nodes = all_node_ids - destination_nodes
        for node_id in all_node_ids: progress[node_id] = 'unlocked' if node_id in root_nodes else 'locked'
        st.session_state.user_progress = progress
        st.session_state.mastery_stage = 'skill_tree'
        st.rerun()

    st.markdown("### Create Your Own Concept")
    user_interest = st.text_input("What concept are you interested in learning about?", key="user_allele_query")
    use_context = st.checkbox("Use context from 'Note & Lesson Engine' session", key="use_context", value=True)
    if st.button("Generate Concept Allele", use_container_width=True, disabled=not user_interest):
        context_chunks = st.session_state.get('all_chunks') if use_context else None
        if use_context and not context_chunks: st.warning("Contextual generation selected, but no files have been processed in the 'Note & Lesson Engine'. Falling back to non-contextual generation.")
        if st.session_state.current_genome is None: st.session_state.current_genome = {"subject": "My Custom Concepts", "version": "1.0", "nodes": [], "edges": []}
        with st.spinner(f"Generating concept for '{user_interest}'..."):
            new_allele = generate_allele_from_query(user_interest, context_chunks=context_chunks)
            if new_allele:
                if new_allele['gene_id'] not in {n['gene_id'] for n in st.session_state.current_genome['nodes']}:
                    st.session_state.current_genome['nodes'].append(new_allele)
                    st.success(f"Concept '{new_allele['gene_name']}' generated and unlocked!")
                else: st.info(f"Concept '{new_allele['gene_name']}' already exists.")
                st.session_state.user_progress[new_allele['gene_id']] = 'unlocked'
                st.session_state.mastery_stage = 'skill_tree'
                st.rerun()

def render_skill_tree():
    st.subheader(f"Skill Tree: {st.session_state.current_genome['subject']}")
    nodes, progress = st.session_state.current_genome['nodes'], st.session_state.user_progress
    for node in nodes:
        node_id, node_name, status = node['gene_id'], node['gene_name'], progress.get(node_id, 'locked')
        if status == 'mastered': st.success(f"**{node_name}** - ✅ Mastered!", icon="✅")
        elif status == 'unlocked':
            if st.button(f"🧠 Learn: {node_name}", key=node_id, use_container_width=True, type="primary"):
                st.session_state.selected_node_id = node_id; st.session_state.mastery_stage = 'content_viewer'; st.rerun()
        else: st.info(f"**{node_name}** - 🔒 Locked", icon="🔒")
        st.markdown('<p style="text-align: center; margin: 0; padding: 0;">↓</p>', unsafe_allow_html=True)
    st.markdown("---")
    if st.button("Back to Course Selection"): st.session_state.mastery_stage = 'course_selection'; st.rerun()

def render_content_viewer():
    node_id = st.session_state.selected_node_id
    node_data = next((n for n in st.session_state.current_genome['nodes'] if n['gene_id'] == node_id), None)
    if not node_data: st.error("Error: Could not load node data."); st.session_state.mastery_stage = 'skill_tree'; st.rerun(); return
    st.subheader(f"Learning: {node_data['gene_name']}")
    st.markdown("---")
    for allele in node_data['content_alleles']:
        if allele['type'] == 'text': st.markdown(allele['content'])
        elif allele['type'] == 'video': st.video(allele['url'])
    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    if col1.button("Back to Skill Tree"): st.session_state.mastery_stage = 'skill_tree'; st.rerun()
    if col2.button(f"⚔️ Challenge Boss: {node_data['gene_name']}", type="primary"):
        st.session_state.mastery_stage = 'boss_battle'
        syllabus_parts = [a['content'] for a in node_data['content_alleles'] if a['type'] == 'text']
        st.session_state.syllabus = f"Topic: {node_data['gene_name']}. Content: {' '.join(syllabus_parts)}"
        st.session_state.test_stage = 'mcq_generating'
        for key in ['questions', 'user_answers', 'score', 'feedback']:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

def render_boss_battle():
    if 'selected_node_id' not in st.session_state:
        st.warning("No concept selected for the boss battle. Redirecting to skill tree.")
        st.session_state.mastery_stage = 'skill_tree'
        for key in ['test_stage', 'syllabus', 'questions', 'user_answers', 'score', 'feedback']:
            if key in st.session_state: del st.session_state[key]
        st.rerun()
        return

    node_id = st.session_state.selected_node_id
    node_data = next((n for n in st.session_state.current_genome['nodes'] if n['gene_id'] == node_id), None)
    st.subheader(f"Boss Battle: {node_data['gene_name']}")
    
    if 'test_stage' not in st.session_state: st.session_state.test_stage = 'mcq_generating'
    stage = st.session_state.test_stage
    
    if stage == 'mcq_generating':
        render_generating_questions('mcq', 'boss_mcq_test', 10)
    elif stage == 'boss_mcq_test':
        render_mcq_test('boss_mcq_results')
    elif stage == 'boss_mcq_results':
        score = st.session_state.score.get('mcq', 0)
        total = 10
        st.subheader(f"Battle Results: You scored {score} / {total}")
        if score >= 7:
            st.balloons()
            st.success("Victory! You have mastered this concept.")
            st.session_state.user_progress[node_id] = 'mastered'
            for edge in st.session_state.current_genome.get('edges', []):
                if edge['from'] == node_id:
                    st.session_state.user_progress[edge['to']] = 'unlocked'
            if st.button("Return to Skill Tree", type="primary"):
                st.session_state.mastery_stage = 'skill_tree'
                for key in ['test_stage', 'syllabus', 'questions', 'user_answers', 'score', 'feedback']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()
        else:
            st.error("Defeated. The concept is not yet mastered. Review the material and try again.")
            if st.button("Return to Learning"):
                st.session_state.mastery_stage = 'content_viewer'
                for key in ['test_stage', 'syllabus', 'questions', 'user_answers', 'score', 'feedback']:
                    if key in st.session_state: del st.session_state[key]
                st.rerun()


# --- MAIN APP ---
def main():
    if 'user_info' not in st.session_state: st.session_state.user_info = None
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
    except KeyError:
        st.error("Gemini API key ('api_key') not found in st.secrets.toml. Please add it."); st.stop()

    flow = get_google_flow()
    auth_code = st.query_params.get("code")

    if auth_code and not st.session_state.user_info:
        try:
            flow.fetch_token(code=auth_code)
            user_info = build('oauth2', 'v2', credentials=flow.credentials).userinfo().get().execute()
            st.session_state.user_info = user_info
            st.query_params.clear(); st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {e}"); st.session_state.user_info = None
    
    if not st.session_state.user_info:
        st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} [data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        # New Landing View Toggle Logic
        if 'landing_view' not in st.session_state:
            st.session_state.landing_view = 'marketing'
            
        if st.session_state.landing_view == 'marketing':
            show_landing_page(auth_url)
        elif st.session_state.landing_view == 'policies':
            show_policies_page(auth_url)
        
        return

    # --- HIDE STREAMLIT STYLE ---
    st.markdown("""
        <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            footer {visibility: hidden;}
        </style>
        """, unsafe_allow_html=True)

    st.sidebar.title("Vekkam Engine")
    user = st.session_state.user_info
    user_id = user.get('id') or user.get('email')
    st.sidebar.image(user['picture'], width=80)
    st.sidebar.subheader(f"Welcome, {user['given_name']}")
    if st.sidebar.button("Logout"): st.session_state.clear(); st.rerun()
    st.sidebar.divider()
    
    # --- Subscription Status in Sidebar ---
    st.sidebar.subheader("Subscription Status")
    user_data = load_user_data(user_id)
    tier = user_data.get('user_tier', 'free')
    st.sidebar.metric("Your Tier", tier.title())
    if tier == 'free':
        analyses_left = FREE_TIER_LIMIT - user_data.get('total_analyses', 0)
        st.sidebar.write(f"Analyses Left: **{analyses_left}**")
        if analyses_left <= 0 and st.sidebar.button("Upgrade to Premium"):
             st.session_state.show_upgrade_flow = True # A flag to trigger paywall
    else: # Paid tier
        today_str = datetime.now().strftime("%Y-%m-%d")
        daily_count = user_data.get('daily_analyses_count', 0)
        if user_data.get('last_analysis_date') != today_str:
            daily_count = 0 # Reset for the new day
        analyses_left = PAID_TIER_DAILY_LIMIT - daily_count
        st.sidebar.write(f"Daily Analyses Left: **{analyses_left}/{PAID_TIER_DAILY_LIMIT}**")
    st.sidebar.divider()


    st.sidebar.subheader("Study Session History")
    if not user_data["sessions"]:
        st.sidebar.info("Your saved sessions will appear here.")
    else:
        for i, session in enumerate(list(user_data["sessions"])):
            with st.sidebar.expander(f"{session.get('timestamp', 'N/A')} - {session.get('title', 'Untitled')}"):
                is_editing = st.session_state.get('editing_session_id') == session.get('id')
                if is_editing:
                    new_title = st.text_input("Edit Title", value=session.get('title', ''), key=f"edit_title_{session.get('id')}", label_visibility="collapsed")
                    col1, col2 = st.columns(2)
                    if col1.button("Save", key=f"save_{session.get('id')}", type="primary", use_container_width=True):
                        user_data["sessions"][i]['title'] = new_title; save_user_data(user_id, user_data); st.session_state.editing_session_id = None; st.rerun()
                    if col2.button("Cancel", key=f"cancel_{session.get('id')}", use_container_width=True):
                        st.session_state.editing_session_id = None; st.rerun()
                else:
                    for note in session.get('notes', []): st.write(f"• {note.get('topic', 'No Topic')}")
                    st.divider()
                    col1, col2, col3 = st.columns(3)
                    if col1.button("👁️ View", key=f"view_{session.get('id')}", use_container_width=True):
                        reset_session(); st.session_state.tool_choice = "Note & Lesson Engine"; st.session_state.final_notes = session.get('notes', []); st.session_state.current_state = 'results'; st.session_state.messages = []; st.rerun()
                    if col2.button("✏️ Edit", key=f"edit_{session.get('id')}", use_container_width=True):
                        st.session_state.editing_session_id = session.get('id'); st.rerun()
                    if col3.button("🗑️ Delete", key=f"del_{session.get('id')}", type="secondary", use_container_width=True):
                        user_data["sessions"].pop(i); save_user_data(user_id, user_data); st.rerun()

    st.sidebar.divider()
    tool_choice = st.sidebar.radio("Select a Tool", ("Note & Lesson Engine", "Personal TA", "Mock Test Generator", "Mastery Engine"), key='tool_choice')
    
    if 'last_tool_choice' not in st.session_state: st.session_state.last_tool_choice = tool_choice
    if st.session_state.last_tool_choice != tool_choice:
        st.session_state.last_tool_choice = tool_choice
        reset_session(); st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("API Status")
    st.sidebar.write(f"Gemini: **{check_gemini_api()}**")

    # --- Tool Routing ---
    # Handle the upgrade flow if triggered from sidebar
    if st.session_state.get('show_upgrade_flow'):
        show_paywall(user_id, st.session_state.user_info)
        # un-set the flag so it doesn't persist
        if 'show_upgrade_flow' in st.session_state:
            del st.session_state['show_upgrade_flow']
    elif tool_choice == "Note & Lesson Engine":
        if 'current_state' not in st.session_state: st.session_state.current_state = 'upload'
        state_map = { 'upload': show_upload_state, 'processing': show_processing_state, 'workspace': show_workspace_state, 'synthesizing': show_synthesizing_state, 'results': show_results_state }
        state_map.get(st.session_state.current_state, show_upload_state)()
    elif tool_choice == "Personal TA": show_personal_ta_ui()
    elif tool_choice == "Mock Test Generator": show_mock_test_generator()
    elif tool_choice == "Mastery Engine": show_mastery_engine()

if __name__ == "__main__":
    main()
