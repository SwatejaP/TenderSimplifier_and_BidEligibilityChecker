import json
import logging
from section_extractor import get_llm, clean_json_response, extract_section_text_by_rules
from prompts import CRITERIA_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

def extract_tender_criteria(raw_text: str) -> dict:
    """
    Isolates the eligibility section via rules, then queries Groq/Llama3
    to extract eligibility parameters (turnover, experience, certifications, exemptions).
    """
    # 1. Isolate the eligibility text segment first using heading rules
    eligibility_text = extract_section_text_by_rules(raw_text, "eligibility")
    
    # If the rule-based extractor was empty, fall back to the entire text
    if not eligibility_text.strip():
        logger.warning("Rules-based eligibility extraction returned empty text. Falling back to full text.")
        eligibility_context = raw_text[:20000] # Grab first 20k characters
    else:
        eligibility_context = eligibility_text

    # 2. Query ChatGroq to extract parameters
    llm = get_llm()
    messages = [
        ("system", CRITERIA_EXTRACTION_PROMPT),
        ("human", f"Analyze this eligibility text and extract the parameters in JSON:\n\n{eligibility_context}")
    ]
    
    criteria = {}
    try:
        response = llm.invoke(messages)
        criteria = clean_json_response(response.content)
    except Exception as e:
        logger.error(f"Error calling Groq for criteria extraction: {e}")
        
    # Provide robust default keys in case extraction missed them
    default_criteria = {
        "min_turnover_inr": None,
        "min_experience_years": None,
        "required_certifications": [],
        "msme_exempt_turnover": False,
        "msme_exempt_experience": False,
        "msme_exempt_emd": False,
        "explanation_turnover": "Not specified in tender.",
        "explanation_experience": "Not specified in tender.",
        "explanation_certifications": "Not specified in tender.",
        "explanation_msme": "Not specified in tender."
    }
    
    for k, v in default_criteria.items():
        if k not in criteria:
            criteria[k] = v
            
    return criteria

