from tools.index_storage import search_index
from tools.context_builder import build_context

def search_code(query):
    matches = search_index(query)
    if not matches:
        return "No matches found."
    
    return build_context(matches)
