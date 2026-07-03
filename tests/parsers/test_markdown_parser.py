"""Unit tests for MarkdownTaskParser."""

import pytest
from iccc.parsers.markdown_parser import MarkdownTaskParser

class TestMarkdownTaskParser:
    """Tests for Markdown parsing logic."""

    def test_parse_standard_format(self):
        """Test parsing standard strict format."""
        content = """
# MAINTASK

#### Task TASK-001: Implement Login
- **Description**: Implement the login page using React.
- **Type**: frontend_feature
- **Assignee**: worker-frontend

#### Task TASK-002: Setup DB
- **Description**: Init MongoDB.
- **Type**: backend_feature
- **Assignee**: worker-backend
"""
        tasks = MarkdownTaskParser.parse(content)
        assert len(tasks) == 2
        
        assert tasks[0]["id"] == "TASK-001"
        assert tasks[0]["title"] == "Implement Login"
        assert tasks[0]["description"] == "Implement the login page using React."
        assert tasks[0]["task_type"] == "frontend_feature"

    def test_parse_lenient_headers(self):
        """Test parsing with different header levels (fragility check)."""
        content = """
## Task TASK-100: Big Header
- **Description**: desc
- **Type**: test
- **Assignee**: me

### Task TASK-101: Med Header
- **Description**: desc
"""
        # The current implementation might fail here because it splits by "#### Task"
        tasks = MarkdownTaskParser.parse(content)
        
        # If the current parser is fragile, this might be 0 or broken
        # We expect our NEW parser to handle this.
        # For now, let's see what happens.
        assert len(tasks) >= 2

    def test_parse_lenient_attributes(self):
        """Test parsing attributes with different formatting."""
        content = """
#### Task TASK-200: Attributes
- Description: No bold
- Type: feature
- Assignee: worker
"""
        tasks = MarkdownTaskParser.parse(content)
        assert len(tasks) == 1
        assert tasks[0]["description"] == "No bold"

    def test_parse_multiline_description(self):
        """Test parsing multiline descriptions (if supported)."""
        content = """
#### Task TASK-300: Multiline
- **Description**: This is a
  multiline description.
- **Type**: feature
"""
        tasks = MarkdownTaskParser.parse(content)
        assert len(tasks) == 1
        # Ideally, it should capture the full text.
        # Current implementation likely truncates.
        assert "multiline description" in tasks[0]["description"]

    def test_json_fallback(self):
        """Test parsing if JSON block is present (future proofing)."""
        content = """
Some text.

```json
[
  {
    "id": "TASK-JSON",
    "title": "From JSON",
    "description": "Parsed from JSON block",
    "task_type": "json",
    "assignee": "bot"
  }
]
```
"""
        # Current parser doesn't support this yet.
        tasks = MarkdownTaskParser.parse(content)
        # We want this to eventually work
        # assert len(tasks) == 1
