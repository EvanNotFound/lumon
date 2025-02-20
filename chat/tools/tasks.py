from datetime import datetime
from typing import List, Optional, Dict
import json
import os
from langchain_core.tools import tool
from utils.date import get_montreal_time

TASKS_FILE = "data/tasks.json"

class Task:
    def __init__(self, title: str, due_date: str, description: str, category: str, recurring: bool = False):
        self.title = title
        self.due_date = due_date  # ISO format string
        self.description = description
        self.category = category
        self.recurring = recurring

    def to_dict(self):
        return {
            "title": self.title,
            "due_date": self.due_date,
            "description": self.description,
            "category": self.category,
            "recurring": self.recurring
        }

def load_tasks() -> List[Dict]:
    if not os.path.exists(TASKS_FILE):
        return []
    with open(TASKS_FILE, 'r') as f:
        return json.load(f)

def save_tasks(tasks: List[Dict]):
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, 'w') as f:
        json.dump(tasks, f, indent=2)

@tool
def add_task(title: str, due_date: str, description: str, category: str, recurring: bool = False) -> str:
    """Add a new task to the task list.
    Args:
        title: Task title
        due_date: Due date in ISO format (YYYY-MM-DD)
        description: Task description
        category: Task category (e.g., "homework", "exam", "project")
        recurring: Whether the task repeats
    """
    task = Task(title, due_date, description, category, recurring)
    tasks = load_tasks()
    tasks.append(task.to_dict())
    save_tasks(tasks)
    return f"Added task: {title}"

@tool
def get_current_tasks() -> List[Dict]:
    """Get all current and upcoming tasks, sorted by due date"""
    current_time = get_montreal_time()["datetime"]
    tasks = load_tasks()
    
    # Filter and sort tasks
    current_tasks = []
    for task in tasks:
        due_date = datetime.fromisoformat(task["due_date"])
        if due_date >= current_time or task["recurring"]:
            current_tasks.append(task)
    
    return sorted(current_tasks, key=lambda x: x["due_date"])

@tool
def remove_task(title: str) -> str:
    """Remove a task by its title"""
    tasks = load_tasks()
    initial_count = len(tasks)
    tasks = [task for task in tasks if task["title"] != title]
    save_tasks(tasks)
    
    if len(tasks) < initial_count:
        return f"Removed task: {title}"
    return f"No task found with title: {title}" 