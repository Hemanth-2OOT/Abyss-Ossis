import os

def delete_file(path: str) -> dict:
    """
    Deletes a file.
    
    Args:
        path (str): The absolute or relative path to the file to delete.
    
    Returns:
        dict: A result dictionary indicating success or failure.
    """
    try:
        if not os.path.exists(path):
            return {
                "success": False,
                "status": "failed",
                "stdout": "",
                "stderr": f"File not found: {path}",
                "summary": f"Could not find {path} to delete."
            }
            
        if os.path.isdir(path):
            return {
                "success": False,
                "status": "failed",
                "stdout": "",
                "stderr": f"Target is a directory, not a file: {path}",
                "summary": f"Cannot delete directory {path} with delete_file."
            }
            
        os.remove(path)
        
        return {
            "success": True,
            "status": "completed",
            "stdout": f"Deleted file: {path}",
            "stderr": "",
            "summary": f"Successfully deleted {path}"
        }
    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "summary": f"Error deleting file: {str(e)}"
        }
