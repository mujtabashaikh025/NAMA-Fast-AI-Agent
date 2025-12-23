import streamlit as st
from google import generativeai as genai
import pytesseract
from pdf2image import convert_from_bytes
import pandas as pd
import json
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date

# --- 1. CONFIGURATION & SETUP ---
st.set_page_config(page_title="NAMA Compliance Agent", layout="wide")

# HARDCODED API KEY
api_key =  st.secrets["auth_key"] 
genai.configure(api_key=api_key)

REQUIRED_DOCS = [
    "1- Fees application receipt copy.",
    "2- Nama water services vendor registeration certificates & Product Agency certificates or authorization letter from Factory for local distributor ratified from Oman embassy.",
    "3- Certificate of incorporation of the firm (Factory & Foundry).",
    "4- Manufacturing Process flow chart of product and list of out sourced process / operation if applicable including Outsourcing name & address.",
    "5-Valid copies certificates of (ISO 9001, ISO 45001 & ISO 14001).",
    "6- Factory Layout chart.",
    "7-Factory Organizational structure, Hierarchy levels, Ownership details.",
    "8- Product Compliance Statement with reference to Nama water services specifications (with supports documents accordingly).",
    "9- Product Technical datasheets.",
    "10- Omanisation details from Ministry of Labour.",
    "11- Product Independent Test certificates.",
    "12- Attestation of Sanitary Conformity (hygiene test including mechanical assessment for a full product certificate at 50 degrees Celsiusfull to used in drinking water)",
    "13- Provide products Chemicals Composition of materials.",
    "14- Reference list of products used in Oman or any GCC projects with contact no. or emails of end user or clients."
]

# --- 2. OCR EXTRACTION (TESSERACT) ---
def extract_text_from_pdf(uploaded_file):
    """Converts PDF to Images and performs OCR using Tesseract."""
    try:
        # Important: Reset file pointer to read bytes
        file_bytes = uploaded_file.getvalue()
        # Convert first 3 pages to images to maintain speed
        images = convert_from_bytes(file_bytes, first_page=1, last_page=3)
        
        text = f"FILE_NAME: {uploaded_file.name}\n"
        for img in images:
            text += pytesseract.image_to_string(img)
            
        return text[:15000] # Trim to prevent context overflow
    except Exception as e:
        return f"Error reading {uploaded_file.name}: {str(e)}"

def batch_extract_all(files):
    """Uses ThreadPoolExecutor to OCR 50+ PDFs simultaneously."""
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(extract_text_from_pdf, files))
    return results

# --- 3. BATCHED AI ANALYSIS ---
def analyze_batch(batch_text_list):
    """Sends a group of documents to Gemini 1.5 Flash for speed."""
    # Note: Corrected model name to 1.5-flash
    model = genai.GenerativeModel('gemini-2.5-pro')
    today_str = date.today().strftime("%Y-%m-%d")

    # Cleaned the JSON schema to prevent 'list' object errors
    prompt = f"""
    Today is {today_str}. You are NAMA Document Analyzer.
    Extract data from pdfs and translate it if it is not in english.
    Classify each document using this list: {json.dumps(REQUIRED_DOCS)}
    
    Compliance Rule: ISO certificates must be valid for >180 days from {today_str}.
    
    Return ONLY a JSON object with this EXACT structure:
    {{
        "iso_analysis": [
            {{
                "standard": "ISO 9001",
                "expiry_date": "YYYY-MM-DD",
                "days_remaining": 0,
                "compliance_status": "Pass/Fail",
                "confidence_score": 0.9
            }}
        ],
        "found_documents": [
            {{"filename": "name.pdf", "Type": "Category from list", "Status": "Valid"}}
        ],
        "wras_analysis": {{
            "found": false, 
            "wras_id": "N/A",
            "manufacturer_pdf": "N/A"
        }}
    }}
    """
    
    combined_content = "\n\n=== NEXT DOCUMENT ===\n".join(batch_text_list)
    
    response = model.generate_content(
        contents=[prompt, combined_content],
        generation_config={"response_mime_type": "application/json"}
    )
    
    try:
        data = json.loads(response.text)
        # Ensure we return a dict even if AI wraps it in a list
        if isinstance(data, list):
            return data[0]
        return data
    except Exception:
        return {}

# --- 4. UI LOGIC ---
st.title("🛡️ NAMA High-Speed Compliance Audit (OCR Mode)")

uploaded_files = st.file_uploader("Upload PDF documents", type=["pdf"], accept_multiple_files=True)

if st.button("Run Audit", type="primary"):
    if uploaded_files:
        start_time = datetime.now()
        
        with st.spinner(f"⚡ Running OCR and AI Analysis on {len(uploaded_files)} files..."):
            all_texts = batch_extract_all(uploaded_files)
            
            final_report = {
                "iso_analysis": [],
                "wras_analysis": {"found": False},
                "found_documents": [],
                "missing_documents": set(REQUIRED_DOCS)
            }
            
            batch_size = 10
            for i in range(0, len(all_texts), batch_size):
                current_batch = all_texts[i:i + batch_size]
                batch_res = analyze_batch(current_batch)
                
                # Check if batch_res is valid dictionary
                if not isinstance(batch_res, dict):
                    continue

                final_report["iso_analysis"].extend(batch_res.get("iso_analysis", []))
                final_report["found_documents"].extend(batch_res.get("found_documents", []))
                
                # Safe WRAS Check
                wras = batch_res.get("wras_analysis", {})
                if isinstance(wras, dict) and wras.get("found"):
                    final_report["wras_analysis"] = wras
                
                # Remove found items from missing set
                for doc in batch_res.get("found_documents", []):
                    doc_type = doc.get("Type")
                    if doc_type in final_report["missing_documents"]:
                        final_report["missing_documents"].remove(doc_type)

            st.session_state.analysis_result = final_report
            
        duration = (datetime.now() - start_time).total_seconds()
        st.success(f"Audit Complete in {duration:.2f} seconds!")

# --- 5. DISPLAY RESULTS ---
if "analysis_result" in st.session_state:
    res = st.session_state.analysis_result
    
    st.subheader("❌ Missing Documents")
    for m in sorted(list(res["missing_documents"])):
        st.error(f"Missing: {m}")
            
    st.subheader("✅ Documents Found")
    if res["found_documents"]:
        st.dataframe(pd.DataFrame(res["found_documents"]), use_container_width=True)
    else:
        st.write("No documents matched.")

    st.subheader("🏭 ISO Validation (180-Day Rule)")
    iso_data = res.get('iso_analysis', [])
    if iso_data:
        cols = st.columns(3)
        for idx, iso in enumerate(iso_data):
            with cols[idx % 3]:
                # Safe access using .get()
                std_name = iso.get('standard', 'Unknown ISO')
                status = iso.get('compliance_status', 'Fail')
                days = iso.get('days_remaining', 0)
                
                status_color = "green" if "Pass" in status else "red"
                with st.container(border=True):
                    st.markdown(f"#### :{status_color}[{std_name}]")
                    if days < 180:
                        st.error(f"⚠️ {days} days left")
                    else:
                        st.success(f"✅ {days} days left")
                    st.caption(f"Expires: {iso.get('expiry_date')}")
