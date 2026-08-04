import streamlit as st
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


from orchestrator.master import handle, get_health_monitor, get_pipeline
from scheduler.background import get_notifications, mark_all_read
from voice.voice_handler import speak, listen
from database.tracker import save_chat_message, load_chat_history, clear_chat_history, create_chat_session, get_chat_sessions, delete_chat_session, get_tasks, get_projects


# ─── Cached DB Queries ─────────────────────────────────────────────
# Wrapped with st.cache_data so they don't re-query on every Streamlit re-render.

@st.cache_data(ttl=30)
def _cached_active_tasks():
    return get_tasks(status="todo")[:3]


@st.cache_data(ttl=30)
def _cached_active_projects():
    return get_projects(status="active")[:3]

st.set_page_config(page_title="Aaqil AI", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# --- Custom Styling ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp { background-color: #0f1117; color: #e2e8f0; }
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1d27 0%, #12141c 100%);
        border-right: 1px solid #2d3748;
    }
    .sidebar-title {
        font-size: 1.6rem; font-weight: 800;
        background: linear-gradient(135deg, #818cf8, #c084fc);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.1rem;
    }
    .sidebar-subtitle {
        font-size: 0.8rem; color: #64748b; margin-bottom: 1.5rem;
        letter-spacing: 0.05em; text-transform: uppercase;
    }

    .status-dot {
        height: 8px; width: 8px; border-radius: 50%;
        display: inline-block; margin-right: 8px; flex-shrink: 0;
    }
    .status-idle     { background-color: #10b981; box-shadow: 0 0 4px #10b981; }
    .status-processing { background-color: #f59e0b; box-shadow: 0 0 4px #f59e0b; animation: pulse 1s infinite; }
    .status-error    { background-color: #ef4444; box-shadow: 0 0 4px #ef4444; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

    .agent-row {
        display: flex; align-items: center; padding: 7px 10px; border-radius: 8px;
        margin-bottom: 3px; background: rgba(255,255,255,0.03);
        font-size: 0.82rem; font-weight: 500; color: #cbd5e1;
        border: 1px solid transparent; transition: all 0.2s;
    }
    .agent-row:hover { background: rgba(255,255,255,0.06); border-color: #2d3748; }
    .agent-name { flex: 1; }
    .agent-meta { margin-left: auto; text-align: right; }
    .agent-time { font-size: 0.7rem; color: #475569; display: block; }
    .agent-rate { font-size: 0.65rem; color: #10b981; display: block; }

    .chat-container { padding-bottom: 120px; }

    .agent-badge {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 3px 10px; border-radius: 9999px;
        font-size: 0.7rem; font-weight: 700;
        text-transform: uppercase; letter-spacing: 0.08em;
        background: linear-gradient(135deg, #6366f1, #8b5cf6);
        color: white; margin-bottom: 6px;
        box-shadow: 0 2px 8px rgba(99,102,241,0.3);
    }

    .stButton > button {
        width: 100%; border-radius: 8px; border: 1px solid #2d3748;
        background: rgba(255,255,255,0.03); color: #94a3b8;
        font-size: 0.8rem; font-weight: 600; padding: 6px 8px;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        border-color: #6366f1; color: #a5b4fc;
        background: rgba(99,102,241,0.1); transform: translateY(-1px);
    }

    .notification-box {
        background: rgba(59,130,246,0.08); border-left: 3px solid #3b82f6;
        padding: 10px 14px; margin-bottom: 10px; border-radius: 0 8px 8px 0;
    }
    .notification-time { font-size: 0.7rem; color: #60a5fa; font-weight: 600; }

    .example-grid {
        display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 1.5rem;
    }
    .example-card {
        background: rgba(255,255,255,0.03); border: 1px solid #2d3748;
        border-radius: 12px; padding: 14px 16px; cursor: pointer; transition: all 0.2s;
    }
    .example-card:hover {
        background: rgba(99,102,241,0.08); border-color: #6366f1; transform: translateY(-2px);
    }
    .example-icon { font-size: 1.4rem; margin-bottom: 6px; }
    .example-title { font-weight: 600; font-size: 0.85rem; color: #e2e8f0; margin-bottom: 3px; }
    .example-cmd { font-size: 0.75rem; color: #64748b; font-family: monospace; }

    .workspace-header { font-size: 1.1rem; font-weight: 700; color: #e2e8f0; letter-spacing: -0.01em; }
    .stChatMessage p, .stChatMessage div, .stChatMessage span, .stChatMessage li, .stChatMessage h1, .stChatMessage h2, .stChatMessage h3 { color: #f8fafc !important; font-size: 0.95rem; line-height: 1.5; }
    .stChatMessage { color: #f8fafc !important; }
    .stMarkdown, .stMarkdown p, .stMarkdown li { color: #f8fafc !important; }
</style>
""", unsafe_allow_html=True)


# --- Session State ---
if "current_session_id" not in st.session_state:
    sessions = get_chat_sessions()
    if sessions:
        st.session_state.current_session_id = sessions[0]["id"]
        st.session_state.history = load_chat_history(sessions[0]["id"])
    else:
        st.session_state.current_session_id = None
        st.session_state.history = []
if "history" not in st.session_state:
    st.session_state.history = []
if "pending_quick" not in st.session_state:
    st.session_state.pending_quick = None
if "pending_voice" not in st.session_state:
    st.session_state.pending_voice = None
if "show_notifications" not in st.session_state:
    st.session_state.show_notifications = False


# --- Sidebar ---
with st.sidebar:
    st.markdown('<div class="sidebar-title">⚡ Aaqil AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-subtitle">Multi-Agent Orchestrator</div>', unsafe_allow_html=True)

    st.markdown("### 📊 System Diagnostics")
    health_monitor = get_health_monitor()
    stats = health_monitor.get_all_stats()

    core_agents = [
        "orchestrator", "project_manager", "job", "github", "linkedin",
        "career", "growth", "research", "email", "briefing", "info"
    ]

    for agent in core_agents:
        data = stats.get(agent, {"status": "idle", "last_active_str": "Never",
                                  "total_tasks": 0, "success_rate": None})
        status_class = f"status-{data['status']}"
        rate_str = f"{data['success_rate']}% success" if data.get("success_rate") is not None else ""
        st.markdown(f"""
            <div class="agent-row">
                <span class="status-dot {status_class}"></span>
                <span class="agent-name">{agent.replace('_', ' ').title()}</span>
                <span class="agent-meta">
                    <span class="agent-time">{data['last_active_str']}</span>
                    <span class="agent-rate">{rate_str}</span>
                </span>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    st.markdown("### 🚀 Quick Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🌅 Briefing", use_container_width=True):  st.session_state.pending_quick = "generate morning briefing"
        if st.button("💼 Find Jobs", use_container_width=True): st.session_state.pending_quick = "find software engineering jobs"
        if st.button("📝 Draft Post", use_container_width=True):st.session_state.pending_quick = "draft a linkedin post about AI"
    with col2:
        if st.button("📚 Research", use_container_width=True):  st.session_state.pending_quick = "write paper about LLM agents"
        if st.button("🎯 Int Prep", use_container_width=True):  st.session_state.pending_quick = "interview prep for Google SDE"
        if st.button("🐙 Sync Git", use_container_width=True):  st.session_state.pending_quick = "sync my github activity"

    st.divider()
    st.markdown("### 💬 Chat Sessions")
    sc1, sc2 = st.columns([4, 1])
    with sc1:
        if st.button("➕ New Chat", use_container_width=True, type="primary"):
            st.session_state.current_session_id = None
            st.session_state.history = []
            st.rerun()
    with sc2:
        if st.button("🗑️", help="Delete ALL chats"):
            clear_chat_history()
            st.session_state.current_session_id = None
            st.session_state.history = []
            st.rerun()

    sessions = get_chat_sessions()
    for sess in sessions:
        r1, r2 = st.columns([5, 1])
        with r1:
            if st.button(f"💬 {sess['title'][:20]}", key=f"s_{sess['id']}", use_container_width=True):
                st.session_state.current_session_id = sess['id']
                st.session_state.history = load_chat_history(sess['id'])
                st.rerun()
        with r2:
            if st.button("❌", key=f"d_{sess['id']}"):
                delete_chat_session(sess['id'])
                if st.session_state.current_session_id == sess['id']:
                    st.session_state.current_session_id = None
                    st.session_state.history = []
                st.rerun()

    st.divider()

    st.markdown("### 🧠 AI Model")
    selected_model = st.selectbox(
        "Select Generation Model",
        ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "mixtral-8x7b-32768", "gemma2-9b-it"],
        index=0,
        label_visibility="collapsed"
    )
    os.environ["SELECTED_SMART_MODEL"] = selected_model

    st.divider()
    
    st.markdown("### ℹ️ Info Mode")
    info_mode = st.toggle("Talk to InfoAgent", value=False, help="Isolate chat to only talk to the system documentation agent.")
    
    st.divider()

    st.markdown("### 🎙️ Voice Input")
    voice_enabled = st.toggle("Enable Voice Output", value=False)
    if st.button("🎤 Tap to Speak", use_container_width=True):
        with st.spinner("Listening..."):
            spoken = listen()
        if spoken:
            st.session_state.pending_voice = spoken
        else:
            st.warning("Could not hear you. Try again.")

    st.divider()

    if voice_enabled:
        st.write("Voice mode active")


# --- Main Layout ---
pipeline = get_pipeline()
notifications = get_notifications()
unread = [n for n in notifications if not n["read"]]

header_col1, header_col2, header_col3 = st.columns([6, 1, 1])
with header_col1:
    st.markdown('<div class="workspace-header">⚡ Workspace</div>', unsafe_allow_html=True)
with header_col2:
    approvals = pipeline.get_pending_approvals()
    if approvals:
        if st.button(f"⚠️ {len(approvals)} Pending"):
            st.session_state.show_approvals = True
with header_col3:
    notif_label = f"🔔 {len(unread)}" if unread else "🔔 0"
    if st.button(notif_label):
        st.session_state.show_notifications = not st.session_state.show_notifications
        mark_all_read()

st.divider()

# Notifications Panel
if st.session_state.show_notifications:
    st.markdown("### Recent Notifications")
    if not notifications:
        st.info("No notifications yet.")
    for n in notifications[-5:][::-1]:
        st.markdown(f"""
            <div class="notification-box">
                <div class="notification-time">{n['time']}</div>
                <div>{n['message']}</div>
            </div>
        """, unsafe_allow_html=True)
    if st.button("Hide Notifications"):
        st.session_state.show_notifications = False
        st.rerun()
    st.divider()

# Approvals Panel
if approvals:
    st.markdown("### 📋 Action Approvals Required")
    for a in approvals:
        with st.expander(f"[{a['id']}] {a['title']} ({a['type'].upper()})", expanded=True):
            st.text_area("Content Preview", a["content"], height=180,
                         key=f"preview_{a['id']}", disabled=True)
            ac1, ac2 = st.columns(2)
            with ac1:
                if st.button("✅ Approve Action", key=f"app_{a['id']}", type="primary"):
                    st.success(pipeline.approve(a["id"]))
                    st.rerun()
            with ac2:
                if st.button("❌ Reject Action", key=f"rej_{a['id']}"):
                    st.error(pipeline.reject(a["id"]))
                    st.rerun()
    st.divider()


# --- Agent Icons ---
agent_icons = {
    "github": "🐙", "linkedin": "💼", "job": "🔍",
    "project_manager": "📋", "career": "🎓", "growth": "📈",
    "research": "📚", "email": "📧", "briefing": "🌅",
    "orchestrator": "⚡", "pipeline": "⚙️", "info": "ℹ️"
}


# --- Chat Interface ---
st.markdown('<div class="chat-container">', unsafe_allow_html=True)

if not st.session_state.history:
    active_tasks = _cached_active_tasks()
    active_projects = _cached_active_projects()
    
    st.markdown("""
        <div style="padding: 1rem 0 2rem;">
            <h2 style="color: #f8fafc; font-weight: 800; margin-bottom: 0.2rem; font-size: 2.2rem; letter-spacing: -0.02em;">System Dashboard</h2>
            <p style="color: #94a3b8; font-size: 0.95rem;">Real-time overview of active agents, projects, and priority tasks.</p>
        </div>
    """, unsafe_allow_html=True)
    
    dcol1, dcol2, dcol3 = st.columns([1.2, 1.2, 1])
    
    with dcol1:
        st.markdown("<h3 style='color: #e2e8f0; font-size: 1.1rem; margin-bottom: 1rem;'>📋 Priority Tasks</h3>", unsafe_allow_html=True)
        if not active_tasks:
            st.info("No pending tasks. You're all caught up!")
        for t in active_tasks:
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 14px 16px; border-radius: 12px; margin-bottom: 12px; backdrop-filter: blur(10px); transition: transform 0.2s;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <strong style="color: #f8fafc; font-size: 0.95rem;">{t['title']}</strong>
                    <span style="background: rgba(245, 158, 11, 0.15); color: #fcd34d; font-size: 0.65rem; padding: 3px 8px; border-radius: 12px; font-weight: 700; letter-spacing: 0.05em;">{t['priority'].upper()}</span>
                </div>
                <div style="color: #64748b; font-size: 0.8rem;">Project: <span style="color: #94a3b8;">{t.get('project_name', 'None')}</span></div>
            </div>
            """, unsafe_allow_html=True)
            
    with dcol2:
        st.markdown("<h3 style='color: #e2e8f0; font-size: 1.1rem; margin-bottom: 1rem;'>🚀 Active Projects</h3>", unsafe_allow_html=True)
        if not active_projects:
            st.info("No active projects.")
        for p in active_projects:
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 14px 16px; border-radius: 12px; margin-bottom: 12px; backdrop-filter: blur(10px);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <strong style="color: #f8fafc; font-size: 0.95rem;">{p['name']}</strong>
                    <span style="color: #a5b4fc; font-size: 0.75rem; font-weight: 600;">{p['progress']}%</span>
                </div>
                <div style="background: rgba(0,0,0,0.3); border-radius: 8px; height: 6px; overflow: hidden;">
                    <div style="width: {p['progress']}%; background: linear-gradient(90deg, #4f46e5, #ec4899); height: 100%; border-radius: 8px;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    with dcol3:
        st.markdown("<h3 style='color: #e2e8f0; font-size: 1.1rem; margin-bottom: 1rem;'>🧠 Agent Status</h3>", unsafe_allow_html=True)
        total_agents = len(core_agents)
        active_agents = sum(1 for a in core_agents if stats.get(a, {}).get("status") != "idle")
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(79, 70, 229, 0.15), rgba(236, 72, 153, 0.15)); border: 1px solid rgba(99, 102, 241, 0.3); padding: 24px; border-radius: 16px; backdrop-filter: blur(12px); text-align: center; margin-bottom: 16px; box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.1);">
            <div style="font-size: 3rem; margin-bottom: 12px; filter: drop-shadow(0 0 10px rgba(99, 102, 241, 0.4));">⚡</div>
            <h3 style="color: #f8fafc; margin: 0 0 4px 0; font-size: 2rem; font-weight: 800;">{active_agents} <span style="font-size:1.2rem; color:#94a3b8; font-weight:600;">/ {total_agents}</span></h3>
            <p style="color: #a5b4fc; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin: 0;">Agents Active</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); padding: 14px 16px; border-radius: 12px; font-size: 0.85rem; color: #cbd5e1; backdrop-filter: blur(8px);">
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="height:8px; width:8px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981; margin-right:10px;"></span> 
                <span style="flex:1;">System Core</span>
                <span style="color:#10b981; font-weight:600; font-size:0.7rem;">ONLINE</span>
            </div>
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
                <span style="height:8px; width:8px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981; margin-right:10px;"></span> 
                <span style="flex:1;">Vector DB</span>
                <span style="color:#10b981; font-weight:600; font-size:0.7rem;">CONNECTED</span>
            </div>
            <div style="display: flex; align-items: center;">
                <span style="height:8px; width:8px; border-radius:50%; background:#10b981; box-shadow:0 0 8px #10b981; margin-right:10px;"></span> 
                <span style="flex:1;">Sync State</span>
                <span style="color:#10b981; font-weight:600; font-size:0.7rem;">NOMINAL</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown("<br><br>", unsafe_allow_html=True)

# Render Chat History
for msg in st.session_state.history:
    with st.chat_message("user", avatar="👤"):
        st.write(msg["user"])
    with st.chat_message("assistant", avatar=agent_icons.get(msg["agent"], "🤖")):
        st.markdown(
            f'<div class="agent-badge">'
            f'{agent_icons.get(msg["agent"], "🤖")} {msg["agent"].replace("_", " ")}'
            f'</div>',
            unsafe_allow_html=True
        )
        st.write(msg["response"])

st.markdown('</div>', unsafe_allow_html=True)


def _is_long_operation(user_input: str) -> bool:
    """Detect multi-step operations that benefit from progress feedback."""
    u = user_input.lower()
    return any(kw in u for kw in [
        "write paper", "generate paper", "research pipeline",
        "publish pipeline", "apply pipeline", "content pipeline",
        "generate briefing", "morning briefing"
    ])


def _run_with_feedback(user_input: str) -> dict:
    """Run the orchestrator. Shows step-by-step status for long operations."""
    u = user_input.lower()
    force_agent = "info" if info_mode else None
    # Use Streamlit's session ID as the memory partition key
    session_key = str(st.session_state.get("current_session_id", "default"))

    if _is_long_operation(user_input):
        if "paper" in u or "research pipeline" in u:
            steps = [
                "Searching ArXiv for related papers...",
                "Writing Abstract & Introduction...",
                "Writing Related Work & Background...",
                "Writing Methodology...",
                "Writing Experiments & Results...",
                "Writing Conclusion & assembling paper...",
                "Finding target journals...",
            ]
        elif "publish pipeline" in u or "content pipeline" in u:
            steps = [
                "Generating LinkedIn post...",
                "Critic reviewing post quality...",
                "Writing full blog post...",
                "Queuing for your approval...",
            ]
        elif "apply pipeline" in u:
            steps = [
                "Tailoring resume to job description...",
                "Generating cover letter...",
                "Critic reviewing cover letter...",
                "Queuing application for approval...",
            ]
        else:
            steps = ["Gathering your data...", "Generating briefing..."]

        with st.status("Working...", expanded=True) as status:
            for step in steps:
                st.write(f"⏳ {step}")
                time.sleep(0.25)
            result = handle(user_input, force_agent=force_agent, session_id=session_key)
            status.update(label="✅ Done!", state="complete")
    else:
        with st.spinner("Thinking..."):
            result = handle(user_input, force_agent=force_agent, session_id=session_key)

    return result


# --- Process Pending Inputs ---
pending_input = st.session_state.pending_quick or st.session_state.pending_voice

if pending_input:
    st.session_state.pending_quick = None
    st.session_state.pending_voice = None

    st.chat_message("user", avatar="👤").write(pending_input)
    with st.chat_message("assistant", avatar="⚡"):
        result = _run_with_feedback(pending_input)
        st.markdown(
            f'<div class="agent-badge">'
            f'{agent_icons.get(result["agent"], "🤖")} {result["agent"].replace("_", " ")}'
            f'</div>',
            unsafe_allow_html=True
        )
        st.write(result["response"])

    if voice_enabled:
        speak(result["response"][:500])

    if st.session_state.current_session_id is None:
        title_text = " ".join(pending_input.split()[:5]) + "..."
        st.session_state.current_session_id = create_chat_session(title_text)

    entry = {"user": pending_input, "agent": result["agent"], "response": result["response"]}
    st.session_state.history.append(entry)
    save_chat_message(st.session_state.current_session_id, pending_input, result["agent"], result["response"])
    st.rerun()


# --- Chat Input ---
input_placeholder = "Ask InfoAgent about the system..." if info_mode else "Ask Aaqil anything..."
user_input = st.chat_input(input_placeholder)

if user_input:
    with st.chat_message("user", avatar="👤"):
        st.markdown('<div class="is-user-msg"></div>', unsafe_allow_html=True)
        st.write(user_input)
        
    with st.chat_message("assistant", avatar="⚡"):
        st.markdown('<div class="is-assistant-msg"></div>', unsafe_allow_html=True)
        result = _run_with_feedback(user_input)
        st.markdown(
            f'<div class="agent-badge">'
            f'{agent_icons.get(result["agent"], "🤖")} {result["agent"].replace("_", " ")}'
            f'</div>',
            unsafe_allow_html=True
        )
        st.write(result["response"])

    if voice_enabled:
        speak(result["response"][:500])

    if st.session_state.current_session_id is None:
        title_text = " ".join(user_input.split()[:5]) + "..."
        st.session_state.current_session_id = create_chat_session(title_text)

    entry = {"user": user_input, "agent": result["agent"], "response": result["response"]}
    st.session_state.history.append(entry)
    save_chat_message(st.session_state.current_session_id, user_input, result["agent"], result["response"])
    st.rerun()
