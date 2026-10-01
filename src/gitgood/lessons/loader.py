"""Lesson file loader."""

import os
from pathlib import Path
from typing import Optional

import yaml

from .engine import Lesson, LessonStep, StepType, LessonEngine


def load_lesson_from_yaml(filepath: str) -> Optional[Lesson]:
    """Load a lesson from a YAML file."""
    try:
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"Error loading lesson from {filepath}: {e}")
        return None

    if not data:
        return None

    steps = []
    for step_data in data.get("steps", []):
        step_type_str = step_data.get("step_type", "command")
        step_type = StepType(step_type_str)

        step = LessonStep(
            step_id=step_data.get("step_id", ""),
            step_type=step_type,
            instruction=step_data.get("instruction", ""),
            expected_commands=step_data.get("expected_commands", []),
            command_pattern=step_data.get("command_pattern"),
            success_message=step_data.get("success_message", "Correct!"),
            failure_hints=step_data.get("failure_hints", []),
            setup_changes=step_data.get("setup_changes", []),
        )
        steps.append(step)

    lesson = Lesson(
        lesson_id=data.get("lesson_id", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        objectives=data.get("objectives", []),
        steps=steps,
        required_lessons=data.get("required_lessons", []),
        initial_state=data.get("initial_state"),
    )

    return lesson


def load_lessons_from_directory(directory: str, engine: LessonEngine) -> int:
    """Load all lessons from a directory into the engine."""
    count = 0
    lesson_dir = Path(directory)

    if not lesson_dir.exists():
        return 0

    # Sort files to ensure consistent order
    yaml_files = sorted(lesson_dir.glob("*.yaml"))

    for filepath in yaml_files:
        lesson = load_lesson_from_yaml(str(filepath))
        if lesson:
            engine.add_lesson(lesson)
            count += 1

    return count


def get_default_lessons_dir() -> str:
    """Get the path to the default lessons directory."""
    # Look relative to this file
    this_file = Path(__file__)
    lessons_dir = this_file.parent / "data"
    return str(lessons_dir)
