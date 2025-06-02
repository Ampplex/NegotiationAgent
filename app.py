from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, TypedDict, List, Optional
import json
import asyncio
import re
from datetime import datetime
import uuid

app = FastAPI(title="Negotiation Agent API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API
class NegotiationStart(BaseModel):
    budget: int
    campaign_type: Optional[str] = "social_media"
    duration: Optional[str] = "2_weeks"

class UserResponse(BaseModel):
    session_id: str
    message: str
    current_state: Optional[Dict[str, Any]] = None

class NegotiationResponse(BaseModel):
    type: str  # "message", "options", "complete"
    content: str
    options: Optional[List[str]] = None
    state: Dict[str, Any]
    is_complete: bool = False

# Define negotiation state
class NegotiationState(TypedDict):
    messages: List[str]
    budget: int
    campaign_type: str
    duration: str
    brand_offer: int
    influencer_offer: int
    agreed_price: Optional[int]
    negotiation_phase: str
    negotiation_rounds: int
    user_input: str
    session_id: str
    created_at: str
    last_activity: str

# Store active sessions
active_sessions: Dict[str, Dict[str, Any]] = {}

def create_session_id() -> str:
    return str(uuid.uuid4())

async def stream_message(content: str, delay: float = 0.03):
    """Stream message character by character"""
    for char in content:
        yield f"data: {json.dumps({'type': 'stream', 'content': char})}\n\n"
        await asyncio.sleep(delay)

def brand_initial_offer(state: NegotiationState) -> Dict[str, Any]:
    """Brand makes initial offer"""
    budget = state.get("budget")
    campaign_type = state.get("campaign_type", "social media")
    duration = state.get("duration", "2 weeks")
    
    if not budget:
        raise ValueError("Missing budget in state")
    
    # Format campaign type for display
    campaign_display = campaign_type.replace("_", " ").title()
    duration_display = duration.replace("_", " ").title()
    
    response = f"🏢 Brand: Hello! We're excited to work with you on our {campaign_display} campaign.\n🏢 Brand: This is a {duration_display} campaign, and our budget is ₹{budget:,}.\n🏢 Brand: What are your thoughts on this collaboration?"
    
    return {
        "messages": [f"Brand offers ₹{budget:,} for {campaign_display} campaign ({duration_display})"],
        "brand_offer": budget,
        "negotiation_phase": "waiting_for_influencer_response",
        "negotiation_rounds": state.get("negotiation_rounds", 0) + 1,
        "bot_response": response,
        "options": ["Accept the offer", "Counter with your price", "Ask about campaign details"],
        "last_activity": datetime.now().isoformat()
    }

def handle_influencer_response(state: NegotiationState) -> Dict[str, Any]:
    """Handle influencer's response to brand offer"""
    brand_offer = state.get("brand_offer")
    user_input = state.get("user_input", "")
    rounds = state.get("negotiation_rounds", 0)
    
    # Parse user response
    if "accept" in user_input.lower() or "yes" in user_input.lower():
        response = f"🎭 Influencer: I accept your offer of ₹{brand_offer:,}!\n🏢 Brand: Excellent! We have a deal!"
        return {
            "messages": [f"Influencer accepts ₹{brand_offer:,}"],
            "agreed_price": brand_offer,
            "negotiation_phase": "completed",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "is_complete": True,
            "last_activity": datetime.now().isoformat()
        }
    
    # Check for counter-offer
    price_match = re.search(r'₹?(\d+)', user_input)
    if price_match:
        counter_offer = int(price_match.group(1))
        response = f"🎭 Influencer: I was thinking more along the lines of ₹{counter_offer:,}.\n🏢 Brand: Let me consider your offer..."
        return {
            "messages": [f"Influencer counters with ₹{counter_offer:,}"],
            "influencer_offer": counter_offer,
            "negotiation_phase": "brand_considering",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "last_activity": datetime.now().isoformat()
        }
    
    # Handle questions about campaign
    if any(word in user_input.lower() for word in ["campaign", "what", "about", "details", "?"]):
        campaign_type = state.get("campaign_type", "social_media").replace("_", " ")
        duration = state.get("duration", "2_weeks").replace("_", " ")
        
        response = f"🏢 Brand: This is a {campaign_type} campaign for our new product launch.\n🏢 Brand: Duration: {duration}, with authentic content in your style.\n🏢 Brand: We need 3-5 posts showcasing our product naturally.\n🏢 Brand: So, what do you think about our offer of ₹{brand_offer:,}?"
        return {
            "messages": [f"Brand explains campaign details"],
            "negotiation_phase": "waiting_for_decision",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "options": [f"Accept ₹{brand_offer:,}", "Make counter-offer", "Need more details"],
            "last_activity": datetime.now().isoformat()
        }
    
    # Default response
    response = f"🏢 Brand: I'd like to understand your position better. Are you interested in accepting ₹{brand_offer:,}, or do you have a different rate in mind?"
    return {
        "messages": [f"Brand asks for clarification"],
        "negotiation_phase": "waiting_for_decision",
        "negotiation_rounds": rounds + 1,
        "bot_response": response,
        "options": [f"Accept ₹{brand_offer:,}", "Make counter-offer"],
        "last_activity": datetime.now().isoformat()
    }

def brand_considers_counter(state: NegotiationState) -> Dict[str, Any]:
    """Brand considers influencer's counter offer"""
    influencer_offer = state.get("influencer_offer")
    budget = state.get("budget")
    rounds = state.get("negotiation_rounds", 0)
    
    if not influencer_offer or not budget:
        return {"negotiation_phase": "error"}
    
    max_budget = int(budget * 1.15)  # Brand can go 15% over initial budget
    
    if influencer_offer <= budget:
        response = f"🏢 Brand: ₹{influencer_offer:,} works perfectly for us! Let's proceed with the collaboration."
        return {
            "messages": [f"Brand accepts ₹{influencer_offer:,}"],
            "agreed_price": influencer_offer,
            "negotiation_phase": "completed",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "is_complete": True,
            "last_activity": datetime.now().isoformat()
        }
    elif influencer_offer <= max_budget:
        response = f"🏢 Brand: ₹{influencer_offer:,} is a bit higher than our initial budget, but we really like your content. We can agree to ₹{influencer_offer:,}!"
        return {
            "messages": [f"Brand accepts ₹{influencer_offer:,}"],
            "agreed_price": influencer_offer,
            "negotiation_phase": "completed",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "is_complete": True,
            "last_activity": datetime.now().isoformat()
        }
    else:
        final_offer = max_budget
        response = f"🏢 Brand: ₹{influencer_offer:,} is beyond our current budget. The highest we can go is ₹{final_offer:,}. This is our final offer."
        return {
            "messages": [f"Brand's final offer: ₹{final_offer:,}"],
            "brand_offer": final_offer,
            "negotiation_phase": "final_decision",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "options": ["Accept final offer", "Decline offer"],
            "last_activity": datetime.now().isoformat()
        }

def handle_final_decision(state: NegotiationState) -> Dict[str, Any]:
    """Handle influencer's decision on brand's final offer"""
    final_offer = state.get("brand_offer")
    user_input = state.get("user_input", "")
    rounds = state.get("negotiation_rounds", 0)
    
    if "accept" in user_input.lower() or "yes" in user_input.lower():
        response = f"🎭 Influencer: Yes, I'll accept ₹{final_offer:,}!\n🏢 Brand: Excellent! We have a deal at ₹{final_offer:,}!"
        return {
            "messages": [f"Influencer accepts final offer of ₹{final_offer:,}"],
            "agreed_price": final_offer,
            "negotiation_phase": "completed",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "is_complete": True,
            "last_activity": datetime.now().isoformat()
        }
    else:
        response = f"🎭 Influencer: I appreciate the offer, but I can't accept ₹{final_offer:,}.\n🏢 Brand: We understand. Unfortunately, we can't go higher. Thanks for considering!"
        return {
            "messages": ["Negotiation failed - no agreement reached"],
            "agreed_price": None,
            "negotiation_phase": "failed",
            "negotiation_rounds": rounds + 1,
            "bot_response": response,
            "is_complete": True,
            "last_activity": datetime.now().isoformat()
        }

def determine_next_step(state: NegotiationState) -> str:
    """Determine next step based on current state"""
    phase = state.get("negotiation_phase", "")
    user_input = state.get("user_input", "")
    
    if phase == "waiting_for_influencer_response" or phase == "waiting_for_decision":
        return "handle_response"
    elif phase == "brand_considering":
        return "brand_considers"
    elif phase == "final_decision":
        return "final_choice"
    else:
        return "handle_response"

# Simple state machine implementation
def process_negotiation_step(state: NegotiationState) -> Dict[str, Any]:
    """Process one step of negotiation"""
    phase = state.get("negotiation_phase", "initial")
    
    if phase == "initial":
        return brand_initial_offer(state)
    elif phase in ["waiting_for_influencer_response", "waiting_for_decision"]:
        return handle_influencer_response(state)
    elif phase == "brand_considering":
        return brand_considers_counter(state)
    elif phase == "final_decision":
        return handle_final_decision(state)
    else:
        return {"negotiation_phase": "error", "bot_response": "Something went wrong. Please start over."}

# API Routes
@app.post("/start-negotiation")
async def start_negotiation(request: NegotiationStart):
    """Start a new negotiation session"""
    session_id = create_session_id()
    
    # Initialize state
    initial_state: NegotiationState = {
        "messages": [],
        "budget": request.budget,
        "campaign_type": request.campaign_type,
        "duration": request.duration,
        "brand_offer": 0,
        "influencer_offer": 0,
        "agreed_price": None,
        "negotiation_phase": "initial",
        "negotiation_rounds": 0,
        "user_input": "",
        "session_id": session_id,
        "created_at": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat()
    }
    
    try:
        # Process initial step
        result = process_negotiation_step(initial_state)
        
        # Update state with result
        for key, value in result.items():
            if key != "bot_response" and key != "options":
                initial_state[key] = value
        
        # Store session
        active_sessions[session_id] = {
            "state": initial_state,
            "created_at": datetime.now().isoformat()
        }
        
        return {
            "session_id": session_id,
            "type": "message",
            "content": result.get("bot_response", ""),
            "options": result.get("options", []),
            "state": initial_state,
            "is_complete": result.get("is_complete", False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/respond")
async def respond_to_negotiation(request: UserResponse):
    """Handle user response in negotiation"""
    if request.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[request.session_id]
    current_state = session["state"]
    
    # Update state with user input
    current_state["user_input"] = request.message
    current_state["last_activity"] = datetime.now().isoformat()
    
    try:
        # Process response
        result = process_negotiation_step(current_state)
        
        # Update state with result
        for key, value in result.items():
            if key != "bot_response" and key != "options":
                current_state[key] = value
        
        return {
            "session_id": request.session_id,
            "type": "message",
            "content": result.get("bot_response", ""),
            "options": result.get("options", []),
            "state": current_state,
            "is_complete": result.get("is_complete", False)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/respond-stream")
async def respond_to_negotiation_stream(request: UserResponse):
    """Handle user response with streaming response"""
    if request.session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[request.session_id]
    current_state = session["state"]
    current_state["user_input"] = request.message
    current_state["last_activity"] = datetime.now().isoformat()
    
    async def generate_stream():
        try:
            # Process the response
            result = process_negotiation_step(current_state)
            
            # Update state with result
            for key, value in result.items():
                if key != "bot_response" and key != "options":
                    current_state[key] = value
            
            # Stream the bot response
            bot_response = result.get("bot_response", "")
            
            # Stream character by character
            async for chunk in stream_message(bot_response):
                yield chunk
            
            # Send final data
            final_data = {
                "type": "complete",
                "session_id": request.session_id,
                "options": result.get("options", []),
                "state": current_state,
                "is_complete": result.get("is_complete", False)
            }
            yield f"data: {json.dumps(final_data)}\n\n"
            
        except Exception as e:
            error_data = {"type": "error", "content": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )

@app.get("/sessions")
async def get_active_sessions():
    """Get all active sessions"""
    session_list = []
    
    for session_id, session_data in active_sessions.items():
        state = session_data["state"]
        session_info = {
            "session_id": session_id,
            "created_at": session_data["created_at"],
            "budget": state.get("budget", 0),
            "status": state.get("negotiation_phase", "unknown"),
            "last_activity": state.get("last_activity", session_data["created_at"]),
            "rounds": state.get("negotiation_rounds", 0)
        }
        session_list.append(session_info)
    
    return {"active_sessions": session_list}

@app.get("/session/{session_id}")
async def get_session_state(session_id: str):
    """Get current session state"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "state": active_sessions[session_id]["state"]
    }

@app.delete("/session/{session_id}")
async def end_session(session_id: str):
    """End a negotiation session"""
    if session_id in active_sessions:
        del active_sessions[session_id]
        return {"message": "Session ended successfully"}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "Negotiation Agent API is running", "active_sessions": len(active_sessions)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
    
    # Run command: uvicorn app:app --host 0.0.0.0 --port 3000 --reload