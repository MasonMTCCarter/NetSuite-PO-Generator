import streamlit as st
import pandas as pd
import google.generativeai as genai
import pypdf
import json
import io

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NetSuite PO Import Generator",
    layout="wide",
    page_icon="📦",
)

# ---------------------------------------------------------------------------
# Windows 11 "Fluent Design" styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        @import url('https://fonts.cdnfonts.com/css/segoe-ui-4');

        :root {
            --win-accent: #0051BA;       /* Kansas Blue */
            --win-accent-hover: #003459; /* Night (dark navy) */
            --win-crimson: #E8000D;      /* Crimson */
            --win-yellow: #FFC82D;       /* Jayhawk Yellow */
            --win-bg: #F4F6F8;
            --win-card: #FFFFFF;
            --win-border: #DDE5ED;       /* Steam */
            --win-text: #1B1B1B;
            --win-subtext: #5B6770;      /* darkened Signature Gray for readability */
            --win-radius: 8px;
        }

        html, body, [class*="css"] {
            font-family: 'Segoe UI', 'Segoe UI Variable', -apple-system, sans-serif;
        }

        /* Overall app background - subtle KU-tinted gradient */
        .stApp {
            background: radial-gradient(circle at 20% 0%, #eaf1fb 0%, #f4f6f8 40%, #f4f6f8 100%);
        }

        /* Hide default Streamlit chrome */
        #MainMenu, footer {visibility: hidden;}

        /* -------------------------------------------------------------
           Force readable text everywhere, regardless of whether the
           underlying Streamlit theme is set to light or dark. Without
           this, widget labels/radio text inherit the theme's default
           color (often white) and become invisible on our light cards.
        ------------------------------------------------------------- */
        [data-testid="stAppViewContainer"] * ,
        [data-testid="stSidebar"] * {
            color: var(--win-text) !important;
        }
        [data-testid="stAppViewContainer"] ::placeholder {
            color: #9A9A9A !important;
            opacity: 1 !important;
        }

        /* Title bar */
        .win11-titlebar {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 18px 24px;
            margin: -1rem -1rem 1.5rem -1rem;
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-bottom: 3px solid var(--win-crimson);
        }
        .win11-titlebar .icon-badge {
            width: 42px;
            height: 42px;
            border-radius: 10px;
            background: linear-gradient(135deg, #0051BA, #003459);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 2px 6px rgba(0, 81, 186, 0.35);
        }
        .win11-titlebar h1 {
            font-size: 22px;
            font-weight: 600;
            margin: 0;
            color: var(--win-text) !important;
        }
        .win11-titlebar p {
            margin: 0;
            font-size: 13px;
            color: var(--win-subtext) !important;
        }
        .win11-titlebar .icon-badge {
            color: #FFFFFF !important;
        }

        /* Card container (used for bordered st.container) */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--win-card);
            border: 1px solid var(--win-border);
            border-radius: var(--win-radius);
            box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
            padding: 4px;
        }

        /* Section labels - small crimson accent tab, like the brand page's dividers */
        .win11-section-label {
            font-size: 13px;
            font-weight: 600;
            color: var(--win-text);
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
            padding-left: 8px;
            border-left: 3px solid var(--win-crimson);
        }

        /* Inputs */
        .stTextInput > div > div > input,
        .stTextArea textarea {
            background-color: #FBFBFB;
            border: 1px solid var(--win-border);
            border-radius: 6px;
            color: var(--win-text);
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);
        }
        .stTextInput > div > div > input:focus,
        .stTextArea textarea:focus {
            border: 1.5px solid var(--win-accent);
            box-shadow: 0 0 0 1px var(--win-accent);
        }

        /* Radio buttons */
        .stRadio > div {
            gap: 4px;
        }
        .stRadio div[role="radiogroup"] label {
            background: #FBFBFB;
            border: 1px solid var(--win-border);
            padding: 8px 12px;
            border-radius: 6px;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
        }
        .stRadio div[role="radiogroup"] label:has(input:checked) {
            border: 1.5px solid var(--win-accent);
            background: #F0F7FF;
        }

        /* Primary button - Fluent accent style */
        [data-testid="stAppViewContainer"] .stButton > button {
            background: var(--win-accent) !important;
            color: #FFFFFF !important;
            border: none;
            border-radius: 6px;
            padding: 0.55em 1.4em;
            font-weight: 600;
            font-size: 14px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.15);
            transition: background 0.15s ease-in-out, transform 0.05s ease-in-out;
        }
        [data-testid="stAppViewContainer"] .stButton > button p {
            color: #FFFFFF !important;
        }
        .stButton > button:hover {
            background: var(--win-accent-hover) !important;
        }
        .stButton > button:active {
            transform: scale(0.98);
        }

        /* Download button - Crimson, the secondary KU brand color */
        [data-testid="stAppViewContainer"] .stDownloadButton > button {
            background: #FFFFFF !important;
            color: var(--win-crimson) !important;
            border: 1.5px solid var(--win-crimson);
            border-radius: 6px;
            font-weight: 600;
            padding: 0.55em 1.4em;
        }
        [data-testid="stAppViewContainer"] .stDownloadButton > button p {
            color: var(--win-crimson) !important;
        }
        .stDownloadButton > button:hover {
            background: #FFF0F0 !important;
        }

        /* Dataframe */
        [data-testid="stDataFrame"] {
            border: 1px solid var(--win-border);
            border-radius: var(--win-radius);
            overflow: hidden;
        }

        /* Alerts (success / warning / error) - rounded Fluent InfoBar look */
        div[data-testid="stAlert"] {
            border-radius: var(--win-radius);
            border: 1px solid var(--win-border);
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: #FBFBFB;
            border-right: 1px solid var(--win-border);
        }

        /* Spinner text */
        .stSpinner > div {
            font-size: 14px;
            color: var(--win-subtext);
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Title bar
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="win11-titlebar">
        <div class="icon-badge">📦</div>
        <div>
            <h1>NetSuite PO &amp; Item Import Generator</h1>
            <p>Convert order text or invoices into a NetSuite-ready import file</p>
        </div>
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
# Mapping rules (unchanged logic)
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
# UI Inputs - laid out as Fluent-style cards
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2, gap="medium")

