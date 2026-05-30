import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Ensure environment variables are loaded first
load_dotenv()

# Set page configuration with a premium dark theme default
st.set_page_config(
    page_title="Tender Simplifier - AI Compliance Auditor",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded"
)

from pdf_processing import extract_text_from_pdf
from rag_engine import TenderRAGEngine
from section_extractor import get_tender_summary, get_timeline, get_document_checklist
from eligibility_engine import extract_tender_criteria, evaluate_vendor_eligibility
from doc_generator import generate_docx_report
from prompts import CHAT_SYSTEM_PROMPT

# Inject premium custom CSS for aesthetics
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap');
    
    /* Global Styles */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3, .title-text {
        font-family: 'Outfit', sans-serif;
        color: #ffffff;
    }
    
    /* Glassmorphic header card */
    .glass-header {
        background: linear-gradient(135deg, rgba(31, 78, 121, 0.25) 0%, rgba(20, 30, 48, 0.7) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 30px;
        margin-bottom: 25px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    
    /* Styled container cards */
    .styled-card {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
        padding: 20px;
        margin-bottom: 15px;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .styled-card:hover {
        transform: translateY(-2px);
        border-color: rgba(31, 78, 121, 0.3);
    }
    
    /* Status Badges */
    .badge-pass {
        background-color: rgba(46, 204, 113, 0.15);
        color: #2ecc71;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85em;
        border: 1px solid rgba(46, 204, 113, 0.3);
        display: inline-block;
        margin-top: 5px;
    }
    .badge-fail {
        background-color: rgba(231, 76, 60, 0.15);
        color: #e74c3c;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85em;
        border: 1px solid rgba(231, 76, 60, 0.3);
        display: inline-block;
        margin-top: 5px;
    }
    .badge-info {
        background-color: rgba(52, 152, 219, 0.15);
        color: #3498db;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85em;
        border: 1px solid rgba(52, 152, 219, 0.3);
        display: inline-block;
        margin-top: 5px;
    }
    
    /* Custom banner for eligibility status */
    .status-banner-eligible {
        background: linear-gradient(90deg, rgba(46, 204, 113, 0.2) 0%, rgba(46, 204, 113, 0.05) 100%);
        border-left: 5px solid #2ecc71;
        border-radius: 6px;
        padding: 15px 20px;
        margin-bottom: 20px;
    }
    .status-banner-ineligible {
        background: linear-gradient(90deg, rgba(231, 76, 60, 0.2) 0%, rgba(231, 76, 60, 0.05) 100%);
        border-left: 5px solid #e74c3c;
        border-radius: 6px;
        padding: 15px 20px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# 1. Header Banner
st.markdown("""
<div class="glass-header">
    <h1 style="margin: 0; font-size: 2.8rem; font-weight: 800; background: linear-gradient(45deg, #ffffff, #85a1c1); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">✨ Tender Simplifier</h1>
    <p style="margin: 5px 0 0 0; color: #a0aec0; font-size: 1.1rem; font-weight: 400;">
        Real PDF Dataset compliance copilot & rules-based bid eligibility evaluator
    </p>
</div>
""", unsafe_allow_html=True)

# Check API Key Availability
groq_key = os.getenv("GROQ_API_KEY")
if not groq_key or "placeholder" in groq_key:
    st.warning("⚠️ **GROQ_API_KEY** is currently unset or placeholder. Please update the `.env` file in the project folder with a valid key from console.groq.com.")

# 2. Cache the Tender Engine
@st.cache_resource
def load_rag_engine():
    with st.spinner("Initializing HuggingFace Embedding Model & ChatGroq Engine..."):
        return TenderRAGEngine()

rag_engine = load_rag_engine()

# 3. Sidebar - Settings & Vendor Profile Configurator
st.sidebar.markdown("<h2 style='margin-top:0;'>⚙️ System Settings</h2>", unsafe_allow_html=True)
selected_model = st.sidebar.selectbox(
    "LLM Model",
    ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
    index=0,
    help="Default is Llama 3.1 8B (fast, high API limit). Toggle to Llama 3.3 70B for highly precise criteria extraction."
)
st.session_state.selected_model = selected_model

st.sidebar.markdown("<h2 style='margin-top:15px;'>🏢 Vendor Profile</h2>", unsafe_allow_html=True)
st.sidebar.write("Configure your profile parameters to test eligibility against the uploaded tender.")

vendor_name = st.sidebar.text_input("Company Name", value="Horizon Technologies Pvt Ltd")

# Turnover Input with unit selectors
col1, col2 = st.sidebar.columns([2, 1])
with col1:
    turnover_val = st.number_input("Annual Turnover", min_value=0.0, value=12.0, step=1.0)
with col2:
    turnover_unit = st.selectbox("Unit", ["Crores", "Lakhs", "Absolute INR"], index=0)

# Convert turnover to absolute INR
if turnover_unit == "Crores":
    absolute_turnover = turnover_val * 10_000_000
elif turnover_unit == "Lakhs":
    absolute_turnover = turnover_val * 100_000
else:
    absolute_turnover = turnover_val

experience_years = st.sidebar.number_input("Years of Experience", min_value=0, value=7, step=1)

# Certifications selection and custom adder
common_certs = ["ISO 9001", "ISO 27001", "CMMI Level 3", "CMMI Level 5", "GST Registration", "PAN Card", "MSME Registration", "NSIC Certificate"]
vendor_certs = st.sidebar.multiselect("Active Certifications", common_certs, default=["ISO 9001", "GST Registration", "PAN Card", "MSME Registration"])

custom_cert = st.sidebar.text_input("Add Custom Certification (press Enter)")
if custom_cert and custom_cert not in vendor_certs:
    vendor_certs.append(custom_cert)

msme_status = st.sidebar.checkbox("Is MSME / NSIC Registered?", value=True)

completed_projects_text = st.sidebar.text_area("Key Projects Completed", 
    placeholder="1. Design & Deployment of e-Governance portal for State Gov (2024)\n2. Cloud Migration for Smart City Project (2025)",
    value="1. Smart City Portal Development (Value: 5 Cr)\n2. Cloud Infrastructure Migration for Municipal Corp (Value: 8 Cr)"
)

# Build vendor profile dict
vendor_profile = {
    "name": vendor_name,
    "turnover": absolute_turnover,
    "experience": experience_years,
    "certifications": vendor_certs,
    "msme_status": msme_status,
    "projects": completed_projects_text
}

# 4. Main Body - PDF Upload
st.write("---")
uploaded_file = st.file_uploader("Upload Tender PDF Document (CPPP / Karnataka e-Procurement)", type=["pdf"])

# Manage session state for uploaded file to avoid recalculating on every run
if uploaded_file is not None:
    # Check if we uploaded a new file
    file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if "current_file_id" not in st.session_state or st.session_state.current_file_id != file_id:
        st.session_state.current_file_id = file_id
        # Reset cache
        st.session_state.raw_text = None
        st.session_state.vector_store = None
        st.session_state.summary = None
        st.session_state.criteria = None
        st.session_state.timeline = None
        st.session_state.checklist = None
        st.session_state.messages = [] # Reset chatbot history

    # Process PDF if not already done
    if st.session_state.raw_text is None:
        with st.spinner("Step 1/5: Extracting text layout from PDF (pdfplumber/PyPDF2)..."):
            try:
                # Read bytes and pass to engine
                pdf_bytes = uploaded_file.read()
                raw_text = extract_text_from_pdf(pdf_bytes)
                st.session_state.raw_text = raw_text
            except Exception as e:
                st.error(f"Error parsing PDF: {e}")
                st.stop()

        with st.spinner("Step 2/5: Creating local FAISS Vector Store for Chatbot..."):
            try:
                vector_store = rag_engine.create_vector_store(st.session_state.raw_text)
                st.session_state.vector_store = vector_store
            except Exception as e:
                st.error(f"Error indexing vectors: {e}")
                st.stop()

        with st.spinner("Step 3/5: Isolating sections & building Executive Summary..."):
            st.session_state.summary = get_tender_summary(st.session_state.raw_text)

        with st.spinner("Step 4/5: Compiling timeline & submission checklists..."):
            st.session_state.timeline = get_timeline(st.session_state.raw_text)
            st.session_state.checklist = get_document_checklist(st.session_state.raw_text)

        with st.spinner("Step 5/5: Building eligibility verification rules..."):
            st.session_state.criteria = extract_tender_criteria(st.session_state.raw_text)
            
        st.success("Tender compliance model synchronized successfully!")

    # 5. UI Tabs
    tab_summary, tab_eligibility, tab_checklist, tab_chat = st.tabs([
        "📊 Tender Summary", 
        "⚖️ Eligibility Checker", 
        "📋 Checklist & Timeline", 
        "💬 Interactive Copilot"
    ])

    # --- TAB 1: Tender Summary ---
    with tab_summary:
        st.subheader("Tender Executive Summary")
        st.markdown(st.session_state.summary)

    # --- TAB 2: Eligibility Checker ---
    with tab_eligibility:
        st.subheader("Deterministic Vendor Eligibility Assessment")
        st.write("Below is a rule-based audit comparing your **Vendor Profile** parameters against the extracted rules.")
        
        # Calculate eligibility dynamically based on sidebar profile and extracted criteria
        eligibility_results = evaluate_vendor_eligibility(vendor_profile, st.session_state.criteria)
        
        # Big overall assessment banner
        if eligibility_results.get("extraction_error", False):
            st.markdown(f"""
            <div class="status-banner-ineligible" style="border-left: 5px solid #f39c12; background: linear-gradient(90deg, rgba(243, 156, 18, 0.2) 0%, rgba(243, 156, 18, 0.05) 100%);">
                <h3 style="color:#f39c12; margin:0;">⚠️ Evaluation Suspended</h3>
                <p style="color:#ffffff; margin:5px 0 0 0;">LLM parameter extraction failed due to a connection/rate-limit error. Please try again or switch to a higher quota model (like Llama 3.1 8B) in the sidebar.</p>
            </div>
            """, unsafe_allow_html=True)
        elif eligibility_results["eligible"]:
            st.markdown(f"""
            <div class="status-banner-eligible">
                <h3 style="color:#2ecc71; margin:0;">✅ Eligible to Bid</h3>
                <p style="color:#ffffff; margin:5px 0 0 0;">Your profile meets or exceeds all extracted mandatory criteria.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="status-banner-ineligible">
                <h3 style="color:#e74c3c; margin:0;">❌ Ineligible to Bid</h3>
                <p style="color:#ffffff; margin:5px 0 0 0;">One or more mandatory compliance thresholds have not been met. Check details below.</p>
            </div>
            """, unsafe_allow_html=True)

        col_left, col_right = st.columns(2)
        
        with col_left:
            st.markdown("### 📈 Turnover Verification")
            turnover_res = eligibility_results.get("turnover", {})
            t_status = turnover_res.get("status", "FAIL")
            
            st.write(f"**Required Threshold:** {turnover_res.get('required')}")
            st.write(f"**Your Turnover:** {turnover_res.get('vendor')}")
            if t_status == "PASS":
                st.markdown('<span class="badge-pass">PASS</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-fail">FAIL</span>', unsafe_allow_html=True)
            st.info(f"**Extracted Text Rule:** {turnover_res.get('details')}")

            st.write("---")
            
            st.markdown("### 🏆 Certifications Verification")
            cert_res = eligibility_results.get("certifications", {})
            c_status = cert_res.get("status", "FAIL")
            
            # List each required certification and its status
            items = cert_res.get("items", [])
            if items:
                st.write("**Required Certifications Checklist:**")
                for item in items:
                    c_name = item.get("certification")
                    c_stat = item.get("status")
                    if c_stat == "PASS":
                        st.markdown(f"✅ **{c_name}**: Available in profile")
                    else:
                        st.markdown(f"❌ **{c_name}**: <span style='color:#e74c3c; font-weight:bold;'>Missing</span>", unsafe_allow_html=True)
                        st.warning(f"💡 **Action Required**: Add `{c_name}` (or a keyword like `CoA` / `Council of Architecture`) in the **Add Custom Certification** sidebar field to update your eligibility.")
            else:
                st.write(f"**Required:** {cert_res.get('required')}")
                st.write(f"**Provided:** {cert_res.get('vendor')}")
                if c_status == "PASS":
                    st.markdown('<span class="badge-pass">PASS</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="badge-fail">FAIL</span>', unsafe_allow_html=True)
            
            st.info(f"**Extracted Text Rule:** {cert_res.get('details')}")

        with col_right:
            st.markdown("### ⏳ Experience Verification")
            exp_res = eligibility_results.get("experience", {})
            e_status = exp_res.get("status", "FAIL")
            
            st.write(f"**Required Years:** {exp_res.get('required')}")
            st.write(f"**Your Experience:** {exp_res.get('vendor')}")
            if e_status == "PASS":
                st.markdown('<span class="badge-pass">PASS</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-fail">FAIL</span>', unsafe_allow_html=True)
            st.info(f"**Extracted Text Rule:** {exp_res.get('details')}")

            st.write("---")

            st.markdown("### 💡 MSME / NSIC Exemption Analysis")
            msme_res = eligibility_results.get("emd_exemption", {})
            st.write(f"**EMD Exemption Mentioned:** {'Yes' if msme_res.get('exempt') else 'No'}")
            st.markdown(f'<span class="badge-info">MSME EXEMPTION NOTE</span>', unsafe_allow_html=True)
            st.info(f"**Extracted Text Rule:** {msme_res.get('details')}")

    # --- TAB 3: Checklist & Timeline ---
    with tab_checklist:
        col_time, col_check = st.columns([1, 1])
        
        with col_time:
            st.subheader("📅 Critical Milestones & Timeline")
            if st.session_state.timeline:
                for idx, milestone in enumerate(st.session_state.timeline):
                    st.markdown(f"""
                    <div class="styled-card">
                        <div style="font-weight: 700; color: #1F4E79; font-size:1.1em;">{milestone.get('date', 'N/A')}</div>
                        <div style="font-weight: 600; font-size:1em; margin: 4px 0;">{milestone.get('milestone', 'N/A')}</div>
                        <div style="color: #cbd5e0; font-size:0.9em;">{milestone.get('description', 'N/A')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.write("No specific critical dates extracted from the document.")

        with col_check:
            st.subheader("📋 Document Submission Checklist")
            st.write("Interactive list of documents required for your submission package:")
            
            updated_checklist = []
            if st.session_state.checklist:
                for idx, doc_item in enumerate(st.session_state.checklist):
                    is_mandatory = doc_item.get("mandatory", True)
                    mandatory_badge = " [MANDATORY]" if is_mandatory else " [OPTIONAL]"
                    
                    # Create an interactive checkbox
                    checked = st.checkbox(
                        f"{doc_item.get('document_name', 'Document')} ({doc_item.get('category', 'Eligibility')}){mandatory_badge}",
                        key=f"chk_{idx}"
                    )
                    
                    st.markdown(f"<p style='color:#a0aec0; margin-left: 28px; margin-top:-10px; font-size:0.85em; font-style:italic;'>{doc_item.get('description', '')}</p>", unsafe_allow_html=True)
                    
                    # Append status for Word export
                    item_copy = doc_item.copy()
                    item_copy["checked_status"] = "Completed" if checked else "Pending"
                    updated_checklist.append(item_copy)
            else:
                st.write("No required documents found.")
                
        # Export DOCX report
        st.write("---")
        st.subheader("🖨️ Export Audit Report")
        st.write("Download a professional Word document containing the parsed summary, eligibility findings, critical timeline, and compliance checklist.")
        
        try:
            # Generate docx
            docx_data = generate_docx_report(
                st.session_state.summary,
                st.session_state.timeline,
                st.session_state.checklist,
                eligibility_results,
                vendor_profile
            )
            
            st.download_button(
                label="📥 Download Compliance Report (.docx)",
                data=docx_data,
                file_name=f"Tender_Compliance_Report_{vendor_name.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as e:
            st.error(f"Error generating document download: {e}")

    # --- TAB 4: Chatbot ---
    with tab_chat:
        st.subheader("💬 Tender Compliance Copilot")
        st.write("Ask any questions about the tender document terms, technical specs, or criteria details.")
        
        # Display chat messages from history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # React to user input
        if prompt := st.chat_input("What is the EMD amount? Are joint ventures allowed?"):
            # Display user message in chat message container
            st.chat_message("user").markdown(prompt)
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Formulate response
            with st.chat_message("assistant"):
                with st.spinner("Scanning index..."):
                    try:
                        response = rag_engine.query_tender(
                            st.session_state.vector_store,
                            CHAT_SYSTEM_PROMPT,
                            prompt
                        )
                        st.markdown(response)
                        # Add assistant response to chat history
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    except Exception as e:
                        st.error(f"Error querying ChatGroq: {e}")
else:
    # Landing page state
    st.info("👋 Please upload a real CPPP or Karnataka e-Procurement Tender PDF in the file uploader above to begin analysis.")
    
    st.markdown("""
    ### System Architecture & Pipeline:
    1. **Data Layer**: Processes real, publicly available tender documents (e.g. from CPPP or Karnataka e-Procurement).
    2. **Document Processing**: Layout-aware text extraction and sanitation.
    3. **Extraction Layer**: Rules and regex pre-filtering to isolate key sections, followed by Llama 3 70B normalization.
    4. **Decision Engine**: 100% deterministic rule matching in Python (no LLM hallucination in Pass/Fail results).
    5. **Compliance Checklist**: Interactive visual checkmarks with one-click export to a professional Word document (.docx).
    6. **RAG Copilot**: In-memory FAISS retrieval QA system for ad-hoc compliance queries.
    """)
