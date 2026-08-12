import streamlit as st
import pandas as pd
import google.generativeai as genai
from pypdf import PdfReader
import json

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(page_title="NetSuite PO Generator", page_icon="📄", layout="wide")
st.title("NetSuite PO Generator")
st.markdown("Upload a vendor PDF to automatically extract Purchase Order data. Cells with **low AI confidence** will be highlighted for manual review.")

# ==========================================
# API CONFIGURATION
# ==========================================
with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Enter Google Gemini API Key:", type="password")
    if api_key:
        genai.configure(api_key=api_key)

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def extract_text_from_pdf(pdf_file):
    """Extracts text from the uploaded PDF document."""
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def generate_po_data_with_confidence(text):
    """
    Prompts Gemini to extract PO data and assign a confidence score (0.0 to 1.0) 
    to every single field to enable UI highlighting.
    """
    prompt = f"""
    You are a data extraction assistant for NetSuite Purchase Orders.
    Extract the line items from the following Purchase Order / Quote text.
    
    CRITICAL INSTRUCTION:
    Return a JSON array of items. For EVERY field, you must return an object containing 
    both the "value" and your "confidence" score (a float between 0.0 and 1.0) that the data is accurate.
    
    Format exactly like this example:
    [
        {{
            "Item Name": {{"value": "Widget A", "confidence": 0.98}},
            "Item Code": {{"value": "WDG-01", "confidence": 0.65}},
            "Quantity": {{"value": 10, "confidence": 0.99}},
            "Unit Price": {{"value": 15.50, "confidence": 0.90}}
        }}
    ]
    
    Text to process:
    {text}
    """
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    
    try:
        # Clean the response to ensure we just parse the JSON
        raw_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_json)
    except Exception as e:
        st.error(f"Failed to parse AI response. Raw output was: {response.text}")
        return None

def highlight_confidence(val):
    """
    Pandas styler function to apply background colors based on confidence scores.
    🔴 Red: < 85% 
    🟡 Yellow: 85% - 94%
    """
    if isinstance(val, dict) and 'confidence' in val:
        conf = val['confidence']
        if conf < 0.85:
            return 'background-color: #ffcccc; color: #990000;' # Red warning
        elif conf < 0.95:
            return 'background-color: #ffffcc; color: #886600;' # Yellow caution
    return '' # Default styling for high confidence

def format_display_value(val):
    """Extracts just the 'value' for the clean, editable dataframe."""
    if isinstance(val, dict) and 'value' in val:
        return val['value']
    return val

# ==========================================
# MAIN APP UI
# ==========================================
uploaded_file = st.file_uploader("Upload PR/Quote PDF", type=["pdf"])

if uploaded_file is not None:
    if not api_key:
        st.warning("⚠️ Please enter your Google Gemini API key in the sidebar to proceed.")
    else:
        with st.spinner("Reading PDF..."):
            pdf_text = extract_text_from_pdf(uploaded_file)
            
        with st.spinner("AI is extracting PO data and calculating confidence scores..."):
            extracted_data = generate_po_data_with_confidence(pdf_text)
            
        if extracted_data:
            st.success("Extraction Complete!")
            st.divider()
            
            # Convert JSON to DataFrames
            df_raw = pd.DataFrame(extracted_data)
            
            # 1. FORMAT THE VISUAL HIGHLIGHT MAP
            # Apply color styles to the raw dictionary structure
            styled_df = df_raw.style.map(highlight_confidence)
            
            # Clean up what the user actually sees in the cells of the highlighted map (hide the raw JSON)
            styled_df = styled_df.format(lambda x: x['value'] if isinstance(x, dict) and 'value' in x else x)
            
            st.subheader("1. AI Confidence Review")
            st.markdown("Use this map to spot potential AI hallucinations. 🔴 **< 85%** | 🟡 **85-94%** | 🟢 **>= 95%**")
            st.dataframe(styled_df, use_container_width=True)
            
            # 2. CREATE THE EDITABLE GRID
            # Strip out the dictionaries so the data editor works natively with strings/numbers
            df_editable = df_raw.map(format_display_value)
            
            st.subheader("2. Human-in-the-Loop Corrections")
            st.info("Make your manual corrections below. You can edit cells, add rows, or delete rows.")
            final_df = st.data_editor(df_editable, num_rows="dynamic", use_container_width=True)
            
            # 3. EXPORT TO NETSUITE
            st.divider()
            st.subheader("3. Export")
            csv = final_df.to_csv(index=False)
            
            st.download_button(
                label="📥 Download NetSuite Import CSV",
                data=csv,
                file_name="netsuite_po_import.csv",
                mime="text/csv",
                type="primary"
            )
