# PawPal+ Architecture

PawPal+ is a Streamlit app for planning pet-care tasks, with an AI assistant
layered on top of a plain-Python domain model. Data persists to CSV files.
This document diagrams the system from four angles: layers, domain model,
runtime flows, and file layout.

## 1. System layers

```mermaid
flowchart TB
    subgraph UI["UI Layer (Streamlit)"]
        app["app.py<br/>page router + session state"]
        main_page["views/main_page.py<br/>owner/pet/task CRUD, schedule table"]
        ai_page["views/ai_assistant.py<br/>chat UI"]
        common["views/common.py<br/>load_owner_cached"]
    end

    subgraph Domain["Domain Layer (pawpal_system.py)"]
        Owner["Owner"]
        Pet["Pet"]
        Task["Task"]
        Scheduler["Scheduler<br/>sort / filter / conflicts / recurrence"]
    end

    subgraph AI["AI Layer"]
        retriever["pet_retriever.py<br/>PetRetriever (chunk + score)"]
        llm["llm_client.py<br/>GeminiClient (RAG + function calling)"]
    end

    subgraph Persistence["Persistence"]
        storage["storage.py<br/>save_owner / load_owner / data_version"]
        csv[("data/*.csv<br/>owners, pets, tasks")]
    end

    subgraph External["External Service"]
        gemini(["Google Gemini API<br/>gemini-3.5-flash"])
    end

    app --> main_page
    app --> ai_page
    main_page --> common
    ai_page --> common
    common --> storage

    main_page --> Scheduler
    Scheduler --> Owner
    Owner --> Pet
    Pet --> Task

    ai_page --> retriever
    ai_page --> llm
    retriever --> Owner
    retriever --> Scheduler
    llm --> Owner
    llm --> Scheduler
    llm --> gemini

    main_page --> storage
    storage --> csv
```

