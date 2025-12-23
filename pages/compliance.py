import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Compliance Extractor", layout="wide")
st.image("nama-logo.png")

# REPLACE with your actual API Key
api_key =  "AIzaSyDwaYLytrIWKf0M3ru4b3hR3R2qh8tPYrE"

# --- 2. HELPER FUNCTIONS ---

def clean_json_string(json_str):
    """Cleans Markdown formatting from JSON string."""
    cleaned = re.sub(r"```json\s*", "", json_str)
    cleaned = re.sub(r"```", "", cleaned)
    return cleaned.strip()

def get_compliance_table(pdf_bytes, key):
    """Sends the PDF file DIRECTLY to Gemini (no local text extraction needed)."""
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-3-pro-preview')
        
        system_prompt = """
        You are a Technical QA Engineer reviewing a scanned Vendor Specification Document.
        
        **YOUR TASK:**
        Look at the document image/PDF and extract a comprehensive Compliance Table.
        
        **INPUT DATA:**
        The document contains a list of "APPLICABLE STANDARDS" (BS EN, ISO, etc.) and specific sections (Climatic Data, Design Considerations, Materials). 
        Next to each item, the vendor has written a response (e.g., "Comply", "Noncomply", "Not related") or used a **handwritten tick/check mark**.
        
        **RULES FOR EXTRACTION:**
        1. **Identify every Standard** (e.g., BS EN 558-1, ISO 9001) and **Key Section** (Climatic Data, Scope, etc.).
        2. **Determine Status:**
           - If text says "Comply", "Included", or has a positive context -> **"Comply"**.
           - If text says "Noncomply", "Not related", "Excluded" -> **"Not Comply"**.
           - **CRITICAL:** If you see a **handwritten tick ($\checkmark$)** or check mark next to a section (especially Climatic Data/Design Considerations) -> Mark as **"Comply"**.
        3. **Generate Remark:**
           - If "Not Comply", explain the deviation (e.g., "Vendor excludes galvanization standard").
           - If "Comply" but with a note (e.g., "Comply (Ductile Iron used)"), include that note.

        **OUTPUT FORMAT (JSON ARRAY):**
        [
            {"Standard_Section": "BS EN 558-1", "Status": "Comply", "Remark": "Face-to-face dimensions for valves"},
            {"Standard_Section": "BS EN ISO 1461", "Status": "Not Comply", "Remark": "Vendor states 'Not related', deviating from galvanization requirement"}
        ]
        """

        # Create the data part for Gemini
        pdf_data = {
            "mime_type": "application/pdf",
            "data": pdf_bytes
        }

        # Send both prompt and PDF data
        response = model.generate_content(
            contents=[system_prompt, pdf_data],
            generation_config={"response_mime_type": "application/json"}
        )
        
        return json.loads(clean_json_string(response.text))

    except Exception as e:
        st.error(f"AI Error: {str(e)}")
        return []

# --- 3. STREAMLIT UI ---

st.title("📑 Smart Compliance Report Generator")
st.markdown("Upload a Vendor Specification PDF (Scanned or Digital) to auto-extract the **Compliance Table**.")

uploaded_file = st.file_uploader("Upload Compliance Statement PDF", type=["pdf"])

if uploaded_file and st.button("Generate Compliance Table"):
    with st.spinner("👀 Analyzing PDF Image & Compliance..."):
        
        # Get bytes directly
        bytes_data = uploaded_file.getvalue()
        
        if bytes_data:
            # Get AI Analysis
            table_data = get_compliance_table(bytes_data, api_key)
            
            if table_data:
                # Display Dataframe
                df = pd.DataFrame(table_data)
                
                # Visual Coloring for Status
                def color_status(val):
                    color = '#d4edda' if 'Comply' in val and 'Not' not in val else '#f8d7da'
                    return f'background-color: {color}'

                st.subheader("Compliance Report")
                st.dataframe(
                    df.style.map(color_status, subset=['Status']),
                    column_config={
                        "Standard_Section": "Standard / Section",
                        "Status": "Compliance Status",
                        "Remark": "AI Observations / Remarks"
                    },
                    use_container_width=True
                )
                
                # Download Button
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Table as CSV",
                    data=csv,
                    file_name="compliance_table.csv",
                    mime="text/csv",
                )
            else:

                st.warning("Could not extract a table. Please ensure the PDF is not password protected.")

