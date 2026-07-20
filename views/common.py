from typing import Optional

import streamlit as st

import storage
from pawpal_system import Owner


@st.cache_data
def load_owner_cached(name: str, version: float) -> Optional[Owner]:
    """
    Load an owner from CSV, cached per (name, version).

    `version` is a CSV-mtime stamp (see storage.data_version), so this cache
    is reused across reruns that don't touch the CSVs and is automatically
    invalidated the moment a save changes them — no manual cache-busting.
    Shared by every page so the cache key stays the same regardless of
    which page triggers the load.
    """
    return storage.load_owner(name)
