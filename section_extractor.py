import json
import re
import os
import logging
from langchain_groq import ChatGroq
from prompts import SUMMARIZATION_PROMPT, TIMELINE_PROMPT, CHECKLIST_PROMPT

logger = logging.getLogger(__name__)

# Keywords dictionary mapping section types to lists of relevant search terms
SECTION_KEYWORDS = {
    "scope": [
        "scope of work", "scope of supply", "work description", "nature of work", 
        "brief description of work", "objectives", "detailed scope", "project scope"
    ],
    "emd": [
        "earnest money", "emd", "bid security", "security deposit", "exempt", 
        "emd exemption", "bid declaration", "tender fee"
    ],
    "dates": [
        "critical dates", "tender calendar", "key dates", "schedule of dates", 
        "pre-bid meeting", "submission deadline", "opening date", "important dates",
        "tender schedule"
    ],
    "documents": [
        "documents to be uploaded", "list of documents", "checklist", 
        "submission of documents", "documents required", "annexure", 
        "technical bid documents", "document compliance"
    ],
    "eligibility": [
        "eligibility criteria", "qualification criteria", "minimum qualifying", 
        "technical criteria", "turnover", "financial criteria", "experience criteria",
        "pre-qualification", "bidder eligibility"
    ]
}

def get_llm():
    """Initializes the ChatGroq model for summarization and JSON extraction."""
    # Default to llama-3.1-8b-instant for fast, high daily token limit quota
    model_name = "llama-3.1-8b-instant"
    try:
        import streamlit as st
        if "selected_model" in st.session_state:
            model_name = st.session_state.selected_model
    except Exception:
        pass
        
    return ChatGroq(
        model=model_name,
        temperature=0,
        max_tokens=2048,
        api_key=os.getenv("GROQ_API_KEY")
    )

def clean_json_response(response_text: str) -> dict:
    """Strips markdown styling and attempts to parse JSON."""
    cleaned = response_text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
        
    try:
        # Find first { or [ and corresponding end
        start_dict = cleaned.find('{')
        start_list = cleaned.find('[')
        
        if start_dict != -1 and (start_list == -1 or start_dict < start_list):
            start_idx = start_dict
            end_idx = cleaned.rfind('}')
        elif start_list != -1:
            start_idx = start_list
            end_idx = cleaned.rfind(']')
        else:
            return json.loads(cleaned)
            
        if start_idx != -1 and end_idx != -1:
            return json.loads(cleaned[start_idx:end_idx + 1])
    except Exception as e:
        logger.error(f"JSON parsing error: {e}. Raw response: {response_text}")
        
    return {}

def extract_section_text_by_rules(raw_text: str, section_type: str) -> str:
    """
    Slices the PDF raw text using keyword/regex matches on lines to isolate
    the relevant sections. Grabs a window of text around matches.
    """
    keywords = SECTION_KEYWORDS.get(section_type, [])
    if not keywords:
        return ""
        
    lines = raw_text.split("\n")
    matching_indices = []
    
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        for kw in keywords:
            # Check if keyword is present in a relatively short line (typical heading)
            if kw in line_lower and len(line_stripped := line.strip()) < 120:
                matching_indices.append(idx)
                break
                
    if not matching_indices:
        # Fallback: String matching window extraction anywhere in text
        segments = []
        for kw in keywords:
            for match in re.finditer(re.escape(kw), raw_text, re.IGNORECASE):
                start = max(0, match.start() - 150)
                end = min(len(raw_text), match.end() + 2500)
                segments.append(raw_text[start:end])
        return "\n\n... [Truncated Segment] ...\n\n".join(segments)[:8000]

    # Map indices to ranges, grabbing up to 90 lines (approx 700 words) per match
    ranges = []
    for idx in matching_indices:
        start_line = max(0, idx - 3)
        end_line = min(len(lines), idx + 90)
        ranges.append((start_line, end_line))
        
    # Merge overlapping ranges
    merged_ranges = []
    for start, end in sorted(ranges):
        if not merged_ranges:
            merged_ranges.append((start, end))
        else:
            prev_start, prev_end = merged_ranges[-1]
            if start <= prev_end:
                merged_ranges[-1] = (prev_start, max(prev_end, end))
            else:
                merged_ranges.append((start, end))
                
    segments = []
    for start, end in merged_ranges:
        segments.append("\n".join(lines[start:end]))
        
    return "\n\n... [Next Matched Heading Section] ...\n\n".join(segments)[:14000]

def get_tender_summary(raw_text: str) -> str:
    """
    Isolates Scope, EMD, Dates, and Documents sections using regex,
    then uses ChatGroq to generate a clean, consolidated executive summary.
    """
    scope_text = extract_section_text_by_rules(raw_text, "scope")
    emd_text = extract_section_text_by_rules(raw_text, "emd")
    dates_text = extract_section_text_by_rules(raw_text, "dates")
    docs_text = extract_section_text_by_rules(raw_text, "documents")
    
    combined_context = (
        f"--- SCOPE OF WORK SEGMENTS ---\n{scope_text}\n\n"
        f"--- EMD / BID SECURITY SEGMENTS ---\n{emd_text}\n\n"
        f"--- CRITICAL DATE SEGMENTS ---\n{dates_text}\n\n"
        f"--- DOCUMENT REQUIREMENT SEGMENTS ---\n{docs_text}\n"
    )
    
    llm = get_llm()
    messages = [
        ("system", SUMMARIZATION_PROMPT),
        ("human", f"Please summarize the following extracted sections from the tender document:\n\n{combined_context}")
    ]
    
    try:
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        logger.error(f"Error calling Groq for summarization: {e}")
        return "Failed to extract summary due to LLM error. Please check your API configuration."

def get_timeline(raw_text: str) -> list:
    """
    Isolates date segments using regex, then uses ChatGroq to extract 
    a structured milestones list JSON.
    """
    dates_text = extract_section_text_by_rules(raw_text, "dates")
    
    llm = get_llm()
    messages = [
        ("system", TIMELINE_PROMPT),
        ("human", f"Analyze the following timeline and dates segments from the tender and extract a list of milestones:\n\n{dates_text}")
    ]
    
    try:
        response = llm.invoke(messages)
        parsed = clean_json_response(response.content)
        return parsed.get("milestones", [])
    except Exception as e:
        logger.error(f"Error calling Groq for timeline: {e}")
        return []

def get_document_checklist(raw_text: str) -> list:
    """
    Isolates document checklist segments using regex, then uses ChatGroq
    to extract a structured checklist list JSON.
    """
    docs_text = extract_section_text_by_rules(raw_text, "documents")
    
    llm = get_llm()
    messages = [
        ("system", CHECKLIST_PROMPT),
        ("human", f"Analyze the following document checklist segments and extract the list of required documents:\n\n{docs_text}")
    ]
    
    try:
        response = llm.invoke(messages)
        parsed = clean_json_response(response.content)
        return parsed.get("documents", [])
    except Exception as e:
        logger.error(f"Error calling Groq for checklist: {e}")
        return []
