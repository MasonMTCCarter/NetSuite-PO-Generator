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

                clean_json_str = response.text.replace("```json", "").replace("```", "").strip()
                data = json.loads(clean_json_str)

                # Step 1: Parse DataFrame
                df = pd.DataFrame(data)

                # Step 2: Post-process mapping in Python to guarantee 100% compliance with final PR #
                df = apply_pr_mappings(df)

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
