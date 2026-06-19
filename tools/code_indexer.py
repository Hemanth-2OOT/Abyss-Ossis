import os
import ast
from core.sandbox import sandbox
from core.logger import get_logger

logger = get_logger(__name__)

IGNORE_DIRS = {"venv", "__pycache__", ".git", ".agents"}

class IndexVisitor(ast.NodeVisitor):
    def __init__(self, filename, source_lines):
        self.filename = filename
        self.source_lines = source_lines
        self.entities = []
        self.current_class = None
        self.current_function = None
        
    def _get_source(self, node):
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
            # AST lineno is 1-indexed
            return "\n".join(self.source_lines[node.lineno-1:node.end_lineno])
        return ""

    def visit_ClassDef(self, node):
        prev_class = self.current_class
        self.current_class = node.name
        
        docstring = ast.get_docstring(node) or ""
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        
        self.entities.append({
            "type": "class",
            "file": self.filename,
            "name": node.name,
            "methods": methods,
            "docstring": docstring,
            "source": self._get_source(node)
        })
        
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node):
        docstring = ast.get_docstring(node) or ""
        
        if self.current_class:
            self.entities.append({
                "type": "method",
                "file": self.filename,
                "class": self.current_class,
                "name": node.name,
                "docstring": docstring,
                "source": self._get_source(node)
            })
        else:
            self.entities.append({
                "type": "function",
                "file": self.filename,
                "name": node.name,
                "docstring": docstring,
                "source": self._get_source(node)
            })
            
        prev_func = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = prev_func

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Call(self, node):
        caller = self.current_function or self.current_class or "<module>"
        
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        else:
            callee = None
            
        if callee:
            self.entities.append({
                "type": "call",
                "file": self.filename,
                "name": callee,
                "caller": caller
            })
            
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.entities.append({
                "type": "import",
                "file": self.filename,
                "name": alias.name,
                "module": alias.name
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.entities.append({
                "type": "import",
                "file": self.filename,
                "name": alias.name,
                "module": module
            })
        self.generic_visit(node)


def build_index(root="."):
    index = []

    try:
        safe_root = sandbox.get_safe_path(root)
    except Exception as e:
        logger.error(f"Failed to resolve root {root} for indexing: {e}")
        return index

    for current_root, dirs, files in os.walk(safe_root):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            path = os.path.join(current_root, file)
            rel_path = os.path.relpath(path, safe_root).replace("\\", "/")

            try:
                mtime = os.path.getmtime(path)
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Fallback for ALL files
                index.append({
                    "type": "file",
                    "file": rel_path,
                    "mtime": mtime,
                    "content": content[:2000]
                })

                if file.endswith(".py"):
                    try:
                        tree = ast.parse(content)
                        visitor = IndexVisitor(rel_path, content.splitlines())
                        visitor.visit(tree)
                        index.extend(visitor.entities)
                    except SyntaxError:
                        logger.warning(f"Syntax error in {rel_path}, skipping AST")
            except Exception as e:
                logger.debug(f"Skipped unreadable file {rel_path}: {e}")

    return index

def index_single_file(path, root="."):
    index = []
    try:
        safe_root = sandbox.get_safe_path(root)
        safe_path = sandbox.get_safe_path(path)
    except Exception as e:
        logger.error(f"Failed to resolve path for indexing: {e}")
        return index

    if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
        return index
        
    rel_path = os.path.relpath(safe_path, safe_root).replace("\\", "/")
    
    try:
        mtime = os.path.getmtime(safe_path)
        with open(safe_path, "r", encoding="utf-8") as f:
            content = f.read()

        index.append({
            "type": "file",
            "file": rel_path,
            "mtime": mtime,
            "content": content[:2000]
        })

        if safe_path.endswith(".py"):
            try:
                tree = ast.parse(content)
                visitor = IndexVisitor(rel_path, content.splitlines())
                visitor.visit(tree)
                index.extend(visitor.entities)
            except SyntaxError:
                logger.warning(f"Syntax error in {rel_path}, skipping AST")
    except Exception as e:
        logger.debug(f"Skipped unreadable file {rel_path}: {e}")

    return index