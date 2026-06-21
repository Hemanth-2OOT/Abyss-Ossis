import os
import faiss
import numpy as np
import hashlib
from tools.embedder import embed_text
from core.logger import get_logger

logger = get_logger(__name__)

FAISS_INDEX_FILE = "data/faiss_index.bin"
DIMENSION = 768  # nomic-embed-text

_faiss_index = None

def get_faiss_index():
    global _faiss_index
    if _faiss_index is None:
        if os.path.exists(FAISS_INDEX_FILE):
            try:
                _faiss_index = faiss.read_index(FAISS_INDEX_FILE)
            except Exception:
                pass
        
        if _faiss_index is None:
            flat = faiss.IndexFlatL2(DIMENSION)
            _faiss_index = faiss.IndexIDMap(flat)
            
    return _faiss_index

def save_faiss_index():
    global _faiss_index
    if _faiss_index is not None:
        os.makedirs(os.path.dirname(FAISS_INDEX_FILE), exist_ok=True)
        faiss.write_index(_faiss_index, FAISS_INDEX_FILE)

def generate_entity_id(item):
    # B1 fix: include 'class' so methods with the same name in the same file
    # (e.g. two classes both having a 'run' method) get distinct IDs.
    unique_str = (
        f"{item.get('file', '')}_"
        f"{item.get('type', '')}_"
        f"{item.get('class', '')}_"
        f"{item.get('name', item.get('module', ''))}"
    )
    return int(hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:15], 16)

def build_entity_text(item):
    item_type = item.get("type", "")
    if item_type in ("function", "method"):
        return f"Function/Method {item.get('name', '')}\nDocstring: {item.get('docstring', '')}\nSource: {item.get('source', '')}"
    elif item_type == "class":
        return f"Class {item.get('name', '')}\nDocstring: {item.get('docstring', '')}\nMethods: {', '.join(item.get('methods', []))}\nSource: {item.get('source', '')}"
    elif item_type == "call":
        return f"Function call: '{item.get('caller', '')}' calls '{item.get('name', '')}'"
    elif item_type == "import":
        return f"Import: '{item.get('name', '')}' from module '{item.get('module', '')}'"
    elif item_type == "file":
        return f"File {item.get('file', '')}\nContent snippet: {item.get('content', '')}"
    return str(item)

def add_entities_to_faiss(entities):
    if not entities:
        return
        
    faiss_idx = get_faiss_index()
    
    texts = [build_entity_text(e) for e in entities]
    ids = [generate_entity_id(e) for e in entities]
    
    embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        emb = embed_text(batch)
        if emb:
            embeddings.extend(emb)
        else:
            raise RuntimeError(f"Embedding generation failed for batch. Aborting to prevent FAISS corruption.")
            
    embeddings_np = np.array(embeddings, dtype=np.float32)
    ids_np = np.array(ids, dtype=np.int64)

    # Upsert guard: IndexIDMap does NOT replace on duplicate ID — both vectors
    # persist, corrupting search ranking. Remove any pre-existing vectors with
    # these IDs before inserting so add_with_ids is always a true upsert.
    try:
        faiss_idx.remove_ids(ids_np)
    except Exception:
        pass  # index may not support remove_ids if it has no entries yet

    faiss_idx.add_with_ids(embeddings_np, ids_np)
    save_faiss_index()

def remove_entities_from_faiss(entities):
    if not entities:
        return
    faiss_idx = get_faiss_index()
    ids = [generate_entity_id(e) for e in entities]
    ids_np = np.array(ids, dtype=np.int64)
    faiss_idx.remove_ids(ids_np)
    save_faiss_index()

def sync_faiss_with_ast(entities, force_rebuild=True):
    """
    Syncs the FAISS index with the supplied AST entities.

    force_rebuild=True  (default, used by /index command):
        Wipes the in-memory index and rebuilds from scratch.
    force_rebuild=False (used by incremental update_file_index):
        Appends new entities without destroying existing vectors.
        Callers are responsible for removing stale entities first via
        remove_entities_from_faiss() before calling this.

    B9 fix: the old implementation always replaced _faiss_index with an
    empty index, causing the in-memory state to diverge from the on-disk
    .bin file when called mid-session.
    """
    global _faiss_index

    if force_rebuild:
        flat = faiss.IndexFlatL2(DIMENSION)
        _faiss_index = faiss.IndexIDMap(flat)

    add_entities_to_faiss(entities)

def search_semantic(entities, query, top_k=3):
    """
    Performs similarity search over vector mappings and cross-references matching elements
    against the provided entities collection context wrapper.
    """
    faiss_idx = get_faiss_index()
    if faiss_idx.ntotal == 0 or not entities:
        return []
        
    q_emb = embed_text([query])
    if not q_emb:
        return []
        
    q_emb_np = np.array(q_emb, dtype=np.float32)
    _, indices = faiss_idx.search(q_emb_np, top_k)
    
    target_ids = set(indices[0])
    
    results = []
    for item in entities:
        if generate_entity_id(item) in target_ids:
            results.append(item)
            
    return results