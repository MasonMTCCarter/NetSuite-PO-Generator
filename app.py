import streamlit as st
import pandas as pd
import google.generativeai as genai
import json
import io
import os
import base64
import requests
from datetime import datetime

# ---------------------------------------------------------------------------
# App Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NetSuite PO Import Generator",
    layout="centered",
    page_icon="📋",
)

# Explicitly locate script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_FILE = os.path.join(SCRIPT_DIR, "pr_mappings.json")

DEFAULT_MAPPINGS = {
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
    "670-2": {
        "Customer/Project": "Lockheed Martin : 670 AFSOC",
        "Custom WBS Task": "Materials (670-2)",
    },
    "670-3": {
        "Customer/Project": "Lockheed Martin : 670 AFSOC",
        "Custom WBS Task": "Materials (670-3)",
    },
    "611-2": {
        "Customer/Project": "Fluor Marine Propulsion, LLC : 611 I&C",
        "Custom WBS Task": "611-2 Materials",
    },
    "611-5": {
        "Customer/Project": "Fluor Marine Propulsion, LLC : 611 I&C",
        "Custom WBS Task": "611-5 Materials",
    },
    "1000": {
        "Customer/Project": "FLETC : Diversified Fabricators & Erectors : 1000 SAACSIM",
        "Custom WBS Task": "SAACSIM #1-2 Materials",
    },
    "1001": {
        "Customer/Project": "ADS, Inc : 1001 - M1A2 HOT SEPv3",
        "Custom WBS Task": "0014.30.03.80 - Material",
    },
    "1002": {
        "Customer/Project": "Akima/Pinnacle Solutions : 1002 - ACV MTS Production",
        "Custom WBS Task": "1002.0001.30.03.80 - Material",
    },
    "Abrams Hot List": {
        "Customer/Project": "ADS, Inc : 1001 - M1A2 HOT SEPv3",
        "Custom WBS Task": "0014.30.03.80 - Material",
    },
    "505": {
        "Customer/Project": "Lockheed Martin : 505 FuT 5",
        "Custom WBS Task": "Materials",
    },
    "506": {
        "Customer/Project": "Lockheed Martin : 506 FuT 6",
        "Custom WBS Task": "506 Materials",
    },
    "550": {
        "Customer/Project": "CymSTAR, LLC : 550 C5 FuT",
        "Custom WBS Task": "Materials",
    },
    "627": {
        "Customer/Project": "CUBIC : 627 Mortar Production",
        "Custom WBS Task": "Materials",
    },
    "724": {
        "Customer/Project": "Lockheed Martin : 724 -Faceplate Assembly - 543013-103",
        "Custom WBS Task": "Materials",
    },
    "725": {
        "Customer/Project": "Leidos : 725",
        "Custom WBS Task": "Materials",
    },
    "777": {
        "Customer/Project": "Newton Design, LLC : 777 Overhead",
        "Custom WBS Task": "777 Materials",
    },
}

