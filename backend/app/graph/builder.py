# backend/app/graph/builder.py
from langgraph.graph import StateGraph, START, END
from app.graph.state import OrchestratorState

# ── Voice nodes ──────────────────────────────────────────────────────────────
from app.graph.nodes.voice import (
    extract_voice_data, 
    check_missing_fields, 
    ask_user, 
    db_insert_booking
)

# ── Walk-in nodes ────────────────────────────────────────────────────────────
from app.graph.nodes.walkin import (
    extract_walkin_data,
    db_insert_walkin_booking,
)

# ── Collector update nodes ───────────────────────────────────────────────────
from app.graph.nodes.collector import (
    extract_collector_data,
    db_update_sample,
)

# ── Payment & Report nodes ───────────────────────────────────────────────────
from app.graph.nodes.report import (
    extract_payment,
    db_update_paid,
    db_update_report_link,
    check_and_dispatch,
    wa_dispatch_report,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Voice call graph (existing — unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def create_voice_graph():
    builder = StateGraph(OrchestratorState)

    builder.add_node("extract_voice_data", extract_voice_data)
    builder.add_node("ask_user", ask_user)
    builder.add_node("db_insert_booking", db_insert_booking)

    builder.add_edge(START, "extract_voice_data")
    
    builder.add_conditional_edges(
        "extract_voice_data",
        check_missing_fields,
        {
            "ask_user": "ask_user",
            "db_insert_booking": "db_insert_booking"
        }
    )

    builder.add_edge("ask_user", END) 
    builder.add_edge("db_insert_booking", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Walk-in booking graph
#    Flow: extract_walkin_data → db_insert_walkin_booking → END
# ─────────────────────────────────────────────────────────────────────────────
def create_walkin_graph():
    builder = StateGraph(OrchestratorState)

    builder.add_node("extract_walkin_data", extract_walkin_data)
    builder.add_node("db_insert_walkin_booking", db_insert_walkin_booking)

    builder.add_edge(START, "extract_walkin_data")
    builder.add_edge("extract_walkin_data", "db_insert_walkin_booking")
    builder.add_edge("db_insert_walkin_booking", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Collector update graph
#    Flow: extract_collector_data → db_update_sample → END
# ─────────────────────────────────────────────────────────────────────────────
def create_collector_graph():
    builder = StateGraph(OrchestratorState)

    builder.add_node("extract_collector_data", extract_collector_data)
    builder.add_node("db_update_sample", db_update_sample)

    builder.add_edge(START, "extract_collector_data")
    builder.add_edge("extract_collector_data", "db_update_sample")
    builder.add_edge("db_update_sample", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Payment confirmation graph
#    Flow: extract_payment → db_update_paid → check_and_dispatch
#            → wa_dispatch_report → END  (if paid + report available)
#            → END                       (if report not ready yet)
# ─────────────────────────────────────────────────────────────────────────────
def create_payment_graph():
    builder = StateGraph(OrchestratorState)

    builder.add_node("extract_payment", extract_payment)
    builder.add_node("db_update_paid", db_update_paid)
    builder.add_node("wa_dispatch_report", wa_dispatch_report)

    builder.add_edge(START, "extract_payment")
    builder.add_edge("extract_payment", "db_update_paid")

    builder.add_conditional_edges(
        "db_update_paid",
        check_and_dispatch,
        {
            "wa_dispatch_report": "wa_dispatch_report",
            "end": END,
        }
    )

    builder.add_edge("wa_dispatch_report", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Report upload graph
#    Flow: db_update_report_link → check_and_dispatch
#            → wa_dispatch_report → END  (if paid + report available)
#            → END                       (if payment not done)
# ─────────────────────────────────────────────────────────────────────────────
def create_report_upload_graph():
    builder = StateGraph(OrchestratorState)

    builder.add_node("db_update_report_link", db_update_report_link)
    builder.add_node("wa_dispatch_report", wa_dispatch_report)

    builder.add_edge(START, "db_update_report_link")

    builder.add_conditional_edges(
        "db_update_report_link",
        check_and_dispatch,
        {
            "wa_dispatch_report": "wa_dispatch_report",
            "end": END,
        }
    )

    builder.add_edge("wa_dispatch_report", END)

    return builder.compile()