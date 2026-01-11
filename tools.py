"""
Tool Definitions for the Code-Editing Agent
============================================

This module defines the tools that Claude can use to interact with the
file system. Each tool consists of:

1. A name (how Claude refers to it)
2. A description (tells Claude when and how to use it)
3. An input schema (JSON schema defining expected parameters)
4. A function (the actual Python code that executes the tool)

The key insight here is that Claude reads the descriptions to understand
WHEN to use each tool. Good descriptions are crucial for good behavior.

Tools in this module:
- read_file: Read the contents of a file
- list_files: List files and directories
- edit_file: Edit files by string replacement
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# =============================================================================
# TOOL DEFINITION DATA CLASS
# =============================================================================

@dataclass
class ToolDefinition:
    """
    A complete definition of a tool that Claude can use.
    
    Attributes:
        name: The unique identifier for this tool. Claude uses this name
              when it wants to invoke the tool.
        
        description: A natural language description of what the tool does,
                     when to use it, and any important caveats. This is
                     CRUCIAL - Claude reads this to decide when to use
                     the tool. Be specific and clear!
        
        input_schema: A JSON Schema object describing the expected input
                      parameters. This tells Claude what arguments to
                      provide and in what format.
        
        function: The Python function that actually executes the tool.
                  It receives a dict of parameters (matching input_schema)
                  and returns a string result.
    """
    name: str
    description: str
    input_schema: dict[str, Any]
    function: Callable[[dict[str, Any]], str]


# =============================================================================
# READ FILE TOOL
# =============================================================================

def read_file(params: dict[str, Any]) -> str:
    """
    Read and return the contents of a file.
    
    This is one of the most fundamental tools - it lets Claude "see"
    what's inside files. Without this, Claude would be working blind.
    
    Args:
        params: A dict containing:
            - path (str): The relative path to the file to read
    
    Returns:
        The contents of the file as a string
    
    Raises:
        FileNotFoundError: If the file doesn't exist
        PermissionError: If we don't have read access
        IsADirectoryError: If the path is a directory, not a file
    """
    file_path = params.get("path", "")
    
    if not file_path:
        raise ValueError("No file path provided")
    
    # Read the file and return its contents
    # We use Path for better cross-platform compatibility
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if path.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {file_path}")
    
    # Read with UTF-8 encoding (standard for most code files)
    return path.read_text(encoding="utf-8")


# The input schema tells Claude what parameters this tool expects.
# This follows JSON Schema format (https://json-schema.org/)
read_file_input_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The relative path of a file in the working directory."
        }
    },
    "required": ["path"]
}

# The complete tool definition
# Note the description: it tells Claude exactly when to use this tool
read_file_definition = ToolDefinition(
    name="read_file",
    description=(
        "Read the contents of a given relative file path. "
        "Use this when you want to see what's inside a file. "
        "Do not use this with directory names."
    ),
    input_schema=read_file_input_schema,
    function=read_file,
)


# =============================================================================
# LIST FILES TOOL
# =============================================================================

def list_files(params: dict[str, Any]) -> str:
    """
    List all files and directories at a given path.
    
    This is Claude's way of "looking around" the file system. It's often
    the first tool Claude uses when starting a task - just like how you
    might run 'ls' when you open a new terminal.
    
    Args:
        params: A dict containing:
            - path (str, optional): The directory to list. Defaults to "."
    
    Returns:
        A JSON-encoded list of file and directory names.
        Directories have a trailing "/" to distinguish them from files.
    
    Note:
        We return JSON because it's easy for Claude to parse and understand.
        We could return plain text, but JSON is more structured.
    """
    # Get the directory path, default to current directory
    dir_path = params.get("path", ".") or "."
    
    path = Path(dir_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")
    
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {dir_path}")
    
    # Collect all files and directories
    # We walk the directory tree to get everything
    files = []
    
    for root, dirs, filenames in os.walk(dir_path):
        # Calculate relative path from the starting directory
        rel_root = os.path.relpath(root, dir_path)
        
        # Skip the current directory marker
        if rel_root == ".":
            rel_root = ""
        
        # Add directories (with trailing slash)
        for d in dirs:
            if rel_root:
                files.append(f"{rel_root}/{d}/")
            else:
                files.append(f"{d}/")
        
        # Add files
        for f in filenames:
            if rel_root:
                files.append(f"{rel_root}/{f}")
            else:
                files.append(f)
    
    # Return as JSON for easy parsing
    return json.dumps(files, indent=2)


list_files_input_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": (
                "Optional relative path to list files from. "
                "Defaults to current directory if not provided."
            )
        }
    },
    "required": []  # path is optional
}

list_files_definition = ToolDefinition(
    name="list_files",
    description=(
        "List files and directories at a given path. "
        "If no path is provided, lists files in the current directory."
    ),
    input_schema=list_files_input_schema,
    function=list_files,
)


# =============================================================================
# EDIT FILE TOOL
# =============================================================================

def edit_file(params: dict[str, Any]) -> str:
    """
    Edit a file by replacing one string with another.
    
    This is the most powerful tool - it lets Claude actually modify files.
    The implementation uses string replacement, which Claude is very good at.
    
    The approach is simple:
    1. Find the exact "old_str" in the file
    2. Replace it with "new_str"
    3. Write the result back
    
    If old_str is empty and the file doesn't exist, create a new file
    with new_str as its content.
    
    Args:
        params: A dict containing:
            - path (str): The file to edit or create
            - old_str (str): The text to find and replace
            - new_str (str): The text to replace it with
    
    Returns:
        "OK" on success, or a descriptive message for file creation
    
    Notes:
        - old_str must match exactly (including whitespace)
        - If old_str appears multiple times, ALL occurrences are replaced
        - If old_str is empty and file doesn't exist, file is created
    """
    file_path = params.get("path", "")
    old_str = params.get("old_str", "")
    new_str = params.get("new_str", "")
    
    # Validate input
    if not file_path:
        raise ValueError("No file path provided")
    
    if old_str == new_str:
        raise ValueError("old_str and new_str must be different")
    
    path = Path(file_path)
    
    # Handle file creation case
    if not path.exists():
        if old_str == "":
            # Create new file with new_str as content
            return create_new_file(file_path, new_str)
        else:
            raise FileNotFoundError(f"File not found: {file_path}")
    
    # Read the current content
    content = path.read_text(encoding="utf-8")
    
    # Check if old_str exists in the file
    if old_str and old_str not in content:
        raise ValueError(f"old_str not found in file: {file_path}")
    
    # Perform the replacement
    # Note: This replaces ALL occurrences of old_str
    new_content = content.replace(old_str, new_str)
    
    # Write the modified content back
    path.write_text(new_content, encoding="utf-8")
    
    return "OK"


def create_new_file(file_path: str, content: str) -> str:
    """
    Create a new file with the given content.
    
    This is a helper function used by edit_file when the file doesn't
    exist and old_str is empty.
    
    Args:
        file_path: Path to the new file (may include directories)
        content: The content to write to the file
    
    Returns:
        A success message
    """
    path = Path(file_path)
    
    # Create parent directories if they don't exist
    # This is convenient for creating files in new directories
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the content
    path.write_text(content, encoding="utf-8")
    
    return f"Successfully created file {file_path}"


edit_file_input_schema = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "The path to the file"
        },
        "old_str": {
            "type": "string",
            "description": (
                "Text to search for - must match exactly and must only "
                "have one match exactly"
            )
        },
        "new_str": {
            "type": "string",
            "description": "Text to replace old_str with"
        }
    },
    "required": ["path", "old_str", "new_str"]
}

edit_file_definition = ToolDefinition(
    name="edit_file",
    description="""Make edits to a text file.

Replaces 'old_str' with 'new_str' in the given file. 'old_str' and 'new_str' MUST be different from each other.

If the file specified with path doesn't exist, it will be created.
""",
    input_schema=edit_file_input_schema,
    function=edit_file,
)


# =============================================================================
# EXPORTS
# =============================================================================

# All tool definitions in a list for easy import
all_tools = [
    read_file_definition,
    list_files_definition,
    edit_file_definition,
]
