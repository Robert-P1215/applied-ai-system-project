from dataclasses import dataclass, field
from datetime import date, time, timedelta
from typing import List, Optional

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
RECURRENCE_OPTIONS = ["none", "daily", "weekly"]


@dataclass
class Task:
    name: str
    time: time
    priority: str
    description: str = "No description"
    completion_status: bool = False
    recurrence: str = "none"          # "none" | "daily" | "weekly"
    due_date: date = field(default_factory=date.today)

    def mark_complete(self) -> Optional["Task"]:
        """
        Mark this task complete. If it recurs, return a new Task for the next
        occurrence (today + 1 day for daily, + 7 days for weekly). Returns None
        if the task does not recur.
        """
        self.completion_status = True

        if self.recurrence == "daily":
            next_date = self.due_date + timedelta(days=1)
        elif self.recurrence == "weekly":
            next_date = self.due_date + timedelta(weeks=1)
        else:
            return None

        return Task(
            name=self.name,
            time=self.time,
            priority=self.priority,
            description=self.description,
            recurrence=self.recurrence,
            due_date=next_date,
        )


@dataclass
class Pet:
    name: str
    species: str
    tasks: List[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Append a task to this pet's task list."""
        self.tasks.append(task)

    def remove_task(self, task_name: str) -> None:
        """Remove a task by name from this pet's task list."""
        self.tasks = [t for t in self.tasks if t.name != task_name]

    def get_tasks(self) -> List[Task]:
        """Return all tasks assigned to this pet."""
        return self.tasks


class Owner:
    def __init__(self, name: str):
        self.name = name
        self.pets: List[Pet] = []

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner's pet list."""
        self.pets.append(pet)

    def remove_pet(self, pet_name: str) -> None:
        """Remove a pet by name from this owner's pet list."""
        self.pets = [p for p in self.pets if p.name != pet_name]

    def get_pets(self) -> List[Pet]:
        """Return all pets belonging to this owner."""
        return self.pets


class Scheduler:
    def __init__(self, owner: Owner):
        self.owner = owner

    def build_schedule(self, sort_key: str = "priority") -> List[Task]:
        """
        Collect every incomplete task across all of the owner's pets and return
        them as a sorted list.

        Args:
            sort_key: "priority" (default) sorts high→medium→low, then by
                      due_date and time. "time" sorts strictly by due_date then
                      time, ignoring priority.

        Returns:
            A new list of incomplete Task objects in the requested order.
            Returns an empty list if no pending tasks exist.
        """
        all_tasks = []
        for pet in self.owner.get_pets():
            for task in pet.get_tasks():
                if not task.completion_status:
                    all_tasks.append(task)
        return self.sort_tasks(all_tasks, key=sort_key)

    def sort_tasks(self, tasks: List[Task], key: str = "priority") -> List[Task]:
        """
        Return a sorted copy of the provided task list without modifying the
        original.

        Sorting rules:
        - key="priority" (default): primary key is priority rank (high=0,
          medium=1, low=2, unknown=99), then due_date, then time-of-day, then
          task name as a tiebreaker so results are always deterministic.
        - key="time": primary key is due_date, then time-of-day, then task name.
          Priority is ignored, making this useful for a chronological day view.

        Args:
            tasks: The list of Task objects to sort.
            key:   Sort strategy — "priority" or "time".

        Returns:
            A new sorted list of Task objects.
        """
        if key == "time":
            return sorted(tasks, key=lambda t: (t.due_date, t.time, t.name))
        return sorted(tasks, key=lambda t: (PRIORITY_ORDER.get(t.priority, 99), t.due_date, t.time, t.name))

    def filter_by_pet(self, pet_name: str, sort_key: str = "priority") -> List[Task]:
        """
        Return all incomplete tasks belonging to a single named pet, sorted by
        the chosen strategy.

        This is useful when the owner wants to focus on one pet's schedule
        without seeing tasks from other pets.

        Args:
            pet_name: The exact name of the pet to filter by (case-sensitive).
            sort_key: Passed directly to sort_tasks — "priority" or "time".

        Returns:
            A sorted list of incomplete Task objects for that pet.
            Returns an empty list if the pet is not found or has no pending tasks.
        """
        for pet in self.owner.get_pets():
            if pet.name == pet_name:
                tasks = [t for t in pet.get_tasks() if not t.completion_status]
                return self.sort_tasks(tasks, key=sort_key)
        return []

    def filter_by_status(self, completed: bool) -> List[Task]:
        """
        Return all tasks across every pet that match the given completion state,
        sorted by priority then due_date then time.

        Args:
            completed: Pass True to retrieve finished tasks; False for pending.

        Returns:
            A sorted list of Task objects whose completion_status equals the
            argument. Returns an empty list if no tasks match.
        """
        result = []
        for pet in self.owner.get_pets():
            for task in pet.get_tasks():
                if task.completion_status == completed:
                    result.append(task)
        return self.sort_tasks(result)

    def get_conflicts(self) -> List[str]:
        """
        Lightweight conflict detection: scan all incomplete tasks in one dict
        pass, grouping by (due_date, time) slot. Returns a list of human-readable
        warning strings — never raises, never crashes.

        Each warning distinguishes same-pet conflicts from cross-pet conflicts so
        the caller can display them without any further processing.
        """
        # slot -> list of (pet_name, task_name)
        slot_map: dict = {}
        for pet in self.owner.get_pets():
            for task in pet.get_tasks():
                if not task.completion_status:
                    slot = (task.due_date, task.time)
                    slot_map.setdefault(slot, []).append((pet.name, task.name))

        warnings = []
        for (due, t), entries in sorted(slot_map.items()):
            if len(entries) < 2:
                continue
            when = f"{due} at {t.strftime('%I:%M %p')}"
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    pet_a, task_a = entries[i]
                    pet_b, task_b = entries[j]
                    if pet_a == pet_b:
                        msg = (
                            f"[WARNING] Same-pet conflict for {pet_a}: "
                            f"'{task_a}' and '{task_b}' both scheduled {when}."
                        )
                    else:
                        msg = (
                            f"[WARNING] Cross-pet conflict: "
                            f"{pet_a}'s '{task_a}' and {pet_b}'s '{task_b}' "
                            f"both scheduled {when}."
                        )
                    warnings.append(msg)
        return warnings

    def mark_task_complete(self, pet_name: str, task_name: str) -> Optional[Task]:
        """
        Mark the first incomplete task matching task_name on the named pet as
        done, then handle auto-rescheduling for recurring tasks.

        Recurring behaviour:
        - "daily"  — a new Task is created with due_date = completed task's
                     due_date + 1 day, then appended to the pet's task list.
        - "weekly" — same as daily but due_date + 7 days.
        - "none"   — task is marked complete; no new task is created.

        Args:
            pet_name:  Exact name of the pet that owns the task (case-sensitive).
            task_name: Exact name of the task to mark complete (case-sensitive).
                       Only the first still-pending match is affected.

        Returns:
            The newly created next-occurrence Task if the task recurs, or None
            if the task does not recur or no matching pending task was found.
        """
        for pet in self.owner.get_pets():
            if pet.name != pet_name:
                continue
            for task in pet.get_tasks():
                if task.name == task_name and not task.completion_status:
                    next_task = task.mark_complete()
                    if next_task is not None:
                        pet.add_task(next_task)
                    return next_task
        return None
