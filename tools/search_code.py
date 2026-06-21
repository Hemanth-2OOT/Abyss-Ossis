from tools.index_storage import search_index
from tools.context_builder import build_context

def search_code(session, query):
    matches = search_index(session, query)
    if not matches:
        return "No matches found."
    
    return build_context(matches)