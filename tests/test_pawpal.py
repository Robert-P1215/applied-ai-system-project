from datetime import date, time
from pawpal_system import Task, Pet, Owner, Scheduler


def test_mark_complete_changes_status():
    task = Task(name="Morning Walk", description="Walk the dog", time=time(7, 0), priority="high")
    assert task.completion_status is False
    task.mark_complete()
    assert task.completion_status is True


def test_add_task_increases_pet_task_count():
    pet = Pet(name="Mochi", species="dog")
    assert len(pet.get_tasks()) == 0
    pet.add_task(Task(name="Evening Feed", description="One cup of dry food", time=time(18, 0), priority="medium"))
    assert len(pet.get_tasks()) == 1


# ── Sorting correctness ────────────────────────────────────────────────────────

def test_sort_by_time_returns_chronological_order():
    """Tasks should come back ordered by due_date then time-of-day when sort_key='time'."""
    owner = Owner("Alice")
    pet = Pet("Rex", "dog")
    owner.add_pet(pet)

    day1 = date(2026, 6, 21)
    day2 = date(2026, 6, 22)

    pet.add_task(Task(name="Dinner",    time=time(18, 0), priority="high",   due_date=day2))
    pet.add_task(Task(name="Breakfast", time=time(8,  0), priority="low",    due_date=day1))
    pet.add_task(Task(name="Lunch",     time=time(12, 0), priority="medium", due_date=day1))

    scheduler = Scheduler(owner)
    sorted_tasks = scheduler.build_schedule(sort_key="time")

    assert [t.name for t in sorted_tasks] == ["Breakfast", "Lunch", "Dinner"]


# ── Recurrence logic ───────────────────────────────────────────────────────────

def test_daily_recurrence_creates_next_day_task():
    """Completing a daily task should add a new task due the following day."""
    owner = Owner("Bob")
    pet = Pet("Luna", "cat")
    owner.add_pet(pet)

    original_date = date(2026, 6, 21)
    pet.add_task(Task(
        name="Morning Feed",
        time=time(7, 0),
        priority="high",
        recurrence="daily",
        due_date=original_date,
    ))

    scheduler = Scheduler(owner)
    next_task = scheduler.mark_task_complete("Luna", "Morning Feed")

    # The original task is now complete
    original = pet.get_tasks()[0]
    assert original.completion_status is True

    # A new task was created for the next day
    assert next_task is not None
    assert next_task.due_date == date(2026, 6, 22)
    assert next_task.completion_status is False
    assert next_task.recurrence == "daily"

    # The pet now has two tasks total (original + rescheduled)
    assert len(pet.get_tasks()) == 2


# ── Conflict detection ─────────────────────────────────────────────────────────

def test_get_conflicts_flags_same_time_slot():
    """Two incomplete tasks scheduled at the same date and time should produce a warning."""
    owner = Owner("Carol")
    dog = Pet("Buddy", "dog")
    cat = Pet("Whiskers", "cat")
    owner.add_pet(dog)
    owner.add_pet(cat)

    conflict_date = date(2026, 6, 21)
    conflict_time = time(9, 0)

    dog.add_task(Task(name="Walk",     time=conflict_time, priority="high", due_date=conflict_date))
    cat.add_task(Task(name="Vet Visit", time=conflict_time, priority="high", due_date=conflict_date))

    scheduler = Scheduler(owner)
    warnings = scheduler.get_conflicts()

    assert len(warnings) == 1
    assert "Cross-pet conflict" in warnings[0]
    assert "Walk" in warnings[0]
    assert "Vet Visit" in warnings[0]


def test_get_conflicts_no_warning_for_different_times():
    """Tasks at different times on the same day should not trigger any conflict."""
    owner = Owner("Dave")
    pet = Pet("Max", "dog")
    owner.add_pet(pet)

    today = date(2026, 6, 21)
    pet.add_task(Task(name="Morning Walk", time=time(7, 0),  priority="high", due_date=today))
    pet.add_task(Task(name="Evening Walk", time=time(18, 0), priority="high", due_date=today))

    assert Scheduler(owner).get_conflicts() == []
