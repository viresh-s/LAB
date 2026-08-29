from app.graph.state import OrchestratorState

def route_event(state: OrchestratorState) -> str:
    """
    LangGraph Conditional Edge.
    This acts as the master switchboard for your entire SaaS. 
    When the FastAPI server triggers the graph, this function reads the 
    event_type and sends the state to the correct subgraph.
    """
    event = state.get("event_type")
    
    if event == "voice_call":
        # Route to the first node of the Voice Box
        return "extract_voice_data"
        
    elif event == "whatsapp_walkin":
        # Route to the Walk-in Box
        return "extract_walkin"
        
    elif event == "whatsapp_collector":
        # Route to the Collector Box
        return "extract_collector_update"
        
    elif event == "pdf_upload" or event == "whatsapp_payment":
        # Route to the Payment/Report Box
        return "process_payment_or_report"
        
    # Fallback if unknown event
    return "end"