import streamlit as st
import pandas as pd
import google.generativeai as genai
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
# PR Mapping Rules Table & Python Enforcer
# ---------------------------------------------------------------------------
PR_MAPPINGS = {
    "648-1": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-1 Materials",
    },
    "648-2": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-2 Materials",
    },
    "648-3": {
        "Customer/Project": "JF Taylor : 648 USAF FA FuTs",
        "Custom WBS Task": "648-3 Materials",
    },
    "777": {
        "Customer/Project": "Newton Design, LLC : 777 Overhead",
        "Custom WBS Task": "777 Materials",
    },
    "505": {
        "Customer/Project": "Lockheed Martin : 505 FuT 5",
        "Custom WBS Task": "Materials",
    },
    "506": {
        "Customer/Project": "Lockheed Martin : 506 FuT 6",
        "Custom WBS Task": "506 Materials",
    },
}

def apply_pr_mappings(df: pd.DataFrame) -> pd.DataFrame:
    """Enforces WBS and Customer/Project mappings based on the final PR # value."""
    if df is None or df.empty or "PR #" not in df.columns:
        return df

    for idx, row in df.iterrows():
        pr_val = str(row.get("PR #", ""))
        for key, mapping in PR_MAPPINGS.items():
            if key in pr_val:
                df.at[idx, "Customer/Project"] = mapping["Customer/Project"]
                df.at[idx, "Custom WBS Task"] = mapping["Custom WBS Task"]
                break
    return df

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Prevents CSV formula injection by prepending a space to problematic text."""
    if df is None or df.empty:
        return df
        
    def sanitize_cell(val):
        # Only modify strings; ignore integers or floats (like Cost Price)
        if isinstance(val, str):
            cleaned_val = val.lstrip()
            # If the string starts with a formula trigger, prepend a space
            if cleaned_val.startswith(("=", "+", "-", "@")):
                return f" {cleaned_val}"
        return val

    # Apply element-wise across the entire DataFrame safely
    if hasattr(df, 'map'):
        return df.map(sanitize_cell)
    else:
        return df.applymap(sanitize_cell)

# ---------------------------------------------------------------------------
# High-Accessibility Fluent CSS
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

        /* Large Action Button */
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
# Secure API Key Check
# ---------------------------------------------------------------------------
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ System Configuration Missing: API Key was not found in Streamlit Secrets.")
    st.stop()

genai.configure(api_key=api_key)

# ---------------------------------------------------------------------------
# Mapping Rules Text
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
"""

# ---------------------------------------------------------------------------
# UI Inputs
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<div class="win11-section-label">1️⃣ Step 1: Enter PO Number</div>', unsafe_allow_html=True)
    po_number = st.text_input("PO Number", placeholder="Example: PO1536", help="Enter the Purchase Order number for this import.")

uploaded_pdf_bytes = None
text_input = ""

with st.container(border=True):
    st.markdown('<div class="win11-section-label">2️⃣ Step 2: Provide Order Info</div>', unsafe_allow_html=True)
    
    input_type = st.radio(
        "Choose how you want to provide order details:",
        ["📄 Upload PDF Invoice", "📋 Copy & Paste Order Text"],
        horizontal=True
    )
    
    if input_type == "📄 Upload PDF Invoice":
        uploaded_pdf = st.file_uploader("Upload PDF file", type=["pdf"])
        if uploaded_pdf:
            uploaded_pdf_bytes = uploaded_pdf.getvalue()
    else:
        text_input = st.text_area("Paste order details here:", height=180, placeholder="Paste raw order text or copy-pasted invoice content here...")

with st.expander("⚙️ Special Instructions / Overrides (Optional)"):
    st.markdown("💡 *Note: Updating the PR # column will automatically recalculate Customer/Project and WBS Task.*")
    st.write("")
    
    preset_exclude_tax = st.checkbox("Exclude tax, freight, and shipping line items")
    
    custom_instructions_input = st.text_area(
        "Additional rules or notes for this order:",
        placeholder="e.g. Convert all instances of 777 to 648-2 in PR #",
        height=80,
    )

