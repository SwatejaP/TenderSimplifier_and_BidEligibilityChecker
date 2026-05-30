# Walkthrough - Tender Simplifier

We have successfully implemented the **Tender Simplifier** application. The app leverages a hybrid AI + deterministic rules-based architecture, utilizing **Streamlit** for the frontend, **LangChain / Groq (Llama 3 70B)** for text processing and interactive chatbot queries, **HuggingFace** for local embeddings, and **python-docx** to export compliance checklists.

## Directory Structure

```text
d:/genAi_hackathon/tender-simplifier/
├── app.py                  # Main Streamlit UI and layout logic
├── core_engine.py          # Unified PDF text extraction, FAISS vector indexing, and ChatGroq querying
├── prompts.py              # Centralized prompt templates for Llama 3 70B
├── section_extractor.py    # Summarization, timeline milestone, and document checklist extraction
├── eligibility_engine.py   # Extracts eligibility criteria via LLM and evaluates vendor eligibility in Python
├── doc_generator.py        # Compiles executive summaries and checklists into downloadable Word docs (.docx)
├── requirements.txt        # Package dependencies (Streamlit, LangChain, FAISS, python-docx, etc.)
└── .env                    # Environment variables (contains GROQ_API_KEY)
```

---

## Technical Highlights

### 1. Unified Core Engine
- **Text Extraction**: Uses a layered approach with [pdfplumber](file:///d:/genAi_hackathon/tender-simplifier/core_engine.py) to preserve column and table structures (critical for tender tables), with a fallback to `PyPDF2` in case of errors.
- **RAG & FAISS**: Builds an in-memory `FAISS` vector database using local HuggingFace embeddings (`all-MiniLM-L6-v2`), completely eliminating vector storage and embedding API costs.

### 2. Dual-Pass Eligibility Evaluator
- Follows the design principle **"LLM Extracts Criteria, Python Compares Criteria"**.
- [eligibility_engine.py](file:///d:/genAi_hackathon/tender-simplifier/eligibility_engine.py) prompts Llama 3 70B to pull criteria fields into a clean JSON scheme (turnover, experience, certifications, and MSME benefits).
- It then executes a deterministic Python comparison check against the vendor's profile settings (entered in the sidebar). This completely prevents the LLM from hallucinating bid approvals.

### 3. Compliance Document checklist & Timeline
- Extracts all documents and dates into interactive lists. Bidders can check items off directly in the Streamlit UI.
- Generates a professionally styled `.docx` report on demand for offline tracking and printing.

---

## How to Run & Verify

### 1. Set Up Environment Variables
Update the [.env](file:///d:/genAi_hackathon/tender-simplifier/.env) file with your actual Groq API key:
```env
GROQ_API_KEY=gsk_your_actual_key_here
```

### 2. Install Dependencies
Run the following command inside a virtual environment to install all required packages:
```bash
pip install -r requirements.txt
```

### 3. Run the App
Launch the Streamlit app:
```bash
streamlit run app.py
```

### 4. Verification with Mock PDF
We created a script [generate_mock_tender.py](file:///d:/genAi_hackathon/tender-simplifier/generate_mock_tender.py) that generates `mock_tender.pdf` containing realistic tender data. 
- You can upload this PDF to verify the extraction, pass/fail validation, timeline milestones, doc checklist, and the conversational chatbot.
