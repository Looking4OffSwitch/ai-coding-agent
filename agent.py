#!/usr/bin/env python3
"""
Code-Editing Agent
==================

A simple yet powerful code-editing agent built with the Anthropic API.
This agent can read files, list directories, and edit files based on
natural language instructions.

This is a Python port of the Go implementation from:
https://ampcode.com/how-to-build-an-agent

The core insight: an "agent" is simply an LLM with access to tools,
running in a loop. The LLM decides when to use tools based on the
conversation context, and we execute those tools and feed the results
back to the LLM. That's it. No magic.

Usage:
    python agent.py

Requirements:
    - Python 3.8+
    - anthropic package
    - python-dotenv package
    - ANTHROPIC_API_KEY in .env file or environment
"""

import json
import os
import sys
from typing import Callable, Optional

# Third-party imports
from dotenv import load_dotenv
import anthropic

# Local imports - our tool definitions
from tools import (
    ToolDefinition,
    read_file_definition,
    list_files_definition,
    edit_file_definition,
)


# =============================================================================
# AGENT CLASS
# =============================================================================

class Agent:
    """
    The Agent class is the heart of our code-editing assistant.
    
    It maintains:
    - A connection to the Anthropic API (the "brain")
    - A list of available tools (the "hands")
    - A function to get user input (the "ears")
    
    The agent runs in a loop:
    1. Get user input
    2. Send the conversation to Claude
    3. If Claude wants to use a tool, execute it and send the result back
    4. If Claude responds with text, print it and wait for more input
    5. Repeat
    
    This is fundamentally how ALL AI agents work. The sophistication
    comes from the tools you provide and how you handle edge cases.
    """
    
    def __init__(
        self,
        client: anthropic.Anthropic,
        get_user_message: Callable[[], Optional[str]],
        tools: list[ToolDefinition],
    ):
        """
        Initialize the Agent.
        
        Args:
            client: An initialized Anthropic API client. This handles
                    all communication with Claude.
            
            get_user_message: A function that returns the next user message,
                              or None if the user wants to quit. This
                              abstraction lets us easily swap stdin for
                              other input sources (tests, GUI, etc.)
            
            tools: A list of ToolDefinition objects. Each tool has:
                   - name: What Claude calls it
                   - description: When/how to use it (Claude reads this!)
                   - input_schema: JSON schema for the tool's parameters
                   - function: The actual Python function to execute
        """
        self.client = client
        self.get_user_message = get_user_message
        self.tools = tools
    
    def run(self) -> None:
        """
        The main agent loop.
        
        This is where the magic happens - but it's surprisingly simple:
        
        1. We maintain a conversation history (list of messages)
        2. We send this history to Claude with each request
        3. Claude's response either contains text or tool requests
        4. For text: print it and wait for user input
        5. For tool requests: execute them, add results to history, repeat
        
        The key insight is that Claude is stateless - it only knows what's
        in the conversation we send it. We're responsible for maintaining
        context by keeping and sending the full conversation history.
        """
        # The conversation history. Each message is a dict with 'role' and 'content'.
        # The Anthropic API expects alternating user/assistant messages.
        conversation: list[dict] = []
        
        print("Chat with Claude (use 'ctrl-c' to quit)")
        print()
        
        # This flag controls whether we prompt for user input or continue
        # processing tool results. After Claude uses a tool, we need to
        # send the result back without asking for new user input.
        read_user_input = True
        
        while True:
            # -------------------------------------------------------------
            # STEP 1: Get user input (if needed)
            # -------------------------------------------------------------
            if read_user_input:
                # Print prompt with color (ANSI escape codes)
                # \033[94m = bright blue, \033[0m = reset
                print("\033[94mYou\033[0m: ", end="", flush=True)
                
                user_input = self.get_user_message()
                if user_input is None:
                    # User wants to quit (EOF or Ctrl+D)
                    break
                
                # Add the user's message to the conversation history
                # This is the format Anthropic's API expects
                conversation.append({
                    "role": "user",
                    "content": [{"type": "text", "text": user_input}]
                })
            
            # -------------------------------------------------------------
            # STEP 2: Send conversation to Claude and get response
            # -------------------------------------------------------------
            try:
                message = self._run_inference(conversation)
            except anthropic.APIError as e:
                print(f"\033[91mAPI Error\033[0m: {e}")
                continue
            
            # Add Claude's response to the conversation history
            # We need to convert the Message object to the format expected
            # for the next API call
            conversation.append({
                "role": "assistant",
                "content": message.content
            })
            
            # -------------------------------------------------------------
            # STEP 3: Process Claude's response
            # -------------------------------------------------------------
            # Claude's response can contain multiple "content blocks":
            # - TextBlock: Regular text response
            # - ToolUseBlock: A request to execute a tool
            #
            # A single response might have text AND tool requests,
            # or multiple tool requests. We process them all.
            
            tool_results = []
            
            for content_block in message.content:
                if content_block.type == "text":
                    # Claude sent us text - print it!
                    # \033[93m = bright yellow for Claude's name
                    print(f"\033[93mClaude\033[0m: {content_block.text}")
                
                elif content_block.type == "tool_use":
                    # Claude wants to use a tool!
                    # The content_block contains:
                    # - id: A unique ID for this tool use (for matching results)
                    # - name: Which tool to execute
                    # - input: The parameters Claude wants to pass
                    result = self._execute_tool(
                        tool_id=content_block.id,
                        tool_name=content_block.name,
                        tool_input=content_block.input,
                    )
                    tool_results.append(result)
            
            # -------------------------------------------------------------
            # STEP 4: Handle tool results
            # -------------------------------------------------------------
            if not tool_results:
                # No tools were used - we can wait for user input
                read_user_input = True
                print()  # Add blank line for readability
            else:
                # Tools were used - we need to send results back to Claude
                # WITHOUT asking for new user input
                read_user_input = False
                
                # Tool results are sent as a "user" message (that's the API format)
                # This might seem odd, but think of it as "the user's system"
                # reporting back the results of executing Claude's requested tools
                conversation.append({
                    "role": "user",
                    "content": tool_results
                })
    
    def _run_inference(self, conversation: list[dict]) -> anthropic.types.Message:
        """
        Send the conversation to Claude and get a response.
        
        This method:
        1. Converts our tool definitions to Anthropic's format
        2. Makes the API call
        3. Returns Claude's response
        
        Args:
            conversation: The full conversation history
        
        Returns:
            A Message object containing Claude's response
        
        Note: We send the FULL conversation every time. The API is stateless.
              This is how Claude "remembers" what was said earlier.
        """
        # Convert our tool definitions to Anthropic's expected format
        # The API wants a specific structure for tool definitions
        anthropic_tools = []
        for tool in self.tools:
            anthropic_tools.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            })
        
        # Make the API call
        # Note: We're using Claude 3.5 Sonnet which is excellent at tool use
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",  # Latest Claude Sonnet
            max_tokens=1024,                    # Limit response length
            messages=conversation,              # Full conversation history
            tools=anthropic_tools,              # Available tools
        )
        
        return message
    
    def _execute_tool(
        self,
        tool_id: str,
        tool_name: str,
        tool_input: dict,
    ) -> dict:
        """
        Execute a tool that Claude has requested.
        
        This is where we bridge the gap between Claude's "intent" (wanting
        to use a tool) and actual "action" (running code on the system).
        
        Args:
            tool_id: Unique ID for this tool use (used to match results)
            tool_name: Name of the tool to execute
            tool_input: Parameters Claude wants to pass to the tool
        
        Returns:
            A dict in the format expected by Anthropic's API for tool results
        """
        # Find the tool definition by name
        tool_def = None
        for tool in self.tools:
            if tool.name == tool_name:
                tool_def = tool
                break
        
        if tool_def is None:
            # Tool not found - tell Claude about the error
            # This shouldn't happen if Claude follows its instructions,
            # but it's good to handle gracefully
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"Error: Tool '{tool_name}' not found",
                "is_error": True,
            }
        
        # Print what tool we're executing (for user visibility)
        # \033[92m = bright green
        input_str = json.dumps(tool_input)
        print(f"\033[92mtool\033[0m: {tool_name}({input_str})")
        
        # Execute the tool function
        try:
            result = tool_def.function(tool_input)
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result,
                "is_error": False,
            }
        except Exception as e:
            # If the tool fails, report the error to Claude
            # Claude can often recover from errors (e.g., try a different file)
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": f"Error: {str(e)}",
                "is_error": True,
            }


