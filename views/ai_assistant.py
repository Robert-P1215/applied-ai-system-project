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

        mode = st.radio(
            "Mode",
            ["Ask a question", "Make a change"],
            horizontal=True,
            help=(
                "'Ask a question' only reads the current schedule and never changes it. "
                "'Make a change' lets the AI add/remove pets or tasks and mark tasks complete, "
                "then saves the result."
            ),
        )

        placeholder = (
            f"Ask about {owner.name}'s pets..."
            if mode == "Ask a question"
            else f"Tell the AI what to add, remove, or complete for {owner.name}'s pets..."
        )
        query = st.chat_input(placeholder)

        if query:
            is_error = False

            try:
                client = GeminiClient()
            except RuntimeError as e:
                response = str(e)
                is_error = True
            else:
                if mode == "Ask a question":
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

                    if not snippets:
                        response = PetRetriever.NO_EVIDENCE_MESSAGE
                    else:
                        try:
                            with st.spinner("Thinking..."):
                                response = client.answer_from_snippets(query, snippets)
                        except GeminiAPIError as e:
                            response = str(e)
                            is_error = True
                else:
                    try:
                        with st.spinner("Working..."):
                            response = client.run_action(query, owner)
                        storage.save_owner(owner)
                    except GeminiAPIError as e:
                        response = str(e)
                        is_error = True

            st.session_state.chat_history.append({
                "query": query,
                "response": response,
                "is_error": is_error,
            })
            st.rerun()
