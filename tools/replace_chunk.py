import hashlib
from core.tool_result import ToolResult
from tools.file_reader import read_file
from tools.file_writer import write_file

def replace_chunk(path: str, target_code: str, replacement_code: str, content_signatures: set) -> ToolResult:
    """
    Replaces a specific chunk of text in a file.
    Takes content_signatures to prevent redundant writes (loops).
    """
    if replacement_code.startswith("```"):
        lines = replacement_code.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        replacement_code = "\n".join(lines)
        
    read_res = read_file(path)
    if not read_res.success:
        return read_res
        
    content = read_res.stdout
    if target_code not in content:
        return ToolResult(
            success=False, 
            stdout="", 
            stderr="Error: target_code not found in file."
        )
        
    updated_content = content.replace(target_code, replacement_code)
    content_hash = hashlib.sha256(updated_content.encode("utf-8")).hexdigest()
    file_content_sig = (path.lower(), content_hash)
    
    if file_content_sig in content_signatures:
        return ToolResult(
            success=False,
            stdout="",
            stderr="Error: Redundant chunk adjustment mutation. This resulting file configuration is already on disk."
        )
        
    write_res = write_file(path, updated_content)
    if not write_res.success:
        return write_res
        
    content_signatures.add(file_content_sig)
    
    return ToolResult(
        success=True,
        stdout=f"Successfully replaced:\n```\n{target_code}\n```\nwith:\n```\n{replacement_code}\n```",
        summary=f"Replaced chunk in {path}."
    )
