# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GitGood is an interactive CLI tool that teaches GitHub flow through hands-on simulation. Users practice real git/gh commands in a virtual repository environment with structured lessons and real-time validation.

## Build & Run Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run the application
gitgood
# or
python3 -m gitgood

# Run tests (none exist yet)
pytest
pytest --cov=src/gitgood tests/    # with coverage
pytest tests/test_repository.py   # single file

# Linting and type checking
ruff check src/ tests/
ruff check --fix src/ tests/      # auto-fix
mypy src/gitgood
```

## Architecture

The codebase has 5 main modules with distinct responsibilities:

```
src/gitgood/
├── app.py              # Main REPL orchestrator (GitGoodApp)
├── core/               # Virtual repository simulation
│   ├── repository.py   # VirtualRepository - in-memory git state
│   ├── models.py       # Commit, Branch, PR, CommandResult
│   └── github_api.py   # SimulatedGitHub - PR operations
├── parser/             # Command processing pipeline
│   ├── lexer.py        # Tokenizes input → ParsedCommand
│   ├── commands.py     # Command specs and help text
│   └── executor.py     # Routes commands to handlers
├── lessons/            # Tutorial engine
│   ├── engine.py       # LessonEngine - progression & validation
│   ├── loader.py       # YAML lesson file loading
│   └── data/           # 6 lesson YAML files (01-06)
└── ui/                 # Terminal interface (Rich/prompt_toolkit)
    ├── console.py      # GitGoodConsole - styled output
    ├── prompt.py       # CommandPrompt - interactive input
    ├── panels.py       # Status, progress, lesson list panels
    └── tree_view.py    # Commit history visualization
```

### Key Patterns

**Command Flow:** User input → `CommandLexer.parse()` → `ParsedCommand` → `CommandExecutor.execute()` → `CommandResult`

**Lesson Validation:** `LessonEngine.validate_command()` checks user input against `expected_commands` or `command_pattern` (regex) before execution proceeds.

**All operations return `CommandResult`** with `success: bool`, `output: str`, and `hints: list[str]`.

### Lesson YAML Structure

```yaml
lesson_id: "01_branching"
title: "..."
required_lessons: []  # prerequisites
steps:
  - step_id: "intro"
    step_type: "explanation"  # or "command" or "free_practice"
    instruction: "..."
    expected_commands: ["git checkout -b feature"]  # for command steps
    command_pattern: "git checkout.*"  # optional regex alternative
    success_message: "..."
    failure_hints: ["..."]
```

## Key Dependencies

- `rich` - Terminal UI rendering
- `prompt-toolkit` - Interactive command prompt with history
- `pyyaml` - Lesson YAML parsing
- `pydantic` - Data validation and models
