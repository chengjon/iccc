"""
Parsers for converting unstructured specifications into structured data.
"""

import re
import json
from typing import Any

class MarkdownTaskParser:
    """Parses MAINTASK.md content into structured task dictionaries."""

    @staticmethod
    def parse(content: str) -> list[dict[str, Any]]:
        """
        Extract tasks from markdown content.
        
        Strategy:
        1. Check for a ```json block first (robust structured output).
        2. Fallback to robust line-by-line Markdown parsing.
        
        Expected Markdown Format:
        #### Task TASK-XXX: Title
        - **Description**: ...
        - **Type**: ...
        - **Assignee**: ...
        
        Returns:
            List of dicts with keys: id, title, description, task_type, assignee.
        """
        # 1. JSON Block Extraction
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "tasks" in data:
                    return data["tasks"]
            except json.JSONDecodeError:
                pass # Fallback to markdown parsing

        # 2. Robust Markdown Parsing
        tasks = []
        current_task: dict[str, Any] = {}
        current_attr = None 

        # Matches: "#### Task TASK-001: Title" or "## Task TASK-001" (Case insensitive)
        header_pattern = re.compile(r"^#+\s+Task\s+(TASK-[\w-]+)(?::\s*(.+))?", re.IGNORECASE)
        
        # Matches: "- **Description**: Value" or "- Type: Value" (Handles bold/no-bold)
        attr_pattern = re.compile(r"^\s*-\s*[*_]*(\w+)[*_]*:\s*(.+)")

        lines = content.split('\n')
        
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # Check for New Task Header
            header_match = header_pattern.match(stripped_line)
            if header_match:
                # Save previous task if exists
                if current_task:
                    tasks.append(current_task)
                
                task_id = header_match.group(1)
                title = header_match.group(2) or task_id
                
                current_task = {
                    "id": task_id,
                    "title": title.strip(),
                    "description": "",
                    "task_type": "general_coding",
                    "assignee": "worker"
                }
                current_attr = None
                continue

            # If we are inside a task...
            if current_task:
                # Check for Attribute
                attr_match = attr_pattern.match(stripped_line)
                if attr_match:
                    key = attr_match.group(1).lower() # description, type, assignee
                    value = attr_match.group(2).strip()
                    
                    # Map keys to standard internal keys
                    if key == "type":
                        key = "task_type"
                    
                    current_task[key] = value
                    current_attr = key
                elif current_attr and not stripped_line.startswith("-") and not stripped_line.startswith("#"):
                    # Append to current attribute (multiline support)
                    # We assume if it doesn't start with dash or hash, it's continuation
                    current_task[current_attr] += " " + stripped_line

        # Append last task
        if current_task:
            tasks.append(current_task)
            
        return tasks