st.write("")
process_clicked = st.button("🚀 Process Order & Generate CSV", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Processing Action
# ---------------------------------------------------------------------------
if process_clicked:
    st.session_state.processed_df = None
    
    if not po_number.strip():
        st.warning("⚠️ Please fill in the PO Number before continuing.")
    elif input_type == "📄 Upload PDF Invoice" and not uploaded_pdf_bytes:
        st.warning("⚠️ Please upload a PDF file in Step 2.")
    elif input_type == "📋 Copy & Paste Order Text" and not text_input.strip():
        st.warning("⚠️ Please paste the order text in Step 2.")
    else:
        # Build composite custom instructions from presets + text area
        instructions_list = []
        if preset_exclude_tax:
            instructions_list.append("Exclude any freight, shipping, tax, or non-item charge lines.")
        if custom_instructions_input.strip():
            instructions_list.append(custom_instructions_input.strip())

        full_custom_instructions = "\n".join(f"- {inst}" for inst in instructions_list) if instructions_list else "None"

        with st.spinner("⏳ Analyzing order details... This usually takes about 30 seconds to 2 minutes."):
            try:
                prompt = f"""
                You are a data extraction assistant for NetSuite imports.
                Extract line items from the provided document/text and output a JSON array of objects.

                Context & Rules:
                - PO Number to use for all items: {po_number}
                - Custom Instructions:
                {full_custom_instructions}
                {MAPPING_RULES}

                CRITICAL ORDER OF OPERATIONS:
                1. Extract line items and raw "PR #" from the source document.
                2. STEP FIRST: Apply any overrides or replacements from "Custom Instructions" to the "PR #" field FIRST (e.g., if instructed to change 777 to 648-2, update the "PR #" field to 648-2).
                3. STEP LAST: Determine "Customer/Project" and "Custom WBS Task" based strictly on the FINAL updated "PR #" value from Step 2 (e.g., if PR # was changed to 648-2, use the 648-2 customer/project and WBS task mappings).

                CRITICAL VERBATIM EXTRACTION RULES:
                1. "PR #": Copy/modify the PR # string according to custom rules, without truncation.
                2. "Item Description": Copy description EXACTLY word-for-word with original casing and punctuation.

                Return ONLY a raw JSON array where each item has keys:
                "Line Item" (integer starting at 1),
                "Customer/Project" (string based on mapping of FINAL PR #),
                "Custom WBS Task" (string based on mapping of FINAL PR #),
                "PO" (string, e.g., "{po_number}"),
                "PR #" (string),
                "Manufacturer Part Number" (string),
                "Item Description" (string),
                "Qty" (integer),
                "Cost Price" (float),
                "Amount" (float)
                """

                # Define the sequence of models to try
                models_to_try = [
                    "gemini-3.6-flash",      # Primary
                    "gemini-3.5-flash",      # Fallback 1
                    "gemini-3.5-flash-lite"  # Fallback 2
                ]
                
                response = None
                
                for attempt, model_name in enumerate(models_to_try):
                    try:
                        model = genai.GenerativeModel(model_name)

                        # Pass either raw PDF bytes or pasted text into Gemini
                        if input_type == "📄 Upload PDF Invoice" and uploaded_pdf_bytes:
                            pdf_part = {"mime_type": "application/pdf", "data": uploaded_pdf_bytes}
                            response = model.generate_content([prompt, pdf_part], generation_config={"temperature": 0.1})
                        else:
                            response = model.generate_content(f"{prompt}\n\nOrder Info:\n{text_input}", generation_config={"temperature": 0.1})
                        
                        # Break out of the retry loop if the generation succeeds
                        break 
                        
                    except Exception as api_error:
                        error_msg = str(api_error).lower()
                        # Check for rate limit or quota errors
                        if any(keyword in error_msg for keyword in ["429", "quota", "rate limit", "resourceexhausted"]):
                            if attempt < len(models_to_try) - 1:
                                continue # Silently move to the next model in the sequence
                            else:
                                raise Exception("Rate limits exhausted across all fallback models.")
                        else:
                            # If it's a different error type (e.g., bad request), raise immediately
                            raise api_error

                # Updated parsing logic starts here
                raw_text = response.text
                start_idx = raw_text.find('[')
                end_idx = raw_text.rfind(']')

                if start_idx != -1 and end_idx != -1:
                    clean_json_str = raw_text[start_idx:end_idx + 1]
                    data = json.loads(clean_json_str)
                else:
                    # Force the error if no array is found at all
                    raise json.JSONDecodeError("No JSON array found in response", raw_text, 0)

                # Step 1: Parse DataFrame
                df = pd.DataFrame(data)

                # Step 2: Post-process mapping in Python to guarantee 100% compliance with final PR #
                df = apply_pr_mappings(df)

                # Step 3: Sanitize to prevent CSV formula injection
                df = sanitize_dataframe(df)

                # Save successfully processed data to session state
                st.session_state.processed_df = df
                st.success("✅ Order successfully processed!")
                
                # Check if a fallback model was used and warn the user
                if attempt > 0:
                    st.warning(f"⚠️ **Notice:** Due to high server demand, a backup AI model ({model_name}) was used to process this order. The extracted data may be slightly less accurate than usual, so please review the results carefully.")

            except json.JSONDecodeError:
                st.error("⚠️ The system had trouble reading the format. Please try clicking 'Process Order' once more.")
            except Exception as e:
                error_msg = str(e).lower()
                if "rate limits exhausted" in error_msg or "429" in error_msg or "quota" in error_msg or "rate limit" in error_msg:
                    st.error("⏳ All fallback servers are busy. Please wait 1 minute and click the button again.")
                else:
                    st.error("⚠️ Something unexpected happened. Please verify your order text or PDF and try again.")

# ---------------------------------------------------------------------------
# Results Display (Editable & Stateful)
# ---------------------------------------------------------------------------
if st.session_state.processed_df is not None:
    st.markdown("---")
    st.subheader("3️⃣ Step 3: Review & Download")

    # Metrics Summary Bar
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Total Line Items", value=len(st.session_state.processed_df))
    with col2:
        try:
            total_val = (st.session_state.processed_df["Qty"].astype(float) * st.session_state.processed_df["Cost Price"].astype(float)).sum()
            st.metric(label="Total Calculated Order Value", value=f"${total_val:,.2f}")
        except Exception:
            st.metric(label="Total Calculated Order Value", value="N/A")

    # Check for unmapped PR numbers (Safely)
    if "PR #" in st.session_state.processed_df.columns:
        unmapped_rows = st.session_state.processed_df[
            ~st.session_state.processed_df["PR #"].astype(str).str.contains("|".join(PR_MAPPINGS.keys()), na=False)
        ]
        if not unmapped_rows.empty:
            st.warning("⚠️ Some PR numbers were not recognized in our standard database. Please review the Customer/Project and WBS Task for those rows.")
    else:
        st.error("⚠️ The 'PR #' column is missing from the extracted data. This is likely due to a custom instruction overriding the standard format.")

    with st.container(border=True):
        st.markdown("💡 **Tip:** You can double-click any cell below to edit values before downloading.")
        
        edited_df = st.data_editor(
            st.session_state.processed_df, 
            use_container_width=True, 
            num_rows="dynamic",
            hide_index=True
        )

    # Re-apply mapping dynamically in case the user edited PR # in the data editor directly
    # and re-sanitize before the final export just in case the user manually typed a formula
    final_export_df = apply_pr_mappings(edited_df)
    final_export_df = sanitize_dataframe(final_export_df)

    csv_buffer = io.BytesIO()
    final_export_df.to_csv(csv_buffer, index=False)

    col_dl, col_reset = st.columns([2, 1])
    with col_dl:
        st.download_button(
            label="📥 Download NetSuite CSV File",
            data=csv_buffer.getvalue(),
            file_name=f"{po_number}_NetSuite_Import.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_reset:
        if st.button("🔄 Start Next Order", use_container_width=True):
            st.session_state.processed_df = None
            st.rerun()
