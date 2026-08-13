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
    try:
        with open(MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass

    token = st.secrets.get("GITHUB_TOKEN")
    repo = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    file_path = "pr_mappings.json"

    if not token or not repo:
        return True

    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        sha = None
        get_res = requests.get(url, headers=headers, params={"ref": branch})
        if get_res.status_code == 200:
            sha = get_res.json().get("sha")

        content_str = json.dumps(mappings, indent=4)
        content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")

        payload = {
            "message": "Update pr_mappings.json via NetSuite App UI",
            "content": content_b64,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

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
if "raw_ai_output" not in st.session_state:
    st.session_state.raw_ai_output = None

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
# PR Mapping Rules & Combo PR Split Enforcer
# ---------------------------------------------------------------------------
def split_combo_pr_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    If the PR contains '670-2/3', splits the line item into two separate rows:
    e.g., Line 1 becomes 1A (670-2) and 1B (670-3), with Qty and Amount divided equally.
    """
    if df is None or df.empty:
        return df

    combo_patterns = ["670-2/3", "670-2 / 3", "670-2/ 3", "670-2 /3", "670-2 / 670-3", "670-2/670-3"]
    new_rows = []

    for orig_idx, row in df.iterrows():
        pr_str = str(row.get("PR #", ""))
        matched_pattern = None
        for pattern in combo_patterns:
            if pattern in pr_str:
                matched_pattern = pattern
                break

        if matched_pattern:
            try:
                qty_val = float(row.get("Qty", 1))
            except (ValueError, TypeError):
                qty_val = 1.0

            try:
                cost_val = float(row.get("Cost Price", 0.0))
            except (ValueError, TypeError):
                cost_val = 0.0

            split_qty = qty_val / 2.0
            if split_qty.is_integer():
                split_qty = int(split_qty)

            split_amount = round(float(split_qty) * cost_val, 2)

            line_base = str(row.get("Line Item", orig_idx + 1))
            clean_digits = "".join(c for c in line_base if c.isdigit())
            base_number = clean_digits if clean_digits else str(orig_idx + 1)

            # Row A: 670-2
            row_a = row.copy()
            row_a["Line Item"] = f"{base_number}A"
            row_a["PR #"] = pr_str.replace(matched_pattern, "670-2")
            row_a["Qty"] = split_qty
            row_a["Amount"] = split_amount
            new_rows.append(row_a)

            # Row B: 670-3
            row_b = row.copy()
            row_b["Line Item"] = f"{base_number}B"
            row_b["PR #"] = pr_str.replace(matched_pattern, "670-3")
            row_b["Qty"] = split_qty
            row_b["Amount"] = split_amount
            new_rows.append(row_b)
        else:
            new_rows.append(row)

    return pd.DataFrame(new_rows).reset_index(drop=True)

def apply_pr_mappings(df: pd.DataFrame, mappings: dict = None) -> pd.DataFrame:
    """Enforces WBS and Customer/Project mappings using Substring Matching Priority."""
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
    """Generates prompt instructions dynamically based on active mappings."""
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
# Custom CSS for Title Banner
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        .win11-titlebar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 24px;
            margin: -1rem -1rem 1.5rem -1rem;
            background: #ffffff;
            border-bottom: 4px solid var(--primary-color, #0051ba);
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border-radius: 8px;
        }
        .win11-titlebar h1 {
            font-size: 26px;
            font-weight: 700;
            margin: 0;
        }
        .win11-titlebar p {
            margin: 4px 0 0 0;
            font-size: 16px;
            opacity: 0.8;
        }
        .win11-titlebar .header-logo {
            height: 56px;
            width: auto;
            object-fit: contain;
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
**How to use:**
1. Type in your **PO Number** below (optional).
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
# Main Configuration (Replaced Sidebar)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Main Configuration (Replaced Sidebar)
# ---------------------------------------------------------------------------
with st.expander("⚙️ Configuration & Settings", expanded=False):
    tab1, tab2 = st.tabs(["📝 Special Instructions", "🛠️ Manage Mappings"])
    
    with tab1:
        st.markdown("💡 *Note: Updating the PR # column will automatically recalculate Customer/Project and WBS Task.*")
        custom_instructions_input = st.text_area(
            "Additional rules for this order:",
            placeholder="e.g. Convert all instances of 777 to 648-2 in PR #",
            height=80,
        )
        
    with tab2:
        st.markdown("Add, remove, or edit keyword mappings. Click **Save** to sync with GitHub.")
        
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
        
        if st.button("💾 Save Changes", type="primary", use_container_width=True):
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
                    st.toast("Mappings updated and synced!", icon="✅")
            else:
                st.error("⚠️ No valid mapping rows detected to save.")

# ---------------------------------------------------------------------------
# UI Inputs
# ---------------------------------------------------------------------------
with st.container(border=True):
    st.subheader("Step 1: Enter PO Details")
    po_number = st.text_input("PO Number (Optional)", placeholder="Example: PO1536", help="Enter the Purchase Order number for this import or leave blank.")
    expected_date = st.date_input("Expected Date (Optional)", value=None, help="Select the expected date for all items or leave blank.")

uploaded_file_obj = None
text_input = ""

with st.container(border=True):
    st.subheader("Step 2: Provide Order Info")
    
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

st.write("")
col_process, col_debug = st.columns([3, 1])
with col_process:
    process_clicked = st.button("🚀 Process Order & Generate CSV", type="primary", use_container_width=True)
with col_debug:
    debug_mode = st.toggle("🐞 Debug Mode", help="Show raw JSON output from the AI")

# ---------------------------------------------------------------------------
# Processing Action
# ---------------------------------------------------------------------------
if process_clicked:
    st.session_state.processed_df = None
    st.session_state.shipping_cost = None
    st.session_state.raw_ai_output = None
    
    if input_type == "📁 Upload File (PDF, Image, Excel, CSV)" and not uploaded_file_obj:
        st.warning("⚠️ Please upload a file in Step 2.")
    elif input_type == "📋 Copy & Paste Order Text" and not text_input.strip():
        st.warning("⚠️ Please paste the order text in Step 2.")
    else:
        instructions_list = [
            "Exclude any freight, shipping, tax, handling, or non-item charge lines from the line items list.",
            "If a PR contains '670-2/3', split it into two separate line items (e.g. 1A with PR '670-2' and 1B with PR '670-3'), dividing the original total quantity equally between them."
        ]
        
        # Ensure we capture custom instructions safely
        try:
            if custom_instructions_input.strip():
                instructions_list.append(custom_instructions_input.strip())
        except NameError:
            pass

        full_custom_instructions = "\n".join(f"- {inst}" for inst in instructions_list)
        mapping_rules_text = generate_mapping_prompt_rules(st.session_state.pr_mappings)
        po_instruction = f"- PO Number to use for all items: {po_number}" if po_number.strip() else "- PO Number: Leave blank unless explicitly found in the document."

        with st.spinner("⏳ Analyzing order details... This usually takes about 30 seconds to 2 minutes."):
            try:
                prompt = f"""
                You are a data extraction assistant for NetSuite imports.
                Extract line items and shipping cost from the provided document/text and output structured data.

                Context & Rules:
                {po_instruction}
                - Custom Instructions:
                {full_custom_instructions}
                {mapping_rules_text}

                CRITICAL EXTRACTION RULES:
                1. TABLE EXCLUSIONS: Always exclude tax, freight, shipping, and handling charge lines from the line items array.
                2. SHIPPING EXTRACTION: Extract the separate shipping/freight cost amount (if present) as a float into "shipping_cost". If no shipping cost is present, set "shipping_cost" to null.
                3. PR # VERBATIM PRESERVATION:
                   - Extract and retain the FULL string present in the PR / Job / Order reference line word-for-word.
                   - DO NOT strip out or discard job names, room descriptions, notes, numbers, or prefixes/suffixes.
                4. COMBO SPLIT RULE (670-2/3):
                   - If the PR contains '670-2/3', create TWO line items:
                     * Line Item A (e.g. '1A'): PR # with '670-2', half the total quantity (Qty / 2), and half the calculated amount.
                     * Line Item B (e.g. '1B'): PR # with '670-3', half the total quantity (Qty / 2), and half the calculated amount.
                5. MATH EVALUATION RULE: If any field contains a mathematical expression starting with '=' or containing math (e.g., `=10+20`), evaluate it and output the calculated numerical value.
                6. CONFIDENCE SCORING: Evaluate how certain you are of the extraction for each row. Provide a "Confidence Score" between 0.0 and 1.0. Assign a score below 0.8 if the item data was difficult to parse, blurry, ambiguous, or required guesswork.
                7. EXHAUSTIVE EXTRACTION: You MUST process and extract every single valid line item from the provided text. Do not stop early, do not skip lines, and do not summarize. You must continue extracting items until the very end of the provided order text.
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
                                    "Line Item": {"type": "STRING"},
                                    "Customer/Project": {"type": "STRING"},
                                    "Custom WBS Task": {"type": "STRING"},
                                    "PO": {"type": "STRING"},
                                    "PR #": {"type": "STRING"},
                                    "Manufacturer Part Number": {"type": "STRING"},
                                    "Item Description": {"type": "STRING"},
                                    "Qty": {"type": "NUMBER"},
                                    "Cost Price": {"type": "NUMBER"},
                                    "Amount": {"type": "NUMBER"},
                                    "Confidence Score": {"type": "NUMBER"}
                                },
                                "required": ["Line Item", "PO", "PR #", "Manufacturer Part Number", "Item Description", "Qty", "Cost Price", "Amount", "Confidence Score"],
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
                st.session_state.raw_ai_output = parsed_data # Save for Debug Mode
                
                items_data = parsed_data.get("items", [])
                extracted_shipping = parsed_data.get("shipping_cost", None)

                df = pd.DataFrame(items_data)

                if expected_date:
                    df["Expected Date"] = expected_date.strftime("%m/%d/%Y")

                # Step 1: Enforce combo line item split (670-2/3 -> 1A/1B)
                df = split_combo_pr_rows(df)

                # Step 2: Apply WBS & Project mappings
                df = apply_pr_mappings(df, st.session_state.pr_mappings)

                # Step 3: Sanitize dataframe to prevent formula injection
                df = sanitize_dataframe(df)

                st.session_state.processed_df = df
                st.session_state.shipping_cost = extracted_shipping

                try:
                    total_order_val = (df["Qty"].astype(float) * df["Cost Price"].astype(float)).sum()
                except Exception:
                    total_order_val = 0.0

                audit_entry = {
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "PO Number": po_number if po_number.strip() else "None",
                    "Source": file_source_name,
                    "Line Items": len(df),
                    "Order Total ($)": round(float(total_order_val), 2),
                    "Shipping ($)": round(float(extracted_shipping), 2) if extracted_shipping is not None else 0.0,
                    "Model Used": model_name
                }
                st.session_state.audit_history.insert(0, audit_entry)

                st.toast("Order successfully processed!", icon="✅")
                
                if attempt > 0:
                    st.toast(f"Notice: A backup AI model ({model_name}) was used.", icon="⚠️")

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
    
    # 🐞 Debug Output Visibility Check
    if debug_mode and st.session_state.raw_ai_output:
        with st.expander("🐞 Debug Mode: Raw AI API Output", expanded=True):
            st.json(st.session_state.raw_ai_output)

    st.markdown("---")
    st.subheader("Step 3: Review & Download")

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
        st.markdown("💡 **Tip:** You can double-click any cell below to edit values before downloading. Rows highlighted in red indicate a low confidence score (< 0.8) from the AI and should be double-checked.")
        
        def style_low_confidence(row):
            try:
                score = float(row.get("Confidence Score", 1.0))
                if score < 0.8:
                    return ['background-color: rgba(255, 99, 71, 0.3)'] * len(row)
            except (ValueError, TypeError):
                pass
            return [''] * len(row)

        styled_df = st.session_state.processed_df.style.apply(style_low_confidence, axis=1)

        edited_df = st.data_editor(
            styled_df, 
            use_container_width=True, 
            num_rows="dynamic",
            hide_index=True
        )

    final_export_df = apply_pr_mappings(edited_df, st.session_state.pr_mappings)
    final_export_df = sanitize_dataframe(final_export_df)
    
    # Remove Confidence Score before downloading
    final_export_df = final_export_df.drop(columns=["Confidence Score"], errors="ignore")

    csv_buffer = io.BytesIO()
    final_export_df.to_csv(csv_buffer, index=False)

    file_prefix = po_number.strip() if po_number.strip() else "Order"
    
    col_dl, col_reset = st.columns([2, 1])
    with col_dl:
        st.download_button(
            label="📥 Download NetSuite CSV File",
            data=csv_buffer.getvalue(),
            file_name=f"{file_prefix}_NetSuite_Import.csv",
            mime="text/csv",
            use_container_width=True
        )
    with col_reset:
        if st.button("🔄 Start Next Order", use_container_width=True):
            st.session_state.processed_df = None
            st.session_state.shipping_cost = None
            st.session_state.raw_ai_output = None
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
