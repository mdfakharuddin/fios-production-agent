from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from core.memory_retriever import MemoryRetriever
from agents.opportunity_agent import OpportunityAgent

router = APIRouter()
opportunity_agent = OpportunityAgent()
memory_retriever = MemoryRetriever()

class JobAnalyzeRequest(BaseModel):
    user_id: str
    job_data: Dict[str, Any]

class JobAnalyzeResponse(BaseModel):
    win_probability: int
    strategic_fit_score: int
    recommendation: str
    suggested_hook: str
    analysis_details: Dict[str, Any]

@router.post("/analyze", response_model=JobAnalyzeResponse)
async def analyze_job_endpoint(request: JobAnalyzeRequest):
    try:
        # 1. Retrieve memory context (skills, niches, past winning proposals)
        memory_context = await memory_retriever.retrieve_relevant_context(
            user_id=request.user_id,
            query=request.job_data.get("description", ""),
            top_k=3
        )
        
        # 2. Run opportunity scanner
        result = await opportunity_agent.analyze_job(
            job_data=request.job_data,
            memory_context=memory_context
        )
        
        return JobAnalyzeResponse(
            win_probability=result["win_probability"],
            strategic_fit_score=result["strategic_fit_score"],
            recommendation=result["recommendation"],
            suggested_hook=result["suggested_hook"],
            analysis_details=result["analysis_details"]
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
