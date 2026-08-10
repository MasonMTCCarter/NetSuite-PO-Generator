import streamlit as st
import pandas as pd
import google.generativeai as genai
import pypdf
import json
import io

# App Configuration
st.set_page_config(page_title="NetSuite PO Import Generator", layout="wide")
st.title("📦 NetSuite PO & Item Import Generator")

# Initialize Gemini API
api_key = st.secrets.get("GEMINI_API_KEY") or st.sidebar.text_input("Gemini API Key", type="password")

if not api_key:
    st.warning("Please provide a Gemini API Key in Streamlit Secrets or the sidebar to continue.")
    st.stop()

genai.configure(api_key=api_key)

# System Prompt Template
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

# UI Inputs
col1, col2 = st.columns(2)

with col1:
    po_number = st.text_input("PO Number", value="PO1536")
    input_method = st.radio("Input Method", ["Copy & Paste Text", "Upload PDF Invoice"])

with col2:
    custom_instructions = st.text_area("Custom Instructions", placeholder="Add any specific rules, overrides, or notes here...")

extracted_text = ""

if input_method == "Copy & Paste Text":
    extracted_text = st.text_area("Paste Order Raw Text Here", height=200)
else:
    uploaded_pdf = st.file_uploader("Upload Invoice PDF", type=["pdf"])
    if uploaded_pdf:
        pdf_reader = pypdf.PdfReader(uploaded_pdf)
        for page in pdf_reader.pages:
            extracted_text += page.extract_text() or ""

# Processing Action
if st.button("🚀 Process Order & Generate CSV", type="primary"):
    if not extracted_text.strip():
        st.error("Please provide order information via text or PDF.")
    else:
        with st.spinner("Analyzing order details and mapping NetSuite fields..."):
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                prompt = f"""
                You are a data extraction assistant for NetSuite imports.
                Extract line items from the following raw text and output a JSON array of objects.

                Order Info:
                {extracted_text}

                Context & Rules:
                - PO Number to use for all items: {po_number}
                - Custom Instructions: {custom_instructions}
                {MAPPING_RULES}

                Return ONLY a raw JSON array where each item has keys:
                "Line Item" (integer starting at 1),
                "Customer/Project" (string based on mapping),
                "Custom WBS Task" (string based on mapping),
                "PO" (string, e.g., "{po_number}"),
                "PR #" (string reference like 'Job 648-2...'),
                "Manufacturer Part Number" (string),
                "Item Description" (string),
                "Qty" (integer),
                "Cost Price" (float),
                "Amount" (float)
                """

                response = model.generate_content(prompt)
                
                # Parse JSON
                clean_json_str = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json_str)
                
                df = pd.DataFrame(data)

                st.success("Successfully processed line items!")
                
                # Table Preview
                st.subheader("Data Preview")
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