# ---------------------------------------------------------------------------
# Mapping Persistence Functions (Local + GitHub API)
# ---------------------------------------------------------------------------
def load_pr_mappings() -> dict:
    """Loads mappings from local pr_mappings.json or falls back to DEFAULT_MAPPINGS."""
    if os.path.exists(MAPPINGS_FILE):
        try:
            with open(MAPPINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and len(data) > 0:
                    return data
        except Exception:
            return DEFAULT_MAPPINGS.copy()
    return DEFAULT_MAPPINGS.copy()

def save_pr_mappings(mappings: dict) -> bool:
    """
    Saves mappings directly to GitHub repository via GitHub API if secrets are present.
    Also syncs to local pr_mappings.json on disk.
    """
    # 1. Always write locally if possible
    try:
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass

    # 2. Check for GitHub configuration in Streamlit Secrets
    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    file_path = "pr_mappings.json"

    if not token or not repo:
        # If GitHub secrets are not provided, local save is sufficient
        return True

    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        # Step A: Get current file SHA hash (required by GitHub API to update an existing file)
        sha = None
        get_res = requests.get(url, headers=headers, params={"ref": branch})
        if get_res.status_code == 200:
            sha = get_res.json().get("sha")

        # Step B: Encode JSON content to Base64
        content_str = json.dumps(mappings, indent=4)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "Update pr_mappings.json via NetSuite App UI",
            "content": content_b64,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        # Step C: Commit the updated file directly to GitHub
        put_res = requests.put(url, headers=headers, json=payload)
        if put_res.status_code in [200, 201]:
            return True
        else:
            error_details = put_res.json().get("message", "Unknown error")
            st.error(f"GitHub API Error ({put_res.status_code}): {error_details}")
            return False

    except Exception as e:
        st.error(f"Failed to commit changes to GitHub: {e}")
        return False

# Initialize Session States
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None
if "shipping_cost" not in st.session_state:
    st.session_state.shipping_cost = None
if "pr_mappings" not in st.session_state:
    st.session_state.pr_mappings = load_pr_mappings()
if "mapping_version" not in st.session_state:
    st.session_state.mapping_version = 0
if "audit_history" not in st.session_state:
    st.session_state.audit_history = []

# Helper: Load Logo as Base64
LOGO_PATH = os.path.join(SCRIPT_DIR, "logo.png")

def get_base64_image(image_path: str) -> str:
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            encoded = base64.b64encode(img_file.read()).decode()
            return f"data:image/png;base64,{encoded}"
    return ""

logo_base64 = get_base64_image(LOGO_PATH)

# ---------------------------------------------------------------------------
# PR Mapping Rules & Substring Priority Matching
# ---------------------------------------------------------------------------
def apply_pr_mappings(df: pd.DataFrame, mappings: dict = None) -> pd.DataFrame:
    """Enforces WBS and Customer/Project mappings using Substring Matching Priority (longest match first)."""
    if df is None or df.empty or "PR #" not in df.columns:
        return df

    if mappings is None:
        mappings = st.session_state.get("pr_mappings", DEFAULT_MAPPINGS)

    sorted_keys = sorted(mappings.keys(), key=len, reverse=True)

    for idx, row in df.iterrows():
        pr_val = str(row.get("PR #", "")).lower()
        for key in sorted_keys:
            if key.lower() in pr_val:
                df.at[idx, "Customer/Project"] = mappings[key]["Customer/Project"]
                df.at[idx, "Custom WBS Task"] = mappings[key]["Custom WBS Task"]
                break
    return df

def generate_mapping_prompt_rules(mappings: dict) -> str:
    """Generates the prompt instructions dynamically based on active mappings."""
    rules = ["Mappings for PR #:"]
    for key, mapping in mappings.items():
        rules.append(f'  * {key} -> Customer/Project: "{mapping["Customer/Project"]}", Custom WBS Task: "{mapping["Custom WBS Task"]}"')
    rules.append("- Ensure Manufacturer Part Number is used (NOT vendor part numbers).")
    rules.append("- Exclude 'Form' and 'Vendor' columns.")
    return "\n".join(rules)

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Prevents CSV formula injection by prepending a space to problematic text."""
    if df is None or df.empty:
        return df
        
    def sanitize_cell(val):
        if isinstance(val, str):
            cleaned_val = val.lstrip()
            if cleaned_val.startswith(("=", "+", "-", "@")):
                return f" {cleaned_val}"
        return val

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

        .stTextInput input, .stTextArea textarea {
            font-size: 16px !important;
            padding: 10px !important;
            border: 1px solid var(--win-border) !important;
        }

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
            <p>Convert orders, spreadsheets, or invoices into NetSuite CSV format</p>
        </div>
        {logo_html}
    </div>
    """,
    unsafe_allow_html=True,
)

