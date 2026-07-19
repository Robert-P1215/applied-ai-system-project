import csv
import os
from datetime import date, time
from typing import List, Optional

from pawpal_system import Owner, Pet, Task

DATA_DIR = "data"
OWNERS_CSV = os.path.join(DATA_DIR, "owners.csv")
PETS_CSV = os.path.join(DATA_DIR, "pets.csv")
TASKS_CSV = os.path.join(DATA_DIR, "tasks.csv")

OWNERS_FIELDS = ["name"]
PETS_FIELDS = ["owner_name", "pet_name", "species"]
TASKS_FIELDS = [
    "owner_name", "pet_name", "task_name", "description", "time",
    "priority", "completion_status", "recurrence", "due_date",
]


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _read_rows(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(path: str, fieldnames: List[str], rows: List[dict]) -> None:
    _ensure_data_dir()
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def data_version() -> float:
    """
    Return a version stamp that changes whenever any CSV table is written.

    Callers can use this alongside a cached load (e.g. st.cache_data) so that
    repeated reads within the same data version are served from cache instead
    of re-reading and re-parsing the CSVs from disk.
    """
    mtimes = [os.path.getmtime(p) for p in (OWNERS_CSV, PETS_CSV, TASKS_CSV) if os.path.exists(p)]
    return max(mtimes, default=0.0)


def list_owner_names() -> List[str]:
    """Return every owner name currently saved in owners.csv."""
    return [row["name"] for row in _read_rows(OWNERS_CSV)]


def save_owner(owner: Owner) -> None:
    """
    Persist one owner plus all of their pets and tasks to the CSV tables.

    Replaces any previously saved rows belonging to this owner's name (and
    only this owner) so repeated saves overwrite rather than duplicate,
    while other owners' rows are left untouched.
    """
    owners = [r for r in _read_rows(OWNERS_CSV) if r["name"] != owner.name]
    owners.append({"name": owner.name})
    _write_rows(OWNERS_CSV, OWNERS_FIELDS, owners)

    pets = [r for r in _read_rows(PETS_CSV) if r["owner_name"] != owner.name]
    for pet in owner.get_pets():
        pets.append({"owner_name": owner.name, "pet_name": pet.name, "species": pet.species})
    _write_rows(PETS_CSV, PETS_FIELDS, pets)

    tasks = [r for r in _read_rows(TASKS_CSV) if r["owner_name"] != owner.name]
    for pet in owner.get_pets():
        for task in pet.get_tasks():
            tasks.append({
                "owner_name": owner.name,
                "pet_name": pet.name,
                "task_name": task.name,
                "description": task.description,
                "time": task.time.strftime("%H:%M"),
                "priority": task.priority,
                "completion_status": task.completion_status,
                "recurrence": task.recurrence,
                "due_date": task.due_date.isoformat(),
            })
    _write_rows(TASKS_CSV, TASKS_FIELDS, tasks)


def load_owner(name: str) -> Optional[Owner]:
    """
    Rebuild an Owner (with all of their pets and tasks) from the CSV tables.

    Returns None if no owner with this name has ever been saved.
    """
    if not any(r["name"] == name for r in _read_rows(OWNERS_CSV)):
        return None

    owner = Owner(name=name)

    pets_by_name = {}
    for row in _read_rows(PETS_CSV):
        if row["owner_name"] != name:
            continue
        pet = Pet(name=row["pet_name"], species=row["species"])
        owner.add_pet(pet)
        pets_by_name[pet.name] = pet

    for row in _read_rows(TASKS_CSV):
        if row["owner_name"] != name:
            continue
        pet = pets_by_name.get(row["pet_name"])
        if pet is None:
            continue
        hour, minute = map(int, row["time"].split(":"))
        pet.add_task(Task(
            name=row["task_name"],
            description=row["description"],
            time=time(hour, minute),
            priority=row["priority"],
            completion_status=row["completion_status"] == "True",
            recurrence=row["recurrence"],
            due_date=date.fromisoformat(row["due_date"]),
        ))

    return owner
