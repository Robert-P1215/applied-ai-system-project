"""
Retrieval layer for the PawPal+ AI Assistant.
"""

import re

from pawpal_system import Owner, Scheduler

_WORD_RE = re.compile(r"[a-z0-9']+")

# Common English filler words dropped before scoring/evidence-matching, so a
# conversational question ("What tasks do I have every day?") isn't judged
# against words that will never appear in declarative chunk text.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "am",
    "do", "does", "did", "i", "me", "my", "you", "your",
    "what", "which", "who", "whom", "have", "has", "had",
    "of", "to", "in", "on", "for", "and", "or", "that", "this",
    "please", "can", "could", "would", "will", "it", "its",
}

_RECURRENCE_PHRASES = {
    "daily": "This task repeats every day.",
    "weekly": "This task repeats every week.",
    "none": "This is a one-time task that does not repeat.",
}


def _tokenize(text: str):
    """Lowercase and split into word tokens, stripping punctuation so 'day?' matches 'day'."""
    return _WORD_RE.findall(text.lower())


def _content_words(text: str):
    """Tokenize and drop filler words, leaving only the substantive vocabulary."""
    return [w for w in _tokenize(text) if w not in _STOPWORDS]


class PetRetriever:
    """
    Usage:
        retriever = PetRetriever(owner)
        snippets = retriever.retrieve("what does mochi have today")
    """

    NO_EVIDENCE_MESSAGE = "I do not know based on the current schedule."

    def __init__(self, owner: Owner):
        self.owner = owner
        self.chunks = self.build_chunks(owner)  # list of (label, text)

    # -----------------------------------------------------------
    # Chunking: turn live pet/task data into retrievable text chunks
    # -----------------------------------------------------------

    def build_chunks(self, owner: Owner):
        """
        One aggregate summary chunk (pet/task counts), one chunk per pet
        (profile), one chunk per task, plus one chunk summarizing scheduling
        conflicts if any exist. This is the PawPal+ analog of DocuBot's
        paragraph-level chunks pulled from docs/*.md.

        The summary chunk exists because count/list-style questions ("how
        many pets do I have") have no single-pet or single-task chunk that
        answers them — they require reasoning over the whole collection, so
        a precomputed aggregate gives retrieval something concrete to match.
        """
        chunks = [("Owner Summary", self._describe_owner(owner))]
        for pet in owner.get_pets():
            chunks.append((f"{pet.name} (profile)", f"{pet.name} is a {pet.species}."))
            for task in pet.get_tasks():
                status = "done" if task.completion_status else "pending"
                label = f"{pet.name}: {task.name}"
                recurrence_phrase = _RECURRENCE_PHRASES.get(
                    task.recurrence, f"Recurrence: {task.recurrence}."
                )
                text = (
                    f"{pet.name} is a {pet.species} with a {task.priority} priority task "
                    f"called {task.name} which is described as {task.description}. It is "
                    f"scheduled for {task.due_date} at {task.time.strftime('%I:%M %p')}. "
                    f"{recurrence_phrase} Status: {status}."
                )
                chunks.append((label, text))

        conflicts = Scheduler(owner=owner).get_conflicts()
        if conflicts:
            chunks.append(("Schedule Conflicts", "\n".join(conflicts)))

        return chunks

    def _describe_owner(self, owner: Owner) -> str:
        """Precomputed counts so count/comparison questions don't rely on the model tallying chunks itself."""
        pets = owner.get_pets()
        pet_names = ", ".join(p.name for p in pets) if pets else "no pets"
        all_tasks = [t for p in pets for t in p.get_tasks()]
        pending = sum(1 for t in all_tasks if not t.completion_status)
        completed = len(all_tasks) - pending
        per_pet_counts = ", ".join(f"{p.name} has {len(p.get_tasks())} task(s)" for p in pets)
        return (
            f"{owner.name} has {len(pets)} pet(s): {pet_names}. "
            f"There are {len(all_tasks)} task(s) total across all pets: "
            f"{pending} pending and {completed} completed. "
            f"Task count per pet: {per_pet_counts}."
        )

    # -----------------------------------------------------------
    # Scoring and Retrieval (same approach as DocuBot Phase 1)
    # -----------------------------------------------------------

    def score_chunk(self, query: str, text: str) -> int:
        """Count how many non-filler query words appear in the chunk text (word-overlap scoring)."""
        query_words = _content_words(query)
        text_words = _tokenize(text)
        return sum(text_words.count(word) for word in query_words)

    def retrieve(self, query: str, top_k: int = 10):
        """Return the top_k (label, text) chunks by word-overlap score, highest first."""
        scored = []
        for label, text in self.chunks:
            score = self.score_chunk(query, text)
            if score > 0:
                scored.append((score, label, text))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [(label, text) for _, label, text in scored[:top_k]]

    # -----------------------------------------------------------
    # Guardrail: refuse to answer without meaningful evidence
    # -----------------------------------------------------------

    def has_sufficient_evidence(self, query: str, snippets) -> bool:
        """
        Decides whether the retrieved snippets represent meaningful evidence
        for answering the query, as opposed to a coincidental word overlap.

        Requires the top snippet to share at least half of the query's
        distinct words (minimum 1) to count as real evidence.
        """
        if not snippets:
            return False

        query_words = set(_content_words(query))
        if not query_words:
            return False

        _, top_text = snippets[0]
        top_words = set(_tokenize(top_text))
        matched_words = query_words & top_words

        required_matches = max(1, len(query_words) // 2)
        return len(matched_words) >= required_matches
