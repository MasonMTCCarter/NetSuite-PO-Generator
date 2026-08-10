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

# Initialize Session State
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None

# Helper: Load Logo as Base64
LOGO_PATH = "logo.png"  

def get_base64_image(image_path: str) -> str:
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{encoded}"
    return ""

logo_base64 = get_base64_image(LOGO_PATH)

# ---------------------------------------------------------------------------
# Enhanced High-Accessibility CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://fonts.cdnfonts.com/css/segoe-ui-4');

        :root {
            --win-accent: #0051ba;       
            --win-accent-hover: #003459; 
            --win-crimson: #e8000d;      
            --win-bg: #f4f6f8;
            --win-card: #ffffff;
            --win-border: #cccccc;       
            --win-text: #111111;         
            --win-subtext: #444444;
            --win-radius: 8px;
        }

        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Segoe UI Variable', -apple-system, sans-serif;
            font-size: 16px;
        }

        .stApp {
            background: radial-gradient(circle at 20% 0%, #eaf1fb 0%, #f4f6f8 40%, #f4f6f8 100%);
        }

        #MainMenu, footer, [data-testid="stStatusWidget"], [data-testid="stToolbar"] {
            visibility: hidden;
            display: none !important;
        }

        /* Title Bar */
        .win11-titlebar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 24px;
            margin: -1rem -1rem 1.5rem -1rem;
            background: #ffffff;
            border-bottom: 4px solid var(--win-crimson);
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .win11-titlebar h1 {
            font-size: 26px;
            font-weight: 700;
            margin: 0;
            color: var(--win-text) !important;
        }
        .win11-titlebar p {
            margin: 4px 0 0 0;
            font-size: 16px;
            color: var(--win-subtext) !important;
        }
        .win11-titlebar .header-logo {
            height: 56px;
            width: auto;
            object-fit: contain;
        }

        /* Section Headings */
        .win11-section-label {
            font-size: 18px;
            font-weight: 700;
            color: var(--win-text);
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
            padding-left: 8px;
            border-left: 4px solid var(--win-crimson);
        }

        /* Larger Text Inputs */
        .stTextInput input, .stTextArea textarea {
            font-size: 16px !important;
            padding: 10px !important;
            border: 1px solid var(--win-border) !important;
        }

        /* Giant Action Button */
        [data-testid="stAppViewContainer"] .stButton > button {
            background: var(--win-accent) !important;
            color: #FFFFFF !important;
            border-radius: 8px;
            padding: 0.8em 1.5em;
            font-size: 20px !important;
            font-weight: 700;
            width: 100%;
        }
        [data-testid="stAppViewContainer"] .stButton > button p {
            color: #FFFFFF !important;
            font-size: 20px !important;
            font-weight: 700;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header & Instructions
# ---------------------------------------------------------------------------
logo_html = f'<img class="header-logo" src="{logo_base64}" alt="Logo">' if logo_base64 else ""

st.markdown(
    f"""
    <div class="win11-titlebar">
        <div>
            <h1>NetSuite Import File Generator</h1>
            <p>Convert order text or invoices into NetSuite format</p>
        </div>
        {logo_html}
    </div>
    """,
    unsafe_allow_html=True,
)

# Quick Step-by-Step Guide
st.info("""
👉 **How to use:**
1. Type in your **PO Number** below.
2. Upload a **PDF Invoice** or copy/paste order text.
3. Click the big blue **"Process Order & Generate CSV"** button at the bottom.
""")

# ---------------------------------------------------------------------------
# Secure API Key Check (Hidden from UI)
# ---------------------------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ System Configuration Missing: API Key was not found. Please contact support.")
    st.stop()

genai.configure(api_key=api_key)

# ---------------------------------------------------------------------------
# Mapping Rules (Internal System Rules)
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
# Inputs Section
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<div class="win11-section-label">1️⃣ Step 1: Enter PO Number</div>', unsafe_allow_html=True)
    po_number = st.text_input("PO Number", placeholder="Example: PO1536", help="Enter the Purchase Order number for this import.")

extracted_text = ""
is_scanned_pdf = False

with st.container(border=True):
    st.markdown('<div class="win11-section-label">2️⃣ Step 2: Provide Order Info</div>', unsafe_allow_html=True)
    
    # Combined, clear selection method
    input_type = st.radio(
        "Choose how you want to provide order details:",
        ["📄 Upload PDF Invoice", "📋 Copy & Paste Order Text"],
        horizontal=True
    )
    
    if input_type == "📄 Upload PDF Invoice":
        uploaded_pdf = st.file_uploader("Upload PDF file", type=["pdf"])
        if uploaded_pdf:
            pdf_reader = pypdf.PdfReader(uploaded_pdf)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() or ""
            
            if not extracted_text.strip():
                is_scanned_pdf = True
                st.error("⚠️ This PDF appears to be a scanned image or photo. Please select 'Copy & Paste Order Text' above and paste the details manually.")
    else:
        text_input = st.text_area("Paste order details here:", height=180, placeholder="Paste raw order text or copy-pasted invoice content here...")
        if text_input:
            extracted_text = text_input

# Advanced options hidden inside an expander so it doesn't distract
with st.expander("⚙️ Special Instructions / Overrides (Optional)"):
    custom_instructions = st.text_area(
        "Notes or custom rules for this specific order:",
        placeholder="e.g., Override part number for line 2...",
        height=80,
    )

st.write("")
process_clicked = st.button("🚀 Process Order & Generate CSV", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Processing Logic
# ---------------------------------------------------------------------------
if process_clicked:
    st.session_state.processed_df = None
    
    if not po_number.strip():
        st.warning("⚠️ Please fill in the PO Number before continuing.")
    elif is_scanned_pdf:
        st.error("⚠️ Unable to extract text from scanned PDF. Please paste the order text manually.")
    elif not extracted_text.strip():
        st.warning("⚠️ Please upload a PDF or paste order text in Step 2.")
    else:
        with st.spinner("⏳ Analyzing order details... Please wait standard 5-10 seconds."):
            try:
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
                1. "PR #": Copy the reference / PR # string EXACTLY as it appears in the raw source text. DO NOT truncate, cut off, trim, or cap string length.
                2. "Item Description": Copy the description EXACTLY word-for-word as printed in the source text. Preserve exact original casing and punctuation.

                Return ONLY a raw JSON array where each item has keys:
                "Line Item" (integer starting at 1),
                "Customer/Project" (string based on mapping),
                "Custom WBS Task" (string based on mapping),
                "PO" (string, e.g., "{po_number}"),
                "PR #" (string extracted EXACTLY verbatim without truncation),
                "Manufacturer Part Number" (string),
                "Item Description" (string extracted EXACTLY verbatim),
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

                st.session_state.processed_df = pd.DataFrame(data)
                st.success("✅ Order successfully processed!")

            except json.JSONDecodeError:
                st.error("⚠️ The system had trouble reading the format. Please try clicking 'Process Order' once more.")
            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                    st.error("⏳ Server is busy. Please wait 1 minute and click the button again.")
                else:
                    st.error("⚠️ Something unexpected happened. Please verify your order text and try again.")

# ---------------------------------------------------------------------------
# Data Preview & Export
# ---------------------------------------------------------------------------
if st.session_state.processed_df is not None:
    st.markdown("---")
    st.subheader("3️⃣ Step 3: Review & Download")
    st.write(f"Found **{len(st.session_state.processed_df)}** items in this order.")

    with st.container(border=True):
        st.markdown("💡 **Tip:** You can double-click any box below to edit values before downloading.")
        
        edited_df = st.data_editor(
            st.session_state.processed_df, 
            use_container_width=True, 
            num_rows="dynamic",
            hide_index=True
        )

    csv_buffer = io.BytesIO()
    edited_df.to_csv(csv_buffer, index=False)

    st.download_button(
        label="📥 Download NetSuite CSV File",
        data=csv_buffer.getvalue(),
        file_name=f"{po_number}_NetSuite_Import.csv",
        mime="text/csv"
    )
