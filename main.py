from datetime import date, time
from pawpal_system import Owner, Pet, Task, Scheduler

today = date.today()

owner = Owner(name="Jordan")

mochi = Pet(name="Mochi", species="dog")
luna = Pet(name="Luna", species="cat")
rex = Pet(name="Rex", species="dog")   # conflict-free pet to verify no false positives

# --- Mochi: same-pet conflict ---
# Two of Mochi's tasks land at exactly 7:00 AM on the same day.
mochi.add_task(Task(name="Morning Walk",  description="30-min walk",         time=time(7, 0),  priority="high",   recurrence="daily",  due_date=today))
mochi.add_task(Task(name="Morning Feed",  description="Breakfast kibble",     time=time(7, 0),  priority="high",   recurrence="daily",  due_date=today))  # same-pet conflict
mochi.add_task(Task(name="Vet Checkup",   description="Annual shots",         time=time(10, 0), priority="high",   recurrence="none",   due_date=today))
mochi.add_task(Task(name="Evening Feed",  description="Dinner kibble",        time=time(18, 0), priority="low",    recurrence="daily",  due_date=today))

# --- Luna: cross-pet conflict with Mochi at 10:00 AM ---
luna.add_task(Task(name="Playtime",       description="Feather wand session", time=time(10, 0), priority="medium", recurrence="weekly", due_date=today))  # cross-pet conflict with Vet Checkup
luna.add_task(Task(name="Litter Box",     description="Clean litter box",     time=time(19, 0), priority="medium", recurrence="daily",  due_date=today))

# --- Rex: no conflicts at all ---
rex.add_task(Task(name="Afternoon Walk",  description="Park stroll",          time=time(15, 0), priority="medium", recurrence="daily",  due_date=today))
rex.add_task(Task(name="Rex Evening Feed",description="One cup dry food",     time=time(17, 0), priority="low",    recurrence="daily",  due_date=today))

owner.add_pet(mochi)
owner.add_pet(luna)
owner.add_pet(rex)

scheduler = Scheduler(owner=owner)


def print_tasks(label: str, tasks) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if not tasks:
        print("  (no tasks)")
        return
    for i, task in enumerate(tasks, start=1):
        recur = f" | {task.recurrence}" if task.recurrence != "none" else ""
        status = "done" if task.completion_status else "pending"
        print(f"  {i}. [{task.priority.upper()}] {task.name} | {task.due_date} {task.time.strftime('%I:%M %p')}{recur} ({status})")


# Full schedule so the reader can see what's loaded
print_tasks("Full schedule -- sorted by TIME", scheduler.build_schedule(sort_key="time"))

# Conflict detection
print(f"\n{'='*60}")
print("  Conflict Detection")
print(f"{'='*60}")
warnings = scheduler.get_conflicts()
if warnings:
    for msg in warnings:
        print(f"  {msg}")
else:
    print("  No conflicts found.")

# Verify Rex has no conflicts by filtering his tasks in isolation
print(f"\n{'='*60}")
print("  Rex's tasks (should produce zero warnings)")
print(f"{'='*60}")
rex_only_owner = Owner(name="Jordan")
rex_only_owner.add_pet(rex)
rex_scheduler = Scheduler(owner=rex_only_owner)
rex_warnings = rex_scheduler.get_conflicts()
print(f"  Conflicts found: {len(rex_warnings)}  (expected 0)")