st.info("""
👉 **How to use:**
1. Type in your **PO Number** below.
2. Upload a **Document (PDF, Image, Excel, CSV)** or paste order text.
3. Click the big blue **"Process Order & Generate CSV"** button.
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
# Dynamic Mapping Database Manager
# ---------------------------------------------------------------------------
with st.expander("🛠️ Manage Customer/Project & WBS Task Mappings"):
    st.markdown("Add, remove, or edit keyword mappings below. Changes will sync to `pr_mappings.json` (and GitHub repository if configured).")
    
    current_map_data = [
        {"PR Keyword": k, "Customer/Project": v.get("Customer/Project", ""), "Custom WBS Task": v.get("Custom WBS Task", "")}
        for k, v in st.session_state.pr_mappings.items()
    ]
    mappings_df = pd.DataFrame(current_map_data)
    
    edited_mappings_df = st.data_editor(
        mappings_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"mappings_editor_{st.session_state.mapping_version}"
    )
    
    if st.button("💾 Save Changes to Mapping Rules", type="primary", use_container_width=True):
        new_mappings = {}
        for _, row in edited_mappings_df.iterrows():
            kw_raw = row.get("PR Keyword")
            cp_raw = row.get("Customer/Project")
            wbs_raw = row.get("Custom WBS Task")
            
            if pd.notna(kw_raw) and pd.notna(cp_raw) and pd.notna(wbs_raw):
                kw = str(kw_raw).strip()
                cp = str(cp_raw).strip()
                wbs = str(wbs_raw).strip()
                
                if kw and cp and wbs and kw.lower() != "nan":
                    new_mappings[kw] = {"Customer/Project": cp, "Custom WBS Task": wbs}
        
        if new_mappings:
            st.session_state.pr_mappings = new_mappings
            success = save_pr_mappings(new_mappings)
            if success:
                st.session_state.mapping_version += 1
                st.success("✅ Mappings updated and synced!")
                st.rerun()
        else:
            st.error("⚠️ No valid mapping rows detected to save.")

# ---------------------------------------------------------------------------
# UI Inputs
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.markdown('<div class="win11-section-label">1️⃣ Step 1: Enter PO Number</div>', unsafe_allow_html=True)
    po_number = st.text_input("PO Number", placeholder="Example: PO1536", help="Enter the Purchase Order number for this import.")

uploaded_file_obj = None
text_input = ""

with st.container(border=True):
    st.markdown('<div class="win11-section-label">2️⃣ Step 2: Provide Order Info</div>', unsafe_allow_html=True)
    
    input_type = st.radio(
        "Choose how you want to provide order details:",
        ["📁 Upload File (PDF, Image, Excel, CSV)", "📋 Copy & Paste Order Text"],
        horizontal=True
    )
    
    if input_type == "📁 Upload File (PDF, Image, Excel, CSV)":
        uploaded_file_obj = st.file_uploader(
            "Upload file", 
            type=["pdf", "png", "jpg", "jpeg", "xlsx", "xls", "csv"],
            help="Supports PDF invoices, screenshots/images, and quote spreadsheets."
        )
    else:
        text_input = st.text_area("Paste order details here:", height=180, placeholder="Paste raw order text or copy-pasted invoice content here...")

with st.expander("⚙️ Special Instructions / Overrides (Optional)"):
    st.markdown("💡 *Note: Updating the PR # column will automatically recalculate Customer/Project and WBS Task.*")
    st.write("")
    
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
    st.session_state.shipping_cost = None
    
    if not po_number.strip():
        st.warning("⚠️ Please fill in the PO Number before continuing.")
    elif input_type == "📁 Upload File (PDF, Image, Excel, CSV)" and not uploaded_file_obj:
        st.warning("⚠️ Please upload a file in Step 2.")
    elif input_type == "📋 Copy & Paste Order Text" and not text_input.strip():
        st.warning("⚠️ Please paste the order text in Step 2.")
    else:
        instructions_list = [
            "Exclude any freight, shipping, tax, handling, or non-item charge lines from the line items list."
        ]
        if custom_instructions_input.strip():
            instructions_list.append(custom_instructions_input.strip())

        full_custom_instructions = "\n".join(f"- {inst}" for inst in instructions_list)
        mapping_rules_text = generate_mapping_prompt_rules(st.session_state.pr_mappings)

        with st.spinner("⏳ Analyzing order details... This usually takes about 30 seconds to 2 minutes."):
            try:
                prompt = f"""
                You are a data extraction assistant for NetSuite imports.
                Extract line items and shipping cost from the provided document/text and output structured data.

                Context & Rules:
                - PO Number to use for all items: {po_number}
                - Custom Instructions:
                {full_custom_instructions}
                {mapping_rules_text}

                CRITICAL EXTRACTION RULES:
                1. TABLE EXCLUSIONS: Always exclude tax, freight, shipping, and handling charge lines from the line items array.
                2. SHIPPING EXTRACTION: Extract the separate shipping/freight cost amount (if present) as a float into "shipping_cost". If no shipping cost is present, set "shipping_cost" to null.
                3. PR # VERBATIM PRESERVATION (DO NOT STRIP OR SHORTEN):
                   - Extract and retain the FULL, EXACT string present in the PR / Job / Order reference line word-for-word.
                   - DO NOT strip out, trim, abbreviate, or discard any text from the "PR #" field. Preserve all job names, room descriptions, notes, numbers, person names, and prefixes/suffixes.
                   - Never reduce the "PR #" field to just a standalone project number unless that exact number was the only text present.
                4. ORDER OF OPERATIONS FOR LINE ITEMS:
                   a. Extract line items and preserve the complete raw "PR #" string verbatim from the source document.
                   b. If a replacement is explicitly instructed in "Custom Instructions", apply that replacement within the PR # text while keeping the surrounding text intact.
                   c. Determine "Customer/Project" and "Custom WBS Task" by checking if any mapped key is contained inside the PR # string.
                5. VERBATIM EXTRACTION RULES:
                   a. "PR #": Preserve 100% of the input text verbatim without shortening or omitting anything.
                   b. "Item Description": Copy description EXACTLY word-for-word with original casing and punctuation.
                   c. MATH EVALUATION RULE: If any field contains a mathematical formula or expression starting with '=' or containing math (e.g., `=10+20`), evaluate the expression and output the final calculated numerical value instead of the formula string.
                """

                extraction_schema = {
                    "type": "OBJECT",
                    "properties": {
                        "shipping_cost": {"type": "NUMBER", "nullable": True},
                        "items": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "Line Item": {"type": "INTEGER"},
                                    "Customer/Project": {"type": "STRING"},
                                    "Custom WBS Task": {"type": "STRING"},
                                    "PO": {"type": "STRING"},
                                    "PR #": {"type": "STRING"},
                                    "Manufacturer Part Number": {"type": "STRING"},
                                    "Item Description": {"type": "STRING"},
                                    "Qty": {"type": "NUMBER"},
                                    "Cost Price": {"type": "NUMBER"},
                                    "Amount": {"type": "NUMBER"},
                                },
                                "required": ["Line Item", "PO", "PR #", "Manufacturer Part Number", "Item Description", "Qty", "Cost Price", "Amount"],
                            }
                        }
                    },
                    "required": ["items"]
                }

                content_payload = []
                file_source_name = "Pasted Text"
                
                if input_type == "📁 Upload File (PDF, Image, Excel, CSV)" and uploaded_file_obj:
                    file_source_name = uploaded_file_obj.name
                    file_ext = os.path.splitext(uploaded_file_obj.name)[1].lower()
                    file_bytes = uploaded_file_obj.getvalue()

                    if file_ext == ".pdf":
                        content_payload = [prompt, {"mime_type": "application/pdf", "data": file_bytes}]
                    elif file_ext in [".png", ".jpg", ".jpeg"]:
                        mime = "image/png" if file_ext == ".png" else "image/jpeg"
                        content_payload = [prompt, {"mime_type": mime, "data": file_bytes}]
                    elif file_ext == ".csv":
                        csv_df = pd.read_csv(io.BytesIO(file_bytes))
                        content_payload = [f"{prompt}\n\nDocument Content (CSV Table):\n{csv_df.to_csv(index=False)}"]
                    elif file_ext in [".xlsx", ".xls"]:
                        xls = pd.ExcelFile(io.BytesIO(file_bytes))
                        sheets_text = []
                        for s_name in xls.sheet_names:
                            s_df = pd.read_excel(xls, sheet_name=s_name)
                            sheets_text.append(f"--- Sheet: {s_name} ---\n{s_df.to_csv(index=False)}")
                        content_payload = [f"{prompt}\n\nDocument Content (Spreadsheet):\n" + "\n\n".join(sheets_text)]
                else:
                    content_payload = [f"{prompt}\n\nOrder Info:\n{text_input}"]

                models_to_try = [
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gemini-3.5-flash-lite"
                ]
                
                response = None
                
                for attempt, model_name in enumerate(models_to_try):
                    try:
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(
                            content_payload, 
                            generation_config={
                                "temperature": 0.1,
                                "response_mime_type": "application/json",
                                "response_schema": extraction_schema
                            }
                        )
                        break
                    except Exception as api_error:
                        error_msg = str(api_error).lower()
                        if any(keyword in error_msg for keyword in ["429", "quota", "rate limit", "resourceexhausted"]):
                            if attempt < len(models_to_try) - 1:
                                continue
                            else:
                                raise Exception("Rate limits exhausted across all fallback models.")
                        else:
                            raise api_error

                parsed_data = json.loads(response.text)
                items_data = parsed_data.get("items", [])
                extracted_shipping = parsed_data.get("shipping_cost", None)

                df = pd.DataFrame(items_data)
                df = apply_pr_mappings(df, st.session_state.pr_mappings)
                df = sanitize_dataframe(df)

                st.session_state.processed_df = df
                st.session_state.shipping_cost = extracted_shipping

                try:
                    total_order_val = (df["Qty"].astype(float) * df["Cost Price"].astype(float)).sum()
                except Exception:
                    total_order_val = 0.0

                audit_entry = {
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "PO Number": po_number,
                    "Source": file_source_name,
                    "Line Items": len(df),
                    "Order Total ($)": round(float(total_order_val), 2),
                    "Shipping ($)": round(float(extracted_shipping), 2) if extracted_shipping is not None else 0.0,
                    "Model Used": model_name
                }
                st.session_state.audit_history.insert(0, audit_entry)

                st.success("✅ Order successfully processed!")
                
                if attempt > 0:
                    st.warning(f"⚠️ **Notice:** A backup AI model ({model_name}) was used. Please review results carefully.")

            except json.JSONDecodeError:
                st.error("⚠️ The system had trouble formatting the output. Please click 'Process Order' once more.")
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["rate limits exhausted", "429", "quota", "rate limit"]):
                    st.error("⏳ Server busy. Please wait 1 minute and try again.")
                else:
                    st.error(f"⚠️ Error: {str(e)}")

# ---------------------------------------------------------------------------
# Results Display (Editable & Stateful)
# ---------------------------------------------------------------------------
if st.session_state.processed_df is not None:
    st.markdown("---")
    st.subheader("3️⃣ Step 3: Review & Download")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Line Items", value=len(st.session_state.processed_df))
    with col2:
        try:
            total_val = (st.session_state.processed_df["Qty"].astype(float) * st.session_state.processed_df["Cost Price"].astype(float)).sum()
            st.metric(label="Total Order Value", value=f"${total_val:,.2f}")
        except Exception:
            st.metric(label="Total Order Value", value="N/A")
    with col3:
        shipping_val = st.session_state.get("shipping_cost")
        if shipping_val is not None:
            try:
                st.metric(label="Shipping Cost", value=f"${float(shipping_val):,.2f}")
            except (ValueError, TypeError):
                st.metric(label="Shipping Cost", value=str(shipping_val))
        else:
            st.metric(label="Shipping Cost", value="None detected")

    if "PR #" in st.session_state.processed_df.columns:
        mapping_keys = list(st.session_state.pr_mappings.keys())
        if mapping_keys:
            unmapped_rows = st.session_state.processed_df[
                ~st.session_state.processed_df["PR #"].astype(str).str.contains("|".join(mapping_keys), case=False, na=False)
            ]
            if not unmapped_rows.empty:
                st.warning("⚠️ Some PR numbers were not recognized in your mapping database. Please review the Customer/Project and WBS Task for those rows.")

    with st.container(border=True):
        st.markdown("💡 **Tip:** You can double-click any cell below to edit values before downloading.")
        
        edited_df = st.data_editor(
            st.session_state.processed_df, 
            use_container_width=True, 
            num_rows="dynamic",
            hide_index=True
        )

    final_export_df = apply_pr_mappings(edited_df, st.session_state.pr_mappings)
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
            st.session_state.shipping_cost = None
            st.rerun()

# ---------------------------------------------------------------------------
# Session Audit Log & History
# ---------------------------------------------------------------------------
if st.session_state.audit_history:
    with st.expander("📜 Session Audit Log & History"):
        st.markdown("Overview of all orders processed during this session:")
        history_df = pd.DataFrame(st.session_state.audit_history)
        st.dataframe(history_df, use_container_width=True, hide_index=True)
        
        hist_buffer = io.BytesIO()
        history_df.to_csv(hist_buffer, index=False)
        
        col_hist_dl, col_hist_clear = st.columns([2, 1])
        with col_hist_dl:
            st.download_button(
                label="📥 Download Audit Log (CSV)",
                data=hist_buffer.getvalue(),
                file_name=f"Audit_Log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with col_hist_clear:
            if st.button("🗑️ Clear Audit Log", use_container_width=True):
                st.session_state.audit_history = []
                st.rerun()
