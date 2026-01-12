# Code-Editing Agent

A simple yet powerful code-editing agent built with Python and the Anthropic API. This agent can read files, list directories, and edit files based on natural language instructions.

## The Core Insight

**An "agent" is simply an LLM with access to tools, running in a loop.**

There's no magic here. The agent:
1. Receives user input
2. Sends it to Claude along with available tool definitions
3. If Claude wants to use a tool, executes it and sends the result back
4. If Claude responds with text, prints it and waits for more input
5. Repeats

That's it. Everything else is just polish.

## Features

- **`read_file`**: Read the contents of any file
- **`list_files`**: List files and directories 
- **`edit_file`**: Edit files by string replacement (or create new files)

With just these three tools, Claude can:
- Explore codebases
- Understand project structure
- Create new files
- Modify existing code
- Fix bugs
- Implement features

## Installation

### Prerequisites

- Python 3.8 or higher
- [uv](https://docs.astral.sh/uv/) - An extremely fast Python package installer and resolver
- An [Anthropic API key](https://console.anthropic.com/settings/keys)

### Setup

1. **Install uv (if you haven't already):**
   ```bash
   # On macOS and Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # On Windows
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

   # Or with pip
   pip install uv
   ```

2. **Clone or create the project directory:**
   ```bash
   mkdir code-editing-agent
   cd code-editing-agent
   ```

3. **Install dependencies:**
   ```bash
   uv sync
   ```

   This will automatically:
   - Create a virtual environment
   - Install all dependencies from `pyproject.toml`
   - Generate a `uv.lock` file for reproducible installs

4. **Configure your API key:**

   Copy the `.env.example` file to `.env` and add your actual API key:
   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and replace `your-api-key-here` with your actual [Anthropic API key](https://console.anthropic.com/settings/keys).

5. **Download the source files** (`agent.py` and `tools.py`) or copy them from this repository.

## Usage

Run the agent from the directory where you want it to work:

```bash
uv run agent.py
```

Or activate the virtual environment first:

```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python agent.py
```

Then just chat naturally:

```
Chat with Claude (use 'ctrl-c' to quit)

You: What files are in this directory?
tool: list_files({})
Claude: I can see the following files...

You: Show me what's in main.py
tool: read_file({"path":"main.py"})
Claude: Here's what's in main.py...

You: Add a docstring to the main function
tool: read_file({"path":"main.py"})
tool: edit_file({"path":"main.py","old_str":"def main():","new_str":"def main():\n    \"\"\"Entry point for the application.\"\"\""})
Claude: I've added a docstring to the main function.
```

## Project Structure

```
code-editing-agent/
├── agent.py          # Main agent implementation
├── tools.py          # Tool definitions (read_file, list_files, edit_file)
├── pyproject.toml    # Project metadata and dependencies
├── requirements.txt  # Legacy pip dependencies (for compatibility)
├── .env              # Your API key (don't commit this!)
├── .env.example      # Example .env file (safe to commit)
└── README.md         # This file
```

## How It Works

### The Agent Loop

```python
while True:
    # 1. Get user input
    user_message = get_input()
    conversation.append(user_message)
    
    # 2. Send to Claude with available tools
    response = claude.messages.create(
        messages=conversation,
        tools=available_tools
    )
    
    # 3. Process response
    for block in response.content:
        if block.type == "text":
            print(block.text)  # Show Claude's response
        elif block.type == "tool_use":
            result = execute_tool(block)  # Run the tool
            conversation.append(result)   # Add result to context
            continue  # Go back to Claude without user input
```

### Tool Definitions

Each tool has four parts:

1. **Name**: How Claude refers to it
2. **Description**: Tells Claude when/how to use it
3. **Input Schema**: JSON Schema for parameters
4. **Function**: The actual implementation

Example:
```python
ToolDefinition(
    name="read_file",
    description="Read the contents of a file. Use when you need to see what's inside a file.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"}
        },
        "required": ["path"]
    },
    function=read_file_function
)
```

### Why String Replacement for Editing?

The `edit_file` tool uses simple string replacement (`old_str` → `new_str`). This might seem primitive, but:

1. **Claude is excellent at it**: Models are trained extensively on text manipulation
2. **It's predictable**: No complex diff algorithms needed
3. **It's debuggable**: You can see exactly what's being replaced
4. **It works**: More sophisticated approaches often aren't better

## Extending the Agent

### Adding New Tools

1. Create a function that takes a `dict` and returns a `str`:
   ```python
   def my_tool(params: dict) -> str:
       # Do something
       return "result"
   ```

2. Define the input schema:
   ```python
   my_tool_schema = {
       "type": "object",
       "properties": {
           "param1": {"type": "string", "description": "..."}
       },
       "required": ["param1"]
   }
   ```

3. Create the tool definition:
   ```python
   my_tool_definition = ToolDefinition(
       name="my_tool",
       description="What it does and when to use it",
       input_schema=my_tool_schema,
       function=my_tool
   )
   ```

4. Add it to the tools list in `agent.py`:
   ```python
   tools = [
       read_file_definition,
       list_files_definition,
       edit_file_definition,
       my_tool_definition,  # Add here
   ]
   ```

### Tool Ideas

- **`run_command`**: Execute shell commands
- **`search_files`**: Search for text across files
- **`git_status`**: Check git repository status
- **`run_tests`**: Execute test suites
- **`web_search`**: Search the internet for information

## Security Considerations

⚠️ **This agent can read and modify files!**

- Run it only in directories where you trust it to make changes
- Consider adding path restrictions to prevent access outside the working directory
- Be careful with a `run_command` tool - it could execute arbitrary code
- Never commit your `.env` file

## Troubleshooting

### Authentication Error (401 - invalid x-api-key)

If you get an authentication error even with a valid API key, you may have an old `ANTHROPIC_API_KEY` set in your shell environment. The agent uses `load_dotenv(override=True)` to ensure the `.env` file takes precedence, but if you still have issues:

1. Check your shell environment:
   ```bash
   echo $ANTHROPIC_API_KEY
   ```

2. If it shows an old key, unset it:
   ```bash
   unset ANTHROPIC_API_KEY
   ```

3. Then run the agent again with `uv run python agent.py`

The `.env` file should now be loaded correctly.

## Differences from the Original Go Version

This Python implementation is functionally equivalent but:

- Uses `uv` for fast, reliable dependency management
- Uses `python-dotenv` for environment variable loading
- Uses Python's `pathlib` for file operations
- Uses dataclasses for type definitions
- Has more detailed comments explaining the concepts

## License

MIT License - Use freely, but at your own risk.
