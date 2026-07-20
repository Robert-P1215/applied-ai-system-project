"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob

class DocuBot:
    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Split documents into paragraph-level chunks for finer retrieval
        self.chunks = self.build_chunks(self.documents)  # List of (filename, paragraph)

        # Build a retrieval index over the paragraph chunks (implemented in Phase 1)
        self.index = self.build_index(self.chunks)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Paragraph Chunking
    # -----------------------------------------------------------

    def build_chunks(self, documents):
        """
        Splits each document's text into paragraphs (separated by blank lines)
        so retrieval can return smaller, more focused snippets.

        Returns a list of tuples: (filename, paragraph_text)
        """
        chunks = []
        for filename, text in documents:
            paragraphs = text.split("\n\n")
            for paragraph in paragraphs:
                paragraph = paragraph.strip()
                if paragraph:
                    chunks.append((filename, paragraph))
        return chunks

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        TODO (Phase 1):
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}
        for filename, text in documents:
            tokens = text.lower().split()
            for token in tokens:
                if token not in index:
                    index[token] = []
                if filename not in index[token]:
                    index[token].append(filename)
        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        TODO (Phase 1):
        Return a simple relevance score for how well the text matches the query.

        Suggested baseline:
        - Convert query into lowercase words
        - Count how many appear in the text
        - Return the count as the score
        """
        query_words = query.lower().split()
        text_words = text.lower().split()
        return sum(text_words.count(word) for word in query_words)

    def retrieve(self, query, top_k=3):
        """
        TODO (Phase 1):
        Use the index and scoring function to select top_k relevant document snippets.

        Return a list of (filename, text) sorted by score descending.
        """
        scored = []
        for filename, paragraph in self.chunks:
            score = self.score_document(query, paragraph)
            if score > 0:
                scored.append((score, filename, paragraph))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = [(filename, text) for _, filename, text in scored]
        return results[:top_k]

    # -----------------------------------------------------------
    # Guardrail: refuse to answer without meaningful evidence
    # -----------------------------------------------------------

    NO_EVIDENCE_MESSAGE = "I do not know based on these docs."

    def has_sufficient_evidence(self, query, snippets):
        """
        Decides whether the retrieved snippets represent meaningful evidence
        for answering the query, as opposed to a coincidental word overlap.

        "No useful context" means either:
        - Nothing was retrieved at all, or
        - The best snippet only overlaps the query by a stray word or two,
          rather than sharing a real portion of its vocabulary.

        We require the top snippet to share at least half of the query's
        distinct words (minimum 1) to count as real evidence.
        """
        if not snippets:
            return False

        query_words = set(query.lower().split())
        if not query_words:
            return False

        _, top_text = snippets[0]
        top_words = set(top_text.lower().split())
        matched_words = query_words & top_words

        required_matches = max(1, len(query_words) // 2)
        return len(matched_words) >= required_matches

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not self.has_sufficient_evidence(query, snippets):
            return self.NO_EVIDENCE_MESSAGE

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not self.has_sufficient_evidence(query, snippets):
            return self.NO_EVIDENCE_MESSAGE

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