**Notes**
- `app.py` only wires up navigation and session state; it holds no business logic.
- The domain layer (`pawpal_system.py`) has zero dependency on Streamlit or Gemini — it's pure Python and is what `tests/test_pawpal.py` exercises directly.
- The AI layer depends on the domain layer (it reads/mutates `Owner`/`Scheduler`) but the domain layer has no reverse dependency, so PawPal+ works fully without an API key (AI Assistant page just can't run).
- `storage.py` is the only module that touches the filesystem for app data; CSVs are the source of truth and the in-memory `Owner` graph is rebuilt from them on every rerun.

## 2. Domain model (class diagram)

```mermaid
classDiagram
    class Owner {
        +String name
        +List~Pet~ pets
        +add_pet(pet) None
        +remove_pet(pet_name) None
        +get_pets() List~Pet~
    }

    class Pet {
        +String name
        +String species
        +List~Task~ tasks
        +add_task(task) None
        +remove_task(task_name) None
        +get_tasks() List~Task~
    }

    class Task {
        +String name
        +time time
        +String priority
        +String description
        +bool completion_status
        +String recurrence
        +date due_date
        +mark_complete() Task
    }

    class Scheduler {
        +Owner owner
        +build_schedule(sort_key) List~Task~
        +sort_tasks(tasks, key) List~Task~
        +filter_by_pet(pet_name, sort_key) List~Task~
        +filter_by_status(completed) List~Task~
        +get_conflicts() List~str~
        +mark_task_complete(pet_name, task_name) Task
    }

    Owner "1" --> "0..*" Pet : owns
    Pet "1" --> "0..*" Task : has
    Scheduler "1" --> "1" Owner : reads/mutates
    Task ..> Task : mark_complete()\ncreates next occurrence
```

`Scheduler` is stateless business logic over an `Owner`'s pet/task graph: it
never stores its own copy of tasks, it always recomputes from
`owner.get_pets()`. Recurrence (`daily`/`weekly`) is modeled by
`Task.mark_complete()` returning a brand-new `Task` for the next occurrence
rather than mutating dates in place.

## 3. Data flow: load / edit / save cycle

```mermaid
flowchart LR
    csv[("data/*.csv")] -->|"load_owner()"| storage[storage.py]
    storage -->|"builds"| owner((Owner graph))
    owner -->|"cached by (name, data_version)"| cache["st.cache_data\nviews/common.py"]
    cache --> ui["Streamlit page\n(main_page / ai_assistant)"]
    ui -->|"user adds/edits/removes\npet, task, or marks complete"| owner
    owner -->|"save_owner()"| storage
    storage -->|"overwrites this owner's rows"| csv
    storage -.->|"bumps mtime -> new data_version"| cache
```

Because the cache key includes `storage.data_version()` (a max mtime across
the three CSVs), any save invalidates the cache automatically — there's no
manual cache-busting logic, and every Streamlit rerun rebuilds the object
graph fresh from disk rather than trusting session state to stay in sync.

## 4. AI Assistant: RAG flow (`answer_from_snippets`)

```mermaid
sequenceDiagram
    actor User
    participant UI as ai_assistant.py
    participant Retr as PetRetriever
    participant LLM as GeminiClient
    participant Gemini as Gemini API

    User->>UI: types a question in chat
    UI->>Retr: PetRetriever(owner)
    Retr->>Retr: build_chunks(owner)\n(summary + per-pet + per-task + conflicts)
    UI->>Retr: read retriever.chunks
    alt no chunks at all
        UI-->>User: "I do not know based on the current schedule."
    else chunks exist
        UI->>LLM: answer_from_snippets(query, snippets)
        LLM->>LLM: build prompt: rules + retrieved records + question
        LLM->>Gemini: generate_content(prompt)
        alt transient ServerError
            LLM->>LLM: retry with backoff (up to 3x)
            LLM->>Gemini: retry generate_content
        end
        Gemini-->>LLM: model response
        LLM-->>UI: answer text (or raises GeminiAPIError)
        UI-->>User: render answer / error in chat
    end
```

The assistant currently passes **all** of an owner's chunks as context
(rather than a filtered top-k) — a deliberate choice noted in
`views/ai_assistant.py` because one owner's dataset is small enough that
narrowing context via retrieval caused false refusals. `PetRetriever.retrieve`
and `has_sufficient_evidence` remain available for narrower lookups.

## 5. AI Assistant: agentic action flow (`run_action`, function calling)

```mermaid
sequenceDiagram
    actor User
    participant LLM as GeminiClient.run_action
    participant Gemini as Gemini API
    participant Sched as Scheduler
    participant Owner as Owner/Pet (in memory)
    participant Store as storage.save_owner

    User->>LLM: natural-language request\n("add a daily 7am walk for Mochi")
    LLM->>LLM: _describe_schedule(owner) -> plain-text context
    LLM->>Gemini: generate_content(prompt, tools=[add_pet, remove_pet,\nadd_task, remove_task,\nmark_task_complete, get_conflicts])
    Gemini-->>LLM: decides to call one or more tool functions
    LLM->>Owner: closure mutates owner/pet in place\n(e.g. pet.add_task(...))
    opt request involves completing a task
        LLM->>Sched: mark_task_complete(pet_name, task_name)
        Sched-->>Owner: appends recurring next-occurrence Task
    end
    Gemini-->>LLM: final text describing what it did
    LLM-->>User: response text
    Note over LLM,Store: caller (views/ai_assistant.py or main_page.py)\nis responsible for storage.save_owner(owner) afterward
```

The six tool functions (`add_pet`, `remove_pet`, `add_task`, `remove_task`,
`mark_task_complete`, `get_conflicts`) are plain Python closures bound to one
specific `owner`, passed straight to Gemini's `tools=` config — Gemini
decides which to call based on the request, and `run_action` mutates the
real `Owner` object graph as a side effect.

## 6. Error handling in the LLM layer

```mermaid
flowchart TD
    call["GeminiClient._generate_content()"] --> try["client.models.generate_content()"]
    try -->|success| ok["return response.text"]
    try -->|"ServerError (e.g. 503)"| retry{"attempt < 3?"}
    retry -->|yes| backoff["sleep 2^(n-1) sec"] --> try
    retry -->|no| serverErr["raise GeminiAPIError\n(overloaded, user-facing message)"]
    try -->|"ClientError 429"| quotaErr["raise GeminiAPIError\n(rate/quota limit, not retried)"]
    try -->|"ClientError other"| clientErr["raise GeminiAPIError\n(request rejected)"]
    try -->|"any other Exception"| unexpectedErr["raise GeminiAPIError\n(unexpected error)"]
```

`GeminiAPIError` messages are written to be shown directly to the end user
(not swallowed as an internal detail), so callers in the UI layer just catch
it and render `str(e)`.

## 7. Project file layout

```mermaid
flowchart TB
    root["applied-ai-system-project/"]
    root --> app_py["app.py — Streamlit entrypoint, page router"]
    root --> main_py["main.py — CLI demo of Scheduler (no Streamlit/AI)"]
    root --> pawpal["pawpal_system.py — Owner, Pet, Task, Scheduler"]
    root --> storage_py["storage.py — CSV persistence"]
    root --> retriever_py["pet_retriever.py — PetRetriever (RAG chunking/scoring)"]
    root --> llm_py["llm_client.py — GeminiClient (RAG + function-calling agent)"]
    root --> views["views/"]
    views --> vmain["main_page.py — owner/pet/task CRUD + schedule UI"]
    views --> vai["ai_assistant.py — chat UI"]
    views --> vcommon["common.py — load_owner_cached (shared cache)"]
    root --> data["data/"]
    data --> owners_csv["owners.csv"]
    data --> pets_csv["pets.csv"]
    data --> tasks_csv["tasks.csv"]
    root --> tests["tests/test_pawpal.py — Scheduler/Task unit tests"]
    root --> diagrams["diagrams/ — uml_draft.mmd, uml_final.mmd, architecture.md"]
    root --> reflection["reflection.md, ai_interactions.md, README.md"]
    root --> env[".env — API_KEY for Gemini"]
```