# =============================================================================
# MAIN FUNCTION
# =============================================================================

def get_user_input() -> Optional[str]:
    """
    Read a line of input from stdin.
    
    Returns:
        The user's input string, or None if EOF is reached (Ctrl+D)
    
    This is a simple wrapper that can be replaced for testing or
    integration with other interfaces (GUI, web, etc.)
    """
    try:
        return input()
    except EOFError:
        return None


def main():
    """
    Entry point for the code-editing agent.
    
    This function:
    1. Loads environment variables from .env
    2. Creates the Anthropic client
    3. Sets up the available tools
    4. Creates and runs the agent
    """
    # -------------------------------------------------------------------------
    # Load environment variables from .env file
    # -------------------------------------------------------------------------
    # The load_dotenv() function looks for a .env file in the current
    # directory (or parent directories) and loads any variables defined there.
    # This keeps sensitive data like API keys out of the source code.
    # We explicitly specify the path to ensure it's loaded from the script's directory.
    # IMPORTANT: override=True ensures the .env file takes precedence over shell environment
    from pathlib import Path
    env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=env_path, override=True)

    # Get the API key from environment
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment")
        print(f"Looked for .env file at: {env_path}")
        print("Please create a .env file with your API key:")
        print("  ANTHROPIC_API_KEY=your-key-here")
        sys.exit(1)

    # Strip any whitespace that might have been accidentally added
    api_key = api_key.strip()

    # -------------------------------------------------------------------------
    # Create the Anthropic client
    # -------------------------------------------------------------------------
    # The client handles all HTTP communication with Anthropic's API.
    # It automatically manages authentication, retries, and error handling.
    client = anthropic.Anthropic(api_key=api_key)
    
    # -------------------------------------------------------------------------
    # Define available tools
    # -------------------------------------------------------------------------
    # These are the "capabilities" we give to Claude. Each tool is a bridge
    # between Claude's understanding and actual system operations.
    #
    # The tools we provide are:
    # 1. read_file: Read the contents of a file
    # 2. list_files: List files in a directory
    # 3. edit_file: Edit a file by replacing text
    #
    # This is all Claude needs to be a functional code-editing agent!
    tools = [
        read_file_definition,
        list_files_definition,
        edit_file_definition,
    ]
    
    # -------------------------------------------------------------------------
    # Create and run the agent
    # -------------------------------------------------------------------------
    agent = Agent(
        client=client,
        get_user_message=get_user_input,
        tools=tools,
    )
    
    try:
        agent.run()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\n\nGoodbye!")


if __name__ == "__main__":
    main()
