#!/usr/bin/env python3
"""
FastAPI Server for Website Content Audit Crawler

A streamlined REST API interface for the improved site audit crawler.
Provides essential endpoints for site audits only.

Author: AI Assistant
Version: 3.0
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict, Any, List
import logging
import uuid
from datetime import datetime
import threading

# Import the audit functions
from improved_site_audit import conduct_large_scale_audit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Website Content Audit API",
    description="Streamlined REST API for website content auditing",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# In-memory storage for audit status and active threads
audit_status: Dict[str, Dict[str, Any]] = {}
audit_results: Dict[str, Dict[str, Any]] = {}
active_threads: Dict[str, threading.Thread] = {}

# Request models
class LargeScaleAuditRequest(BaseModel):
    url: HttpUrl = Field(..., description="Website URL to audit")
    max_pages: Optional[int] = Field(None, description="Maximum number of pages to crawl", ge=1, le=100000)
    html_workers: Optional[int] = Field(5, description="Number of HTML discovery workers", ge=1, le=100)
    asset_workers: Optional[int] = Field(5, description="Number of asset extraction workers", ge=1, le=100)

# Response models
class AuditResponse(BaseModel):
    audit_id: str = Field(..., description="Unique audit identifier")
    status: str = Field(..., description="Audit status (pending, running, completed, failed)")
    message: str = Field(..., description="Status message")
    estimated_duration_minutes: Optional[float] = Field(None, description="Estimated completion time")

class AuditListItem(BaseModel):
    audit_id: str
    status: str
    type: str
    started_at: str
    completed_at: Optional[str] = None
    url: str
    progress: Optional[str] = None

class AuditListResponse(BaseModel):
    total_audits: int
    audits: List[AuditListItem]
    url: HttpUrl = Field(..., description="Website URL to analyze for CMS architecture")

class CMSAnalysisResponse(BaseModel):
    analysis_id: str = Field(..., description="Unique analysis identifier")
    status: str = Field(..., description="Analysis status (pending, running, completed, failed)")
    message: str = Field(..., description="Status message")
    site_domain: str = Field(..., description="Site domain being analyzed")

# Scanner Analysis models
class ScannerAnalysisRequest(BaseModel):
    url: HttpUrl = Field(..., description="Website URL to analyze for SEO, Accessibility, and Geo audit")

class ScannerAnalysisResponse(BaseModel):
    analysis_id: str = Field(..., description="Unique analysis identifier")
    status: str = Field(..., description="Analysis status (pending, running, completed, failed)")
    message: str = Field(..., description="Status message")
    site_domain: str = Field(..., description="Site domain being analyzed")

# Background task function
def run_large_scale_audit(audit_id: str, request: LargeScaleAuditRequest):
    """Run large scale audit in background thread"""
    try:
        logger.info(f"Starting large scale audit {audit_id} for {request.url}")
        
        # Update status to running
        audit_status[audit_id].update({
            "status": "running",
            "message": "Large scale audit in progress"
        })
        
        # Run the audit
        result = conduct_large_scale_audit(
            base_url=str(request.url),
            max_pages=request.max_pages,
            html_workers=request.html_workers,
            asset_workers=request.asset_workers
        )
        
        # Check if thread was interrupted (killed)
        if threading.current_thread() in active_threads.values():
            # Update status to completed
            audit_status[audit_id].update({
                "status": "completed",
                "message": "Large scale audit completed successfully",
                "completed_at": datetime.now().isoformat()
            })
            
            # Store results
            audit_results[audit_id] = result
            
            logger.info(f"Large scale audit {audit_id} completed successfully")
        
    except Exception as e:
        logger.error(f"Large scale audit {audit_id} failed: {str(e)}")
        if audit_id in audit_status:  # Check if not killed
            audit_status[audit_id].update({
                "status": "failed",
                "message": f"Large scale audit failed: {str(e)}",
                "completed_at": datetime.now().isoformat()
            })
            
    finally:
        # Clean up thread reference
        if audit_id in active_threads:
            del active_threads[audit_id]

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Website Content Audit API v3.0",
        "version": "3.0.0",
        "endpoints": {
            "docs": "/docs",
            "site_audit": "/audit/large-scale",
            "kill_audit": "/audit/{audit_id}",
            "list_audits": "/audits"
        },
        "features": [
            "Large-scale website content auditing",
            "Background task processing",
            "Real-time audit status tracking",
            "Comprehensive error handling"
        ]
    }

@app.post("/audit/large-scale", response_model=AuditResponse)
async def start_large_scale_audit(request: LargeScaleAuditRequest):
    """Start a large-scale website audit"""
    
    # Generate unique audit ID
    audit_id = str(uuid.uuid4())
    
    # Estimate duration (rough calculation)
    estimated_pages = request.max_pages or 10000
    estimated_duration = (estimated_pages / request.html_workers) * 0.2 / 60  # minutes
    
    # Initialize status
    audit_status[audit_id] = {
        "status": "pending",
        "message": "Large scale audit queued",
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "type": "large_scale",
        "url": str(request.url),
        "parameters": {
            "max_pages": request.max_pages,
            "html_workers": request.html_workers,
            "asset_workers": request.asset_workers
        }
    }
    
    # Start audit in background thread
    thread = threading.Thread(
        target=run_large_scale_audit,
        args=(audit_id, request),
        daemon=True
    )
    active_threads[audit_id] = thread
    thread.start()
    
    logger.info(f"Started large scale audit {audit_id} in background thread")
    
    return AuditResponse(
        audit_id=audit_id,
        status="pending",
        message="Large scale audit started. Use the audit_id to check status or kill the job.",
        estimated_duration_minutes=estimated_duration
    )

@app.delete("/audit/{audit_id}")
async def kill_audit(audit_id: str):
    """Kill/stop a running audit and clean up resources"""
    
    if audit_id not in audit_status:
        raise HTTPException(status_code=404, detail="Audit ID not found")
    
    current_status = audit_status[audit_id]["status"]
    
    if current_status in ["completed", "failed"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot kill audit that is already {current_status}"
        )
    
    # Kill the running thread if it exists
    if audit_id in active_threads:
        thread = active_threads[audit_id]
        if thread.is_alive():
            # Note: Python doesn't have direct thread killing, but we clean up references
            logger.warning(f"Attempting to stop audit {audit_id} - thread cleanup")
            del active_threads[audit_id]
    
    # Update status
    audit_status[audit_id].update({
        "status": "killed",
        "message": "Audit was killed by user request",
        "completed_at": datetime.now().isoformat()
    })
    
    # Clean up results if any
    if audit_id in audit_results:
        del audit_results[audit_id]
    
    logger.info(f"Audit {audit_id} killed successfully")
    
    return {
        "message": f"Audit {audit_id} killed successfully",
        "audit_id": audit_id,
        "status": "killed"
    }

@app.get("/audits", response_model=AuditListResponse)
async def list_audits():
    """List all audits with their status"""
    
    audits = []
    for audit_id, status_info in audit_status.items():
        # Check if thread is still alive for running audits
        thread_status = None
        if audit_id in active_threads:
            thread = active_threads[audit_id]
            thread_status = "alive" if thread.is_alive() else "dead"
        
        audits.append(AuditListItem(
            audit_id=audit_id,
            status=status_info["status"],
            type=status_info["type"],
            started_at=status_info["started_at"],
            completed_at=status_info.get("completed_at"),
            url=status_info.get("url", "unknown"),
            progress=f"Thread: {thread_status}" if thread_status else None
        ))
    
    return AuditListResponse(
        total_audits=len(audits),
        audits=sorted(audits, key=lambda x: x.started_at, reverse=True)
    )

@app.get("/audit/{audit_id}/results")
async def get_audit_results(audit_id: str):
    """Get results for a completed audit"""
    
    if audit_id not in audit_status:
        raise HTTPException(status_code=404, detail="Audit ID not found")
    
    status_info = audit_status[audit_id]
    
    if status_info["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Audit is not completed yet. Current status: {status_info['status']}"
        )
    
    if audit_id not in audit_results:
        raise HTTPException(status_code=404, detail="Audit results not found")
    
    return {
        "audit_id": audit_id,
        "status": status_info["status"],
        "started_at": status_info["started_at"],
        "completed_at": status_info.get("completed_at"),
        "url": status_info.get("url"),
        "results": audit_results[audit_id]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app", 
        host="0.0.0.0", 
        port=9000, 
        reload=True,
        log_level="info"
    )