with col1:
    with st.container(border=True):
        st.markdown('<div class="win11-section-label">🧾 Order Details</div>', unsafe_allow_html=True)
        po_number = st.text_input("PO Number", value="PO1536")
        input_method = st.radio("Input Method", ["Copy & Paste Text", "Upload PDF Invoice"])

with col2:
    with st.container(border=True):
        st.markdown('<div class="win11-section-label">⚙️ Custom Instructions</div>', unsafe_allow_html=True)
        custom_instructions = st.text_area(
            "Additional rules or overrides",
            placeholder="Add any specific rules, overrides, or notes here...",
            height=132,
            label_visibility="collapsed",
        )

extracted_text = ""

with st.container(border=True):
    if input_method == "Copy & Paste Text":
        st.markdown('<div class="win11-section-label">📋 Paste Order Raw Text</div>', unsafe_allow_html=True)
        extracted_text = st.text_area("Paste Order Raw Text Here", height=200, label_visibility="collapsed")
    else:
        st.markdown('<div class="win11-section-label">📄 Upload Invoice PDF</div>', unsafe_allow_html=True)
        uploaded_pdf = st.file_uploader("Upload Invoice PDF", type=["pdf"], label_visibility="collapsed")
        if uploaded_pdf:
            pdf_reader = pypdf.PdfReader(uploaded_pdf)
            for page in pdf_reader.pages:
                extracted_text += page.extract_text() or ""

st.write("")
process_clicked = st.button("🚀  Process Order & Generate CSV", type="primary")

# ---------------------------------------------------------------------------
# Processing Action
# ---------------------------------------------------------------------------
if process_clicked:
    if not extracted_text.strip():
        st.error("Please provide order information via text or PDF.")
    else:
        with st.spinner("Analyzing order details and mapping NetSuite fields..."):
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

                # Temperature set to 0.1
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.1}
                )

                # Parse JSON
                clean_json_str = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json_str)

                df = pd.DataFrame(data)

                st.success("Successfully processed line items!")

                # Table Preview
                with st.container(border=True):
                    st.markdown('<div class="win11-section-label">📊 Data Preview</div>', unsafe_allow_html=True)
                    st.dataframe(df, use_container_width=True)

                # CSV Download Button
                csv_buffer = io.BytesIO()
                df.to_csv(csv_buffer, index=False)

                st.download_button(
                    label="📥 Download NetSuite CSV",
                    data=csv_buffer.getvalue(),
                    file_name=f"{po_number}_NetSuite_Import.csv",
                    mime="text/csv"
                )

            except Exception as e:
                st.error(f"Error processing order: {str(e)}")
