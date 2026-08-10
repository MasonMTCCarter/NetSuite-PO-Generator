import streamlit as st
import pandas as pd
import google.generativeai as genai
import pypdf
import json
import io
import os
import base64

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NetSuite PO Import Generator",
    layout="centered",
    page_icon="📋",
)

# ---------------------------------------------------------------------------
# Initialize Session State
# ---------------------------------------------------------------------------
# This prevents the app from forgetting the data when the user clicks 'Download'
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None

# ---------------------------------------------------------------------------
# Helper: Load Logo as Base64 (for embedded HTML rendering)
# ---------------------------------------------------------------------------
LOGO_PATH = "logo.png"  

def get_base64_image(image_path: str) -> str:
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{encoded}"
    return ""

logo_base64 = get_base64_image(LOGO_PATH)

# ---------------------------------------------------------------------------
# Windows 11 "Fluent Design" styling + Brand Colors + Uploader Fixes
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://fonts.cdnfonts.com/css/segoe-ui-4');

        :root {
            --win-accent: #0051ba;       
            --win-accent-hover: #003459; 
            --win-crimson: #e8000d;      
            --win-yellow: #ffc82d;       
            --win-bg: #f4f6f8;
            --win-card: #ffffff;
            --win-border: #dde5ed;       
            --win-text: #333333;         
            --win-subtext: #5b6770;
            --win-radius: 8px;
        }

        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Segoe UI Variable', -apple-system, sans-serif;
        }

        .stApp {
            background: radial-gradient(circle at 20% 0%, #eaf1fb 0%, #f4f6f8 40%, #f4f6f8 100%);
        }

        #MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stToolbar"] {
            visibility: hidden;
            display: none !important;
        }

        [data-testid="stAppViewContainer"] * ,
        [data-testid="stSidebar"] * {
            color: var(--win-text) !important;
        }
        [data-testid="stAppViewContainer"] ::placeholder {
            color: #666666 !important;
            opacity: 1 !important;
        }

        /* --- Fix for the dark File Uploader --- */
        [data-testid="stFileUploadDropzone"] {
            background-color: #FBFBFB !important;
            border: 1px dashed var(--win-border) !important;
        }
        [data-testid="stFileUploadDropzone"] * {
            color: var(--win-text) !important;
        }
        [data-testid="stFileUploadDropzone"] button {
            background-color: #FFFFFF !important;
            border: 1px solid var(--win-border) !important;
            color: var(--win-text) !important;
        }
        /* -------------------------------------- */

        .win11-titlebar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 24px;
            margin: -1rem -1rem 1.5rem -1rem;
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 3px solid var(--win-crimson);
        }
        .win11-titlebar .title-group {
            display: flex;
            flex-direction: column;
        }
        .win11-titlebar h1 {
            font-size: 22px;
            font-weight: 600;
            margin: 0;
            color: var(--win-text) !important;
        }
        .win11-titlebar p {
            margin: 0;
            font-size: 14px;
            color: var(--win-subtext) !important;
        }
        .win11-titlebar .header-logo {
            height: 52px;
            width: auto;
            object-fit: contain;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--win-card);
            border: 1px solid var(--win-border);
            border-radius: var(--win-radius);
            box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
            padding: 4px;
        }

        .win11-section-label {
            font-size: 16px;
            font-weight: 600;
            color: var(--win-text);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
            padding-left: 8px;
            border-left: 3px solid var(--win-crimson);
        }

        .stTextInput > div > div > input,
        .stTextArea textarea {
            background-color: #FBFBFB;
            border: 1px solid var(--win-border);
            border-radius: 6px;
            color: var(--win-text);
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);
            font-size: 15px;
        }
        .stTextInput > div > div > input:focus,
        .stTextArea textarea:focus {
            border: 1.5px solid var(--win-accent);
            box-shadow: 0 0 0 1px var(--win-accent);
        }

        [data-testid="stAppViewContainer"] .stButton > button {
            background: var(--win-accent) !important;
            color: #FFFFFF !important;
            border: none;
            border-radius: 6px;
            padding: 0.6em 1.4em;
            font-weight: 600;
            font-size: 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.15);
            transition: background 0.15s ease-in-out, transform 0.05s ease-in-out;
        }
        [data-testid="stAppViewContainer"] .stButton > button p {
            color: #FFFFFF !important;
            font-size: 16px;
        }
        .stButton > button:hover {
            background: var(--win-accent-hover) !important;
        }
        .stButton > button:active {
            transform: scale(0.98);
        }

        button[data-baseweb="tab"] {
            font-size: 15px;
            color: var(--win-subtext);
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--win-accent);
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Title bar
# ---------------------------------------------------------------------------
logo_html = f'<img class="header-logo" src="{logo_base64}" alt="Logo">' if logo_base64 else ""

