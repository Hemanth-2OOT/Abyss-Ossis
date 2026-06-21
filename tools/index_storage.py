import json
import os

def save_index(session, index):
    os.makedirs(os.path.dirname(session.index_path), exist_ok=True)

    with open(session.index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def load_index(session):
    if not os.path.exists(session.index_path):
        return []

    with open(session.index_path, "r", encoding="utf-8") as f:
        return json.load(f)


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

    for item in index:
        found = False
        item_type = item.get("type", "")

        for word in words:

            if item_type in ("function", "class", "method"):
                if word == item.get("name", "").lower():
                    found = True

            elif item_type == "call":
                if (
                    word == item.get("name", "").lower()
                    or word == item.get("caller", "").lower()
                ):
                    found = True

            elif item_type == "import":
                if (
                    word == item.get("name", "").lower()
                    or word == item.get("module", "").lower()
                ):
                    found = True

            elif item_type == "file":
                if word in item.get("file", "").lower():
                    found = True

        if found:
            if item_type == "file":
                file_matches.append(item)
            else:
                ast_matches.append(item)

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