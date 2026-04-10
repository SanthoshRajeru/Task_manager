# Task Manager Web App

This is a separate FastAPI-based project for managing daily tasks.

## Features (current)
- Create tasks
- List tasks
- Search tasks by title
- Filter tasks by status and priority
- Sort tasks by ID, title, status, priority, or due date
- Productivity analytics dashboard (completion, overdue, due today, upcoming, status/priority charts)
- Add/edit task notes or description (persistent)
- Calendar view with monthly due-date task chips
- Authentication (register/login/logout/forgot password/change password) with per-user private task data
- Update task status (`todo`, `in_progress`, `done`)
- Edit task title inline (Save/Cancel)
- Set and update task due date
- Set and update task priority (`low`, `medium`, `high`)
- Delete tasks
- Fields: Task ID, Task title, Task status
- Persistent storage in `tasks.json`

## Run
1. Open a terminal in `task_manager_web`.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start server:
   - `python main.py`
4. Open browser:
   - `http://127.0.0.1:8010`
5. Register a new account (or login) from the auth panel.