st.markdown(
    f"""
    <div class="win11-titlebar">
        <div class="title-group">
            <h1>NetSuite PO &amp; Item Import Generator</h1>
            <p>Convert order text or invoices into a NetSuite-ready import file</p>
        </div>
        {logo_html}
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Gemini API key
# ---------------------------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY") or st.sidebar.text_input("Gemini API Key", type="password")

if not api_key:
    st.warning("Please provide a Gemini API Key in Streamlit Secrets or the sidebar to continue.")
    st.stop()

genai.configure(api_key=api_key)

# ---------------------------------------------------------------------------
# Mapping rules
# ---------------------------------------------------------------------------
MAPPING_RULES = """
Mappings / Rules for NetSuite Import:
- Mappings for PR #:
  * 648-1 -> Customer/Project: "JF Taylor : 648 USAF FA FuTs", Custom WBS Task: "648-1 Materials"
  * 648-2 -> Customer/Project: "JF Taylor : 648 USAF FA FuTs", Custom WBS Task: "648-2 Materials"
  * 648-3 -> Customer/Project: "JF Taylor : 648 USAF FA FuTs", Custom WBS Task: "648-3 Materials"
  * 777   -> Customer/Project: "Newton Design, LLC : 777 Overhead", Custom WBS Task: "777 Materials"
  * 505   -> Customer/Project: "Lockheed Martin : 505 FuT 5", Custom WBS Task: "Materials"
  * 506   -> Customer/Project: "Lockheed Martin : 506 FuT 6", Custom WBS Task: "506 Materials"
- Ensure Manufacturer Part Number is used (NOT vendor part numbers).
- Exclude 'Form' and 'Vendor' columns.
- Format output strict JSON list of objects.
"""

# ---------------------------------------------------------------------------
# UI Inputs
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<div class="win11-section-label">🧾 1. Order Details</div>', unsafe_allow_html=True)
    po_number = st.text_input("PO Number", placeholder="e.g., PO1536")

with st.container(border=True):
    st.markdown('<div class="win11-section-label">📥 2. Input Method</div>', unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["📋 Copy & Paste Text", "📄 Upload PDF Invoice"])
    
    extracted_text = ""
    is_scanned_pdf = False
    
    with tab1:
        text_input = st.text_area("Paste Order Raw Text Here", height=200, label_visibility="collapsed", placeholder="Paste the raw order text here...")
        if text_input:
            extracted_text = text_input
            
    with tab2:
        uploaded_pdf = st.file_uploader("Upload Invoice PDF", type=["pdf"], label_visibility="collapsed")
        if uploaded_pdf:
            pdf_reader = pypdf.PdfReader(uploaded_pdf)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() or ""
            
            # Check for scanned PDF (no machine-readable text)
            if not extracted_text.strip():
                is_scanned_pdf = True
                st.error("⚠️ No text could be read from this PDF. If this is a scanned document or an image, please use the 'Copy & Paste Text' tab instead.")

with st.container(border=True):
    st.markdown('<div class="win11-section-label">⚙️ 3. Custom Instructions (Optional)</div>', unsafe_allow_html=True)
    custom_instructions = st.text_area(
        "Additional rules or overrides",
        placeholder="Add any specific rules, overrides, or notes here...",
        height=100,
        label_visibility="collapsed",
    )

st.write("")
process_clicked = st.button("🚀 Process Order & Generate CSV", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Processing Action
# ---------------------------------------------------------------------------
if process_clicked:
    # Clear previous results if running a new order
    st.session_state.processed_df = None
    
    if not po_number.strip():
        st.error("Please enter a PO Number.")
    elif is_scanned_pdf:
        st.error("Cannot process an unreadable PDF. Please use the Copy & Paste tab.")
    elif not extracted_text.strip():
        st.error("Please provide order information via text or PDF.")
    else:
        with st.spinner("Analyzing order details and mapping NetSuite fields..."):
            try:
                # Updated to use Gemini Flash 3.6
                model = genai.GenerativeModel("gemini-3.6-flash")

                prompt = f"""
                You are a data extraction assistant for NetSuite imports.
                Extract line items from the following raw text and output a JSON array of objects.

                Order Info:
                {extracted_text}

                Context & Rules:
                - PO Number to use for all items: {po_number}
                - Custom Instructions: {custom_instructions}
                {MAPPING_RULES}

                CRITICAL VERBATIM EXTRACTION RULES:
                1. "PR #": Copy the reference / PR # string EXACTLY as it appears in the raw source text. DO NOT truncate, cut off, trim, or cap string length under any circumstances (do not limit to 40 characters).
                2. "Item Description": Copy the description EXACTLY word-for-word as printed in the source text. DO NOT change the casing (preserve exact original casing, do NOT apply Title Case), and DO NOT add or remove punctuation or quotes.

                Return ONLY a raw JSON array where each item has keys:
                "Line Item" (integer starting at 1),
                "Customer/Project" (string based on mapping),
                "Custom WBS Task" (string based on mapping),
                "PO" (string, e.g., "{po_number}"),
                "PR #" (string extracted EXACTLY verbatim without truncation),
                "Manufacturer Part Number" (string),
                "Item Description" (string extracted EXACTLY verbatim with original casing and punctuation),
                "Qty" (integer),
                "Cost Price" (float),
                "Amount" (float)
                """

                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.1}
                )

                clean_json_str = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json_str)

                # Save successfully processed data to session state
                st.session_state.processed_df = pd.DataFrame(data)
                st.success("Successfully processed line items!")

            except json.JSONDecodeError:
                st.error("⚠️ The AI had trouble formatting this order into the correct structure. Please click 'Process Order' to try again.")
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                    st.error("🛑 The Gemini API rate limit has been reached. Please wait a minute and try again.")
                else:
                    st.error(f"⚠️ An unexpected error occurred: {str(e)}\n\nPlease try again.")

# ---------------------------------------------------------------------------
# Results Display (Editable & Stateful)
# ---------------------------------------------------------------------------
if st.session_state.processed_df is not None:
    st.metric(label="Line Items Extracted", value=len(st.session_state.processed_df))

    with st.container(border=True):
        st.markdown('<div class="win11-section-label">📊 Data Preview & Edit</div>', unsafe_allow_html=True)
        st.info("💡 **Tip:** You can double-click any cell below to make manual corrections before downloading.")
        
        # Use data_editor instead of dataframe so changes can be made before export
        edited_df = st.data_editor(
            st.session_state.processed_df, 
            use_container_width=True, 
            num_rows="dynamic",
            hide_index=True
        )

    # Export using the potentially edited DataFrame
    csv_buffer = io.BytesIO()
    edited_df.to_csv(csv_buffer, index=False)

    st.download_button(
        label="📥 Download NetSuite CSV",
        data=csv_buffer.getvalue(),
        file_name=f"{po_number}_NetSuite_Import.csv",
        mime="text/csv"
    )
