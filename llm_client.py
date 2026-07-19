"""
Gemini client wrapper used by PawPal+.

Handles:
- Configuring the Gemini client from the API_KEY environment variable
- Answering natural-language questions about an owner's pets/tasks
- Performing actions (add/remove pets & tasks, mark tasks complete) via
  Gemini function calling, bound to a specific Owner/Scheduler

Experiment with:
- Prompt wording
- Refusal conditions
- Which Scheduler/Owner operations are exposed as callable tools
"""

import os
from datetime import date, time

from google import genai
from google.genai import types

from pawpal_system import Owner, Pet, Scheduler, Task

GEMINI_MODEL_NAME = "gemini-3.5-flash"


class GeminiClient:
    """
    Wrapper around the Gemini model for PawPal+.

    Usage:
        client = GeminiClient()

        answer = client.ask(query, owner)
        result = client.run_action(query, owner)
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
    # Q&A: answer using only the owner's current schedule data
    # -----------------------------------------------------------

    def ask(self, query: str, owner: Owner) -> str:
        """
        Answer a question about `owner`'s pets/tasks using only their current
        schedule data as context. Refuses to guess if the data doesn't cover it.
        """
        context = self._describe_schedule(owner)

        prompt = f"""
You are PawPal+, an assistant that helps a pet owner track care tasks for their pets.

You will receive:
- The owner's current pets and tasks
- A question from the owner

Current data for {owner.name}:
{context}

Owner question:
{query}

Rules:
- Answer using only the data above. Do not invent pets, tasks, or schedule details.
- If the data does not provide enough information to answer confidently, reply exactly:
  "I do not know based on the current schedule."
"""
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as e:
            return f"API error — could not generate answer. ({type(e).__name__}: {e})"

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
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(tools=tools),
            )
            return (response.text or "").strip()
        except Exception as e:
            return f"API error — could not complete the request. ({type(e).__name__}: {e})"
