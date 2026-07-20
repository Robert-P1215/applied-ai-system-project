"""
Gemini client wrapper used by PawPal+.

Handles:
- Configuring the Gemini client from the API_KEY environment variable
- RAG style answers that use only snippets retrieved by PetRetriever
- Performing actions (add/remove pets & tasks, mark tasks complete) via
  Gemini function calling, bound to a specific Owner/Scheduler

Experiment with:
- Prompt wording
- Refusal conditions
- Which Scheduler/Owner operations are exposed as callable tools
"""

import os
from datetime import date, time
from time import sleep

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from pawpal_system import Owner, Pet, Scheduler, Task

load_dotenv()

GEMINI_MODEL_NAME = "gemini-3.5-flash"


class GeminiAPIError(Exception):
    """
    Raised when a Gemini API call ultimately fails — after retries are
    exhausted for transient errors, or immediately for non-retryable ones.
    The message is written to be shown directly to the end user, so callers
    should surface it rather than swallow it into a normal answer string.
    """


class GeminiClient:
    """
    Wrapper around the Gemini model for PawPal+.

    answer_from_snippets and run_action raise GeminiAPIError if the call
    ultimately fails (overloaded, rate/quota limited, etc.) — callers should
    catch it and show its message, since it's already written for the end
    user rather than being an internal detail.

    Usage:
        client = GeminiClient()

        snippets = PetRetriever(owner).retrieve(query)
        try:
            answer = client.answer_from_snippets(query, snippets)
        except GeminiAPIError as e:
            answer = str(e)
    """

    def __init__(self):
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing API_KEY environment variable. "
                "Set it in your shell or .env file to enable LLM features."
            )

        self.client = genai.Client(api_key=api_key)

    # -----------------------------------------------------------
    # Shared context: render an owner's live data as plain text
    # -----------------------------------------------------------

    def _describe_schedule(self, owner: Owner) -> str:
        """Render every pet and task for `owner` as plain text context for the model."""
        if not owner.get_pets():
            return "This owner has no pets registered yet."

        lines = []
        for pet in owner.get_pets():
            lines.append(f"Pet: {pet.name} ({pet.species})")
            tasks = pet.get_tasks()
            if not tasks:
                lines.append("  (no tasks)")
                continue
            for task in tasks:
                status = "done" if task.completion_status else "pending"
                lines.append(
                    f"  - {task.name} | {task.due_date} {task.time.strftime('%I:%M %p')} "
                    f"| priority={task.priority} | recurrence={task.recurrence} | {status}"
                )

        conflicts = Scheduler(owner=owner).get_conflicts()
        if conflicts:
            lines.append("\nConflicts:")
            lines.extend(f"  - {c}" for c in conflicts)

        return "\n".join(lines)

    # -----------------------------------------------------------
    # Shared API call: retries transient failures, raises a specific
    # GeminiAPIError with a user-facing reason for everything else
    # -----------------------------------------------------------

    def _generate_content(self, **kwargs) -> str:
        """
        Call Gemini's generate_content, retrying transient server overloads
        (ServerError, e.g. 503) a couple of times with backoff. Rate/quota
        limits (ClientError 429) and any other failure are not retried —
        retrying an exhausted quota immediately just fails again — and are
        raised as GeminiAPIError with a message identifying which of the two
        happened, instead of being folded into a normal answer string.
        """
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.client.models.generate_content(model=GEMINI_MODEL_NAME, **kwargs)
                return (response.text or "").strip()
            except errors.ServerError as e:
                if attempt < max_attempts:
                    sleep(2 ** (attempt - 1))  # 1s, then 2s
                    continue
                raise GeminiAPIError(
                    "The AI service is temporarily overloaded and didn't respond "
                    f"after {max_attempts} attempts. Please try again in a moment. "
                    f"(ServerError {e.code}: {e.message})"
                ) from e
            except errors.ClientError as e:
                if e.code == 429:
                    raise GeminiAPIError(
                        "This request was rejected because the Gemini API rate or "
                        "quota limit has been reached. Wait a bit before trying "
                        f"again. (ClientError 429: {e.message})"
                    ) from e
                raise GeminiAPIError(
                    f"The API rejected this request. (ClientError {e.code}: {e.message})"
                ) from e
            except Exception as e:
                raise GeminiAPIError(
                    f"Unexpected error talking to the AI service. ({type(e).__name__}: {e})"
                ) from e

    # -----------------------------------------------------------
    # RAG generation: answer using only retrieved snippets
    # -----------------------------------------------------------

    def answer_from_snippets(self, query: str, snippets) -> str:
        """
        Generate an answer using only the retrieved snippets.

        snippets: list of (label, text) tuples selected by
        PetRetriever.retrieve, e.g. ("Mochi: Morning Walk", "Pet Mochi ...").

        Mirrors DocuBot's answer_from_snippets (outside_files/llm_client.py):
        shows each snippet with its label, instructs the model to rely only
        on these snippets, and requires an explicit refusal when the
        snippets aren't enough.
        """
        if not snippets:
            return "I do not know based on the current schedule."

        context_blocks = [f"Record: {label}\n{text}\n" for label, text in snippets]
        context = "\n\n".join(context_blocks)

        prompt = f"""
You are PawPal+, a cautious assistant helping a pet owner understand their pets' care schedule.

You will receive:
- A small set of retrieved records about the owner's pets and tasks
- A question from the owner

Retrieved records:
{context}

Owner question:
{query}

Rules:
- Answer using only the information in the records above. Do not invent
  pets, tasks, or schedule details.
- If the records do not provide enough evidence to answer confidently, reply
  exactly: "I do not know based on the current schedule."
- When you do answer, briefly mention which record(s) you relied on.
"""
        return self._generate_content(contents=prompt)

    # -----------------------------------------------------------
    # Agent actions: let Gemini call real Scheduler/Owner operations
    # -----------------------------------------------------------

    def run_action(self, query: str, owner: Owner) -> str:
        """
        Let Gemini decide which action(s) to take on `owner` in response to a
        natural-language request (e.g. "add a daily 7am walk for Mochi" or
        "mark Mochi's morning walk done"), using function calling bound to
        this specific owner.

        Mutates `owner` in place. The caller is responsible for persisting
        the change (e.g. via storage.save_owner) after this returns.

        Returns the model's final text response describing what it did.
        """
        scheduler = Scheduler(owner=owner)

        def add_pet(pet_name: str, species: str) -> str:
            """Register a new pet for this owner. species is typically 'dog', 'cat', or 'other'."""
            if any(p.name == pet_name for p in owner.get_pets()):
                return f"A pet named '{pet_name}' already exists."
            owner.add_pet(Pet(name=pet_name, species=species))
            return f"Added pet '{pet_name}' ({species})."

        def remove_pet(pet_name: str) -> str:
            """Remove a pet and all of its tasks."""
            owner.remove_pet(pet_name)
            return f"Removed pet '{pet_name}'."

        def add_task(
            pet_name: str,
            task_name: str,
            description: str,
            hour: int,
            minute: int,
            priority: str,
            recurrence: str,
            due_date_iso: str,
        ) -> str:
            """
            Add a care task to a pet.

            priority must be one of 'high', 'medium', 'low'.
            recurrence must be one of 'none', 'daily', 'weekly'.
            due_date_iso is an ISO date string, e.g. '2026-07-19'.
            """
            pet = next((p for p in owner.get_pets() if p.name == pet_name), None)
            if pet is None:
                return f"No pet named '{pet_name}' found."
            pet.add_task(Task(
                name=task_name,
                description=description,
                time=time(hour, minute),
                priority=priority,
                recurrence=recurrence,
                due_date=date.fromisoformat(due_date_iso),
            ))
            return f"Added task '{task_name}' for {pet_name}."

        def remove_task(pet_name: str, task_name: str) -> str:
            """Remove a task by name from a pet."""
            pet = next((p for p in owner.get_pets() if p.name == pet_name), None)
            if pet is None:
                return f"No pet named '{pet_name}' found."
            pet.remove_task(task_name)
            return f"Removed task '{task_name}' from {pet_name}."

        def mark_task_complete(pet_name: str, task_name: str) -> str:
            """Mark a pet's task complete. Recurring tasks are auto-rescheduled."""
            next_task = scheduler.mark_task_complete(pet_name, task_name)
            if next_task is not None:
                return f"Marked '{task_name}' complete. Next occurrence due {next_task.due_date}."
            return f"Marked '{task_name}' complete."

        def get_conflicts() -> str:
            """List any scheduling conflicts across all of the owner's pets."""
            conflicts = scheduler.get_conflicts()
            return "\n".join(conflicts) if conflicts else "No conflicts found."

        tools = [add_pet, remove_pet, add_task, remove_task, mark_task_complete, get_conflicts]

        prompt = f"""
You are PawPal+, an assistant that manages pet care tasks for {owner.name}.

Current data:
{self._describe_schedule(owner)}

Owner request:
{query}

Use the available tools to carry out the request. If the request is just a
question, answer directly from the current data above instead of calling a tool.
"""
        return self._generate_content(contents=prompt, config=types.GenerateContentConfig(tools=tools))
