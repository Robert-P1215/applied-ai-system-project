import streamlit as st

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# --- Session state init ---
# Only the selected owner's name lives across reruns. The Owner/Scheduler
# object graph is rebuilt from CSV at the top of every run, so CSV stays the
# single source of truth and can't drift from what's cached in the session.
if "owner_name" not in st.session_state:
    st.session_state.owner_name = None

main_page = st.Page("views/main_page.py", title="Main Page", icon="🐾", default=True)
ai_assistant_page = st.Page("views/ai_assistant.py", title="AI Assistant", icon="🤖")

pg = st.navigation([main_page, ai_assistant_page], position="hidden")

st.sidebar.title("🐾 PawPal+")
st.sidebar.page_link(main_page)
st.sidebar.page_link(ai_assistant_page)

pg.run()