def evaluate_vendor_eligibility(vendor_profile: dict, criteria: dict) -> dict:
    """
    Evaluates vendor profile inputs against the extracted tender criteria.
    Executes entirely in Python (no LLM hallucination risk).
    
    Args:
        vendor_profile: dict containing keys:
            - name: str
            - turnover: float (absolute INR)
            - experience: int (years)
            - certifications: list of strings
            - msme_status: bool
        criteria: dict containing extracted parameters from tender.
    """
    results = {}
    is_msme = vendor_profile.get("msme_status", False)
    
    # 1. Turnover Assessment
    req_turnover = criteria.get("min_turnover_inr")
    vendor_turnover = vendor_profile.get("turnover", 0.0)
    
    if req_turnover is None or req_turnover == 0:
        results["turnover"] = {
            "status": "PASS",
            "message": "No minimum turnover requirement specified in the tender.",
            "required": "N/A",
            "vendor": f"INR {vendor_turnover:,.2f}",
            "details": criteria.get("explanation_turnover", "")
        }
    else:
        # Check MSME exemptions
        exempt = criteria.get("msme_exempt_turnover", False)
        if is_msme and exempt:
            results["turnover"] = {
                "status": "PASS",
                "message": "Exempted from turnover requirement due to MSME status.",
                "required": f"INR {req_turnover:,.2f} (Exempted for MSME)",
                "vendor": f"INR {vendor_turnover:,.2f}",
                "details": criteria.get("explanation_turnover", "") + " (MSME exemption active)"
            }
        else:
            if vendor_turnover >= req_turnover:
                results["turnover"] = {
                    "status": "PASS",
                    "message": "Vendor turnover meets or exceeds the required threshold.",
                    "required": f"INR {req_turnover:,.2f}",
                    "vendor": f"INR {vendor_turnover:,.2f}",
                    "details": criteria.get("explanation_turnover", "")
                }
            else:
                results["turnover"] = {
                    "status": "FAIL",
                    "message": "Vendor turnover is below the required threshold.",
                    "required": f"INR {req_turnover:,.2f}",
                    "vendor": f"INR {vendor_turnover:,.2f}",
                    "details": criteria.get("explanation_turnover", "")
                }
                
    # 2. Experience Assessment
    req_experience = criteria.get("min_experience_years")
    vendor_experience = vendor_profile.get("experience", 0)
    
    if req_experience is None or req_experience == 0:
        results["experience"] = {
            "status": "PASS",
            "message": "No minimum experience requirement specified in the tender.",
            "required": "N/A",
            "vendor": f"{vendor_experience} years",
            "details": criteria.get("explanation_experience", "")
        }
    else:
        # Check MSME exemptions
        exempt = criteria.get("msme_exempt_experience", False)
        if is_msme and exempt:
            results["experience"] = {
                "status": "PASS",
                "message": "Exempted from experience requirement due to MSME status.",
                "required": f"{req_experience} years (Exempted for MSME)",
                "vendor": f"{vendor_experience} years",
                "details": criteria.get("explanation_experience", "") + " (MSME exemption active)"
            }
        else:
            if vendor_experience >= req_experience:
                results["experience"] = {
                    "status": "PASS",
                    "message": "Vendor experience meets or exceeds the required duration.",
                    "required": f"{req_experience} years",
                    "vendor": f"{vendor_experience} years",
                    "details": criteria.get("explanation_experience", "")
                }
            else:
                results["experience"] = {
                    "status": "FAIL",
                    "message": "Vendor experience is below the required duration.",
                    "required": f"{req_experience} years",
                    "vendor": f"{vendor_experience} years",
                    "details": criteria.get("explanation_experience", "")
                }

    # 3. Certifications Assessment
    req_certs = criteria.get("required_certifications", [])
    vendor_certs_raw = vendor_profile.get("certifications", [])
    vendor_certs = [c.strip().lower() for c in vendor_certs_raw if c.strip()]
    
    cert_results = []
    missing_certs = []
    
    for rc in req_certs:
        rc_clean = rc.strip().lower()
        found = False
        for vc in vendor_certs:
            if rc_clean in vc or vc in rc_clean:
                found = True
                break
        if found:
            cert_results.append({"certification": rc, "status": "PASS"})
        else:
            cert_results.append({"certification": rc, "status": "FAIL"})
            missing_certs.append(rc)
            
    if not req_certs:
        results["certifications"] = {
            "status": "PASS",
            "message": "No specific certifications required in the tender.",
            "required": "N/A",
            "vendor": ", ".join(vendor_certs_raw) if vendor_certs_raw else "None",
            "details": criteria.get("explanation_certifications", ""),
            "items": []
        }
    elif not missing_certs:
        results["certifications"] = {
            "status": "PASS",
            "message": "Vendor possesses all required certifications.",
            "required": ", ".join(req_certs),
            "vendor": ", ".join(vendor_certs_raw),
            "details": criteria.get("explanation_certifications", ""),
            "items": cert_results
        }
    else:
        results["certifications"] = {
            "status": "FAIL",
            "message": f"Vendor is missing required certifications: {', '.join(missing_certs)}",
            "required": ", ".join(req_certs),
            "vendor": ", ".join(vendor_certs_raw) if vendor_certs_raw else "None",
            "details": criteria.get("explanation_certifications", ""),
            "items": cert_results
        }

    # 4. EMD Exemption assessment (For record and display)
    emd_exempt = criteria.get("msme_exempt_emd", False)
    results["emd_exemption"] = {
        "status": "INFO",
        "message": "MSME/NSIC bidders are exempted from EMD payment." if emd_exempt else "No EMD exemption mentioned for MSMEs.",
        "exempt": emd_exempt,
        "details": criteria.get("explanation_msme", "")
    }

    # Verify overall eligibility status
    is_eligible = True
    for key in ["turnover", "experience", "certifications"]:
        if results[key]["status"] == "FAIL":
            is_eligible = False
            break
            
    results["eligible"] = is_eligible
    
    return results
