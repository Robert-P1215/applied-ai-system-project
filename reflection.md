# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

- **Owner** holds a name and a list of pets. You can add a pet, remove one by name, or get the full list.
- **Pet** holds a name, species, and a list of tasks. Same idea — add, remove, or get tasks.
- **Task** holds all the details for one care item: name, description, time, due date, priority, recurrence, and whether it's done.
- **Scheduler** takes an Owner and handles everything scheduling-related — building the schedule, sorting, filtering, detecting conflicts, and managing recurring tasks.
- Relationships: one Owner has many Pets, one Pet has many Tasks, one Scheduler works with one Owner.

**b. Design changes**

A few things changed once I started actually implementing:

- Added `Task.name` — I realized `Pet.remove_task(task_name)` needed something to match against and there was no name field yet.
- Changed `Task.due_date` from a plain string to `datetime.date` so sorting by date would actually work instead of doing weird alphabetical string comparison.
- Added a `PRIORITY_ORDER` dict (`high → 0, medium → 1, low → 2`) to make the priority sort clean instead of a messy chain of if/else statements.

---

## 2. Scheduling Logic and Tradeoffs

**a. Constraints and priorities**

The scheduler considers two main things: **priority** (high, medium, low) and **time** (due date + time of day). I gave the user control over which one drives the sort because both are useful in different situations — priority sort helps you figure out what matters most, time sort helps you plan your actual day hour by hour.

I focused on these two because they're what a pet owner would actually think about. "
**b. Tradeoffs**

**Exact-time conflict detection instead of duration-aware overlap**

`get_conflicts()` only flags tasks as conflicting when they share the exact same `(due_date, time)` slot. So if Morning Walk is at 7:00 AM and Morning Feed is at 7:20 AM, there's no warning even though they might overlap in real life.

I made this tradeoff since detecting real overlap requires a duration field that doesn't exist on Task. Adding it would mean updating every constructor call, the UI form, the sort logic, and the recurrence logic — a lot of changes for one feature. 

If I added duration later, I could update `get_conflicts()` to check `task_a.time + timedelta(minutes=task_a.duration) > task_b.time` without having to change anything else.

---

## 3. AI Collaboration

**a. How you used AI**

I used Claude Code throughout the whole project. In Phase 1 it helped me think through the class structure. In Phase 2 I'd describe what a method was supposed to do and it would draft the code, which I'd then read and either keep, tweak, or throw out. In Phase 3 it helped connect everything to the Streamlit UI and catch bugs I missed, like tasks always being assigned to the first pet no matter which one was selected in the dropdown.

The most useful features were that it read my actual files, I could keep iterating on the same file without re-pasting everything, and asking it to explain a bug before jumping to a fix usually got better results than just saying "fix this."

**b. Judgment and verification**

When I added the "Remove Pet" button, the AI suggested showing a `st.success()` message right before calling `st.rerun()`. I accepted it, ran the app, and the message never showed up. The problem is `st.rerun()` wipes everything rendered in the same pass, so the message just disappears instantly.

The AI then suggested storing the message in `st.session_state` and displaying it on the next pass. That would have worked, but it felt like too much extra code for something cosmetic. I decided the pet list refreshing immediately was enough feedback on its own and just kept `st.rerun()` with no message. The takeaway was that you can't just read AI-generated code and assume it works — you have to actually run it.

**c. AI Strategy — being the lead architect**

Keeping separate chat sessions for each phase (design, backend, UI, docs) helped a lot because each conversation stayed focused. When a session is only about the backend, suggestions don't randomly drift into Streamlit UI patterns. When it's only about the UI, it's not pulling in unrelated class definitions.

The biggest thing I learned is that the AI does exactly what you tell it to, so the quality of what you get back depends almost entirely on how clearly you describe what you want. When I said something specific like "add a selectbox above the task form that lists all current pets by name and use the selected pet to assign the task," I got something I could use right away. Being the lead architect means knowing your system well enough to catch when a suggestion that looks right is actually wrong for your specific setup.

---

## 4. Testing and Verification

**a. What you tested**

I wrote six tests covering the behaviors I was most likely to accidentally break:

- Marking a task complete flips `completion_status` to `True`
- Adding a task increases the pet's task count
- `build_schedule(sort_key="time")` returns tasks in chronological order regardless of priority
- Completing a daily task creates a new task due the next day
- Two tasks in the same time slot generate a conflict warning
- Two tasks at different times on the same day do not generate a warning

These were the most important to test because they cover the core value of the app. If sorting, recurrence, or conflict detection is broken, the whole schedule is useless. I also wanted to catch any regressions if I refactored those methods later.

**b. Confidence**

I'm pretty confident the main happy-path behaviors work. All six tests pass and I manually tested the UI for the most common use cases. That said, there are a few gaps I'd want to fill before calling it done: weekly recurrence, filtering by a pet name that doesn't exist, same-pet conflicts (the current tests only cover cross-pet), and what happens when a task has a misspelled priority value. Those code paths exist but aren't tested yet.

---

## 5. Reflection

**a. What went well**

I'm most satisfied with the conflict detection. It does one clean pass through all the tasks using a dictionary to group them by time slot, and it handles both same-pet and cross-pet conflicts with clear warning messages. It also never crashes — if there are no conflicts, it just returns an empty list. It ended up being one of the simpler methods to write but one of the most useful features in the final app.

**b. What you would improve**

If I had another iteration, I'd add a duration field to Task and update conflict detection to catch real overlap instead of just exact-time matches. I'd also redesign the UI layout — right now everything is stacked in one long page, which gets hard to navigate once you have several pets and tasks. Breaking it into tabs (one for managing pets and tasks, one for the schedule view) would make it feel a lot cleaner.

**c. Key takeaway**

Starting with a UML diagram actually matters more than I expected. Before I had one, I kept second-guessing what belonged where — should recurrence logic live in Task or Scheduler? Writing out the design forced me to think through those questions before touching any code, which meant way less refactoring later. The AI was also most useful once I had a clear picture of the system, because then I could give it specific instructions instead of vague ones and get something useful back on the first try.
