import streamlit as st
from datetime import date, time
from pawpal_system import Pet, Owner, Scheduler, Task, RECURRENCE_OPTIONS

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")

# --- Session state init ---
if "owner" not in st.session_state:
    st.session_state.owner = None
if "scheduler" not in st.session_state:
    st.session_state.scheduler = None

# --- Owner setup ---
st.subheader("Owner")
owner_name = st.text_input("Owner name", value="Jordan")

if st.button("Set Owner"):
    st.session_state.owner = Owner(name=owner_name)
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)
    st.success(f"Owner '{owner_name}' created.")

# --- Add pets ---
st.subheader("Add a Pet")
if st.session_state.owner is None:
    st.info("Set an owner above before adding pets.")
else:
    pcol1, pcol2 = st.columns(2)
    with pcol1:
        pet_name = st.text_input("Pet name", value="Mochi")
    with pcol2:
        species = st.selectbox("Species", ["dog", "cat", "other"])

    if st.button("Add Pet"):
        existing_names = [p.name for p in st.session_state.owner.get_pets()]
        if pet_name in existing_names:
            st.warning(f"A pet named '{pet_name}' already exists.")
        else:
            st.session_state.owner.add_pet(Pet(name=pet_name, species=species))
            st.success(f"Added pet '{pet_name}' ({species}).")

    current_pets = st.session_state.owner.get_pets()
    if current_pets:
        st.caption("Current pets: " + ", ".join(f"{p.name} ({p.species})" for p in current_pets))

# --- Remove a pet ---
if st.session_state.owner is not None:
    removable_pets = [p.name for p in st.session_state.owner.get_pets()]
    if removable_pets:
        st.subheader("Remove a Pet")
        pet_to_remove = st.selectbox("Select pet to remove", removable_pets, key="remove_pet_select")
        if st.button("Remove Pet"):
            st.session_state.owner.remove_pet(pet_to_remove)
            st.rerun()

# --- Task input ---
st.divider()
st.subheader("Add a Task")

if st.session_state.owner is None:
    st.info("Set an owner and pet above before adding tasks.")
else:
    pets = st.session_state.owner.get_pets()
    pet_names = [p.name for p in pets]
    selected_pet_name = st.selectbox("Assign to pet", pet_names)

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        task_name = st.text_input("Task name", value="Morning Walk")
    with col2:
        task_desc = st.text_input("Description", value="Walk around the block")
    with col3:
        task_hour = st.number_input("Hour (0-23)", min_value=0, max_value=23, value=7)
    with col4:
        priority = st.selectbox("Priority", ["high", "medium", "low"])
    with col5:
        recurrence = st.selectbox("Recurrence", RECURRENCE_OPTIONS)
    with col6:
        due = st.date_input("Due date", value=date.today())

    if st.button("Add Task"):
        task = Task(
            name=task_name,
            description=task_desc,
            time=time(task_hour, 0),
            priority=priority,
            recurrence=recurrence,
            due_date=due,
        )
        target_pet = next(p for p in pets if p.name == selected_pet_name)
        target_pet.add_task(task)
        st.success(f"Task '{task_name}' added to {selected_pet_name} for {due}.")

# --- Schedule ---
st.divider()
st.subheader("Today's Schedule")

if st.session_state.scheduler is not None:
    scheduler: Scheduler = st.session_state.scheduler
    pets = st.session_state.owner.get_pets()
    pet_names = [p.name for p in pets]

    # --- Controls row ---
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        sort_key = st.radio("Sort by", ["priority", "time"], horizontal=True)
    with ctrl2:
        pet_filter = st.selectbox("Filter by pet", ["All pets"] + pet_names)
    with ctrl3:
        status_filter = st.selectbox("Filter by status", ["Pending", "Completed", "All"])

    if st.button("Generate Schedule"):
        # --- Conflict detection ---
        conflicts = scheduler.get_conflicts()
        if conflicts:
            st.warning(f"⚠️ {len(conflicts)} scheduling conflict(s) detected:")
            for msg in conflicts:
                clean = msg.replace("[WARNING] ", "")
                st.warning(f"• {clean}")
        else:
            st.success("No scheduling conflicts found.")

        # --- Fetch tasks based on filters ---
        if status_filter == "Completed":
            schedule = scheduler.filter_by_status(completed=True)
        elif pet_filter != "All pets" and status_filter == "Pending":
            schedule = scheduler.filter_by_pet(pet_filter, sort_key=sort_key)
        elif status_filter == "All":
            all_tasks = []
            for pet in pets:
                if pet_filter == "All pets" or pet.name == pet_filter:
                    all_tasks.extend(pet.get_tasks())
            schedule = scheduler.sort_tasks(all_tasks, key=sort_key)
        else:
            schedule = scheduler.build_schedule(sort_key=sort_key)

        if not schedule:
            st.info("No tasks found for the selected filters.")
        else:
            PRIORITY_COLOR = {"high": "🔴", "medium": "🟡", "low": "🟢"}
            rows = []
            for task in schedule:
                icon = PRIORITY_COLOR.get(task.priority, "⚪")
                status = "✅ Done" if task.completion_status else "⏳ Pending"
                recur = task.recurrence.capitalize() if task.recurrence != "none" else "—"
                rows.append({
                    "Priority": f"{icon} {task.priority.capitalize()}",
                    "Task": task.name,
                    "Description": task.description,
                    "Due": str(task.due_date),
                    "Time": task.time.strftime("%I:%M %p"),
                    "Recurrence": recur,
                    "Status": status,
                })
            st.table(rows)

    # --- Mark complete ---
    st.divider()
    st.subheader("Mark Task Complete")
    all_pending = scheduler.build_schedule()
    if all_pending:
        # Build label -> (pet_name, task_name) mapping to handle same-named tasks across pets
        options = {}
        for pet in pets:
            for task in pet.get_tasks():
                if not task.completion_status:
                    label = f"{pet.name}: {task.name} ({task.due_date})"
                    options[label] = (pet.name, task.name)

        selected_label = st.selectbox("Select task to mark done", list(options.keys()))

        if st.button("Mark Complete"):
            pet_n, task_n = options[selected_label]
            next_task = scheduler.mark_task_complete(pet_n, task_n)
            st.success(f"'{task_n}' marked as complete.")
            if next_task is not None:
                st.info(
                    f"Recurring task auto-scheduled: '{next_task.name}' "
                    f"due {next_task.due_date} ({next_task.recurrence})"
                )
    else:
        st.info("No pending tasks to complete.")

    # --- Remove a task ---
    st.divider()
    st.subheader("Remove a Task")
    all_tasks_removable = {}
    for pet in pets:
        for task in pet.get_tasks():
            label = f"{pet.name}: {task.name} ({task.due_date})"
            all_tasks_removable[label] = (pet, task.name)

    if all_tasks_removable:
        task_to_remove = st.selectbox("Select task to remove", list(all_tasks_removable.keys()), key="remove_task_select")
        if st.button("Remove Task"):
            target_pet, target_task_name = all_tasks_removable[task_to_remove]
            target_pet.remove_task(target_task_name)
            st.rerun()
    else:
        st.info("No tasks to remove.")
