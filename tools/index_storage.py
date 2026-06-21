import json
import os

# ── In-memory index cache (P1 fix) ──────────────────────────────────────────
# load_index() is called on every search_index() call. For a 200KB JSON index
# this causes a full disk read + parse every query. Cache keyed on mtime so
# stale data is never served when the index file changes on disk.
_index_cache: dict = {}   # {index_path: (mtime, data)}

def _build_lookup(index):
    """
    Build an inverted lookup: word → list of matching items.
    Constructed once per mtime epoch and stored in _index_cache alongside data.
    Reduces keyword scan from O(N×W) to O(W × avg_hits_per_word).
    """
    from collections import defaultdict
    lookup = defaultdict(list)
    for item in index:
        t = item.get("type", "")
        if t in ("function", "class", "method"):
            k = item.get("name", "").lower()
            if k:
                lookup[k].append(item)
        elif t == "call":
            for k in (item.get("name","").lower(), item.get("caller","").lower()):
                if k:
                    lookup[k].append(item)
        elif t == "import":
            for k in (item.get("name","").lower(), item.get("module","").lower()):
                if k:
                    lookup[k].append(item)
        elif t == "file":
            # file items matched by substring — kept in a separate flat list
            lookup["__files__"].append(item)
    return lookup


# extend cache tuple to (mtime, data, lookup)
def load_index(session):
    path = session.index_path
    if not os.path.exists(path):
        return []
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    cached = _index_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _index_cache[path] = (mtime, data)
    return data


def _get_lookup(session):
    path = session.index_path
    cached = _index_cache.get(path)
    if cached and len(cached) == 3:
        return cached[2]
    # build and store lookup alongside existing cache entry
    index = load_index(session)
    lookup = _build_lookup(index)
    if path in _index_cache:
        _index_cache[path] = (_index_cache[path][0], _index_cache[path][1], lookup)
    return lookup


def save_index(session, index):
    os.makedirs(os.path.dirname(session.index_path), exist_ok=True)
    with open(session.index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    # Invalidate cache so next load_index reads the freshly written file.
    _index_cache.pop(session.index_path, None)


def update_file_index(session, path):
    from tools.code_indexer import index_single_file
    from core.sandbox import sandbox
    from systems.semantic_index import (
        remove_entities_from_faiss,
        add_entities_to_faiss
    )

    try:
        safe_root = sandbox.get_safe_path(session.root)
        safe_path = sandbox.get_safe_path(path)
        rel_path = os.path.relpath(
            safe_path,
            safe_root
        ).replace("\\", "/")

    except Exception:
        return

    index = load_index(session)

    old_entities = [
        item
        for item in index
        if item.get("file") == rel_path
    ]

    index = [
        item
        for item in index
        if item.get("file") != rel_path
    ]

    if old_entities:
        remove_entities_from_faiss(old_entities)

    new_entities = index_single_file(path)

    if new_entities:
        index.extend(new_entities)
        add_entities_to_faiss(new_entities)

    save_index(session, index)


def search_index(session, query):
    index = load_index(session)

    words = query.lower().replace("?", "").split()

    stop_words = {
        "where",
        "is",
        "the",
        "a",
        "an",
        "defined",
        "what",
        "how",
        "why",
        "who",
        "calls",
        "which",
        "files",
        "import"
    }

    words = [
        w
        for w in words
        if w not in stop_words and len(w) > 2
    ]

    ast_matches = []
    file_matches = []

    # Fast O(W x hits) lookup instead of O(W x N) loop
    lookup = _get_lookup(session)
    seen_entity_idx = set()

    for word in words:
        # Match exact keyword
        if word in lookup:
            for item in lookup[word]:
                idx = id(item)
                if idx not in seen_entity_idx:
                    seen_entity_idx.add(idx)
                    ast_matches.append(item)
        
        # Match file substrings
        for f_item in lookup.get("__files__", []):
            if word in f_item.get("file", "").lower():
                idx = id(f_item)
                if idx not in seen_entity_idx:
                    seen_entity_idx.add(idx)
                    file_matches.append(f_item)

    from systems.semantic_index import (
        search_semantic,
        generate_entity_id
    )

    semantic_matches = search_semantic(index, query, top_k=3)
    merged = ast_matches.copy()

    seen_ids = {
        generate_entity_id(item)
        for item in merged
    }

    for item in semantic_matches:
        item_id = generate_entity_id(item)

        if item_id not in seen_ids:
            merged.append(item)
            seen_ids.add(item_id)

    for item in file_matches:
        item_id = generate_entity_id(item)

        if item_id not in seen_ids:
            merged.append(item)
            seen_ids.add(item_id)

    return merged