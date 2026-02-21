import re
from typing import Dict, Any

def clean_budget(budget_str: str) -> Dict[str, Any]:
    """Parse budget strings like '$50.00' or '$15.00 - $30.00/hr'."""
    if not budget_str or budget_str == "Unknown Budget":
        return {"budget_type": "fixed", "min": 0.0, "max": 0.0}
        
    budget_str = budget_str.lower().replace(",", "")
    
    # Extract all numbers
    numbers = [float(n) for n in re.findall(r"[\d.]+", budget_str)]
    
    is_hourly = "/hr" in budget_str or "hourly" in budget_str
    b_type = "hourly" if is_hourly else "fixed"
    
    if len(numbers) == 1:
        return {"budget_type": b_type, "min": numbers[0], "max": numbers[0]}
    elif len(numbers) >= 2:
        return {"budget_type": b_type, "min": min(numbers), "max": max(numbers)}
        
    return {"budget_type": b_type, "min": 0.0, "max": 0.0}

def normalize_proposal_status(status_str: str) -> str:
    status_str = status_str.lower()
    if "hire" in status_str: return "hired"
    if "interview" in status_str: return "interviewing"
    if "decline" in status_str or "archive" in status_str or "close" in status_str: return "archived"
    if "submit" in status_str or "active" in status_str: return "submitted"
    return "draft"

def clean_text(text: str) -> str:
    """Basic text cleanup."""
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()
