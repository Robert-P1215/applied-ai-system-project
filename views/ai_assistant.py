import streamlit as st

import storage
from llm_client import GeminiAPIError, GeminiClient
from pet_retriever import PetRetriever
from views.common import load_owner_cached

st.title("🤖 AI Assistant")

if not st.session_state.owner_name:
    st.info("Set an owner on the Main Page before using the AI Assistant.")
else:
    owner = load_owner_cached(st.session_state.owner_name, storage.data_version())

    if owner is None:
        st.warning("Could not load this owner's data.")
    else:
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for entry in st.session_state.chat_history:
            with st.chat_message("user"):
                st.write(entry["query"])
            with st.chat_message("assistant"):
                if entry.get("is_error"):
                    st.error(entry["response"])
                else:
                    st.write(entry["response"])

        query = st.chat_input(f"Ask about {owner.name}'s pets...")

        if query:
            retriever = PetRetriever(owner)

            # Ground on the owner's full current data rather than a narrow
            # top-k. One owner's dataset is a handful of pets/tasks, not a
            # real document corpus, so restricting context via retrieval
            # buys nothing and repeatedly caused false refusals on
            # legitimate questions (recurrence wording, aggregate counts,
            # cross-pet comparisons) that no single chunk answers alone.
            # PetRetriever.retrieve/has_sufficient_evidence are still
            # available for narrower, single-chunk lookups if ever needed.
            snippets = retriever.chunks
            is_error = False

            if not snippets:
                response = PetRetriever.NO_EVIDENCE_MESSAGE
            else:
                try:
                    client = GeminiClient()
                except RuntimeError as e:
                    response = str(e)
                    is_error = True
                else:
                    try:
                        with st.spinner("Thinking..."):
                            response = client.answer_from_snippets(query, snippets)
                    except GeminiAPIError as e:
                        response = str(e)
                        is_error = True

            st.session_state.chat_history.append({
                "query": query,
                "response": response,
                "is_error": is_error,
            })
            st.rerun()
