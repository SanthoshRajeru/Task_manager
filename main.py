import hashlib
import json
import secrets
from datetime import date, timedelta
from enum import Enum
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Task Manager API", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "static" / "index.html"
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SortBy(str, Enum):
    TASK_ID = "task_id"
    TASK_TITLE = "task_title"
    TASK_STATUS = "task_status"
    PRIORITY = "priority"
    DUE_DATE = "due_date"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class UserChangePassword(BaseModel):
    old_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class UserForgotPassword(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    new_password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    due_date: date | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    notes: str = Field(default="", max_length=600)


class TaskUpdateStatus(BaseModel):
    status: TaskStatus


class TaskUpdateContent(BaseModel):
    task_title: str = Field(min_length=1, max_length=120)
    task_notes: str = Field(default="", max_length=600)


class TaskUpdateDetails(BaseModel):
    due_date: date | None = None
    priority: TaskPriority | None = None


class Task(BaseModel):
    task_id: int
    task_title: str
    task_notes: str = ""
    task_status: TaskStatus
    due_date: date | None = None
    priority: TaskPriority = TaskPriority.MEDIUM


users: dict[str, dict[str, str]] = {}
tasks_by_user: dict[str, dict[int, Task]] = {}
active_tokens: dict[str, str] = {}


def safe_username(username: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in username.strip().lower())


def get_user_tasks_file(username: str) -> Path:
    return DATA_DIR / f"tasks_{safe_username(username)}.json"


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return digest.hex()


def save_users() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = USERS_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(users, indent=2), encoding="utf-8")
    temp_file.replace(USERS_FILE)


def load_users() -> None:
    if not USERS_FILE.exists():
        return

    try:
        raw_data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return

    if not isinstance(raw_data, dict):
        return

    users.clear()
    for username, value in raw_data.items():
        if (
            isinstance(value, dict)
            and isinstance(value.get("salt"), str)
            and isinstance(value.get("password_hash"), str)
        ):
            users[username] = {
                "salt": value["salt"],
                "password_hash": value["password_hash"],
            }


def load_user_tasks(username: str) -> dict[int, Task]:
    tasks_file = get_user_tasks_file(username)
    if not tasks_file.exists():
        return {}

    try:
        raw_data = json.loads(tasks_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    if not isinstance(raw_data, list):
        return {}

    loaded_tasks: dict[int, Task] = {}
    for item in raw_data:
        try:
            task = Task.model_validate(item)
            loaded_tasks[task.task_id] = task
        except Exception:
            continue
    return loaded_tasks


def save_user_tasks(username: str, user_tasks: dict[int, Task]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tasks_file = get_user_tasks_file(username)
    payload = [task.model_dump(mode="json") for task in user_tasks.values()]
    temp_file = tasks_file.with_suffix(".tmp")
    temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_file.replace(tasks_file)


def get_user_tasks(username: str) -> dict[int, Task]:
    if username not in tasks_by_user:
        tasks_by_user[username] = load_user_tasks(username)
    return tasks_by_user[username]


def get_next_task_id(user_tasks: dict[int, Task]) -> int:
    next_id = 1
    while next_id in user_tasks:
        next_id += 1
    return next_id


def resequence_task_ids(user_tasks: dict[int, Task]) -> None:
    ordered_tasks = sorted(user_tasks.values(), key=lambda task: task.task_id)
    user_tasks.clear()
    for new_id, task in enumerate(ordered_tasks, start=1):
        user_tasks[new_id] = task.model_copy(update={"task_id": new_id})


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(status_code=401, detail="Invalid authorization format.")
    return parts[1].strip()


def get_current_username(authorization: str | None = Header(default=None)) -> str:
    token = parse_bearer_token(authorization)
    username = active_tokens.get(token)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    return username


@app.on_event("startup")
def startup_event():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_users()


@app.get("/")
def read_home():
    if not INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="Frontend file not found.")
    return FileResponse(INDEX_FILE)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "task-manager-api"}


@app.post("/api/auth/register", response_model=AuthResponse, status_code=201)
def register_user(payload: UserRegister):
    username = payload.username.strip().lower()
    if username in users:
        raise HTTPException(status_code=409, detail="Username already exists.")

    salt = secrets.token_hex(16)
    users[username] = {
        "salt": salt,
        "password_hash": hash_password(payload.password, salt),
    }
    save_users()

    token = secrets.token_urlsafe(32)
    active_tokens[token] = username
    user_tasks = get_user_tasks(username)
    save_user_tasks(username, user_tasks)

    return AuthResponse(access_token=token, username=username)


@app.post("/api/auth/login", response_model=AuthResponse)
def login_user(payload: UserLogin):
    username = payload.username.strip().lower()
    record = users.get(username)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if hash_password(payload.password, record["salt"]) != record["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = secrets.token_urlsafe(32)
    active_tokens[token] = username
    return AuthResponse(access_token=token, username=username)


@app.get("/api/auth/me")
def auth_me(username: str = Depends(get_current_username)):
    return {"username": username}


@app.post("/api/auth/logout")
def logout_user(authorization: str | None = Header(default=None)):
    token = parse_bearer_token(authorization)
    active_tokens.pop(token, None)
    return {"message": "Logged out successfully."}


@app.post("/api/auth/change-password")
def change_password(
    payload: UserChangePassword, username: str = Depends(get_current_username)
):
    record = users.get(username)
    if record is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if hash_password(payload.old_password, record["salt"]) != record["password_hash"]:
        raise HTTPException(status_code=401, detail="Current password is incorrect.")

    if payload.old_password == payload.new_password:
        raise HTTPException(
            status_code=400, detail="New password must be different from current password."
        )

    new_salt = secrets.token_hex(16)
    users[username] = {
        "salt": new_salt,
        "password_hash": hash_password(payload.new_password, new_salt),
    }
    save_users()

    return {"message": "Password updated successfully."}


@app.post("/api/auth/forgot-password")
def forgot_password(payload: UserForgotPassword):
    username = payload.username.strip().lower()
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")

    new_password = payload.new_password.strip()
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    record = users.get(username)
    if record is None:
        raise HTTPException(status_code=404, detail="Username not found.")

    new_salt = secrets.token_hex(16)
    users[username] = {
        "salt": new_salt,
        "password_hash": hash_password(new_password, new_salt),
    }
    save_users()

    return {"message": "Password reset successfully. Please login."}


@app.get("/api/tasks", response_model=list[Task])
def get_tasks(
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    q: str | None = None,
    sort_by: SortBy = SortBy.TASK_ID,
    sort_order: SortOrder = SortOrder.ASC,
    username: str = Depends(get_current_username),
):
    filtered_tasks = list(get_user_tasks(username).values())

    if status is not None:
        filtered_tasks = [task for task in filtered_tasks if task.task_status == status]

    if priority is not None:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]

    if q:
        query = q.strip().lower()
        if query:
            filtered_tasks = [
                task
                for task in filtered_tasks
                if query in task.task_title.lower() or query in task.task_notes.lower()
            ]

    reverse_sort = sort_order == SortOrder.DESC
    status_rank = {
        TaskStatus.TODO: 0,
        TaskStatus.IN_PROGRESS: 1,
        TaskStatus.DONE: 2,
    }
    priority_rank = {
        TaskPriority.LOW: 0,
        TaskPriority.MEDIUM: 1,
        TaskPriority.HIGH: 2,
    }

    if sort_by == SortBy.TASK_TITLE:
        return sorted(
            filtered_tasks, key=lambda task: task.task_title.lower(), reverse=reverse_sort
        )

    if sort_by == SortBy.TASK_STATUS:
        return sorted(
            filtered_tasks,
            key=lambda task: status_rank.get(task.task_status, 99),
            reverse=reverse_sort,
        )

    if sort_by == SortBy.PRIORITY:
        return sorted(
            filtered_tasks,
            key=lambda task: priority_rank.get(task.priority, 99),
            reverse=reverse_sort,
        )

    if sort_by == SortBy.DUE_DATE:
        tasks_with_due_date = [task for task in filtered_tasks if task.due_date is not None]
        tasks_without_due_date = [task for task in filtered_tasks if task.due_date is None]
        tasks_with_due_date = sorted(
            tasks_with_due_date, key=lambda task: task.due_date, reverse=reverse_sort
        )
        return tasks_with_due_date + tasks_without_due_date

    return sorted(filtered_tasks, key=lambda task: task.task_id, reverse=reverse_sort)


@app.get("/api/tasks/analytics")
def get_task_analytics(username: str = Depends(get_current_username)):
    all_tasks = list(get_user_tasks(username).values())
    total_tasks = len(all_tasks)
    today = date.today()

    status_counts = {
        TaskStatus.TODO.value: 0,
        TaskStatus.IN_PROGRESS.value: 0,
        TaskStatus.DONE.value: 0,
    }
    priority_counts = {
        TaskPriority.LOW.value: 0,
        TaskPriority.MEDIUM.value: 0,
        TaskPriority.HIGH.value: 0,
    }
    overdue_count = 0
    due_today_count = 0
    upcoming_seven_days_count = 0

    for task in all_tasks:
        status_counts[task.task_status.value] += 1
        priority_counts[task.priority.value] += 1

        if task.due_date is None:
            continue

        if task.due_date < today and task.task_status != TaskStatus.DONE:
            overdue_count += 1
        elif task.due_date == today:
            due_today_count += 1
        elif today < task.due_date <= today + timedelta(days=7):
            upcoming_seven_days_count += 1

    completed_count = status_counts[TaskStatus.DONE.value]
    completion_rate = round((completed_count / total_tasks) * 100, 2) if total_tasks else 0.0

    return {
        "total_tasks": total_tasks,
        "completed_tasks": completed_count,
        "completion_rate": completion_rate,
        "status_counts": status_counts,
        "priority_counts": priority_counts,
        "overdue_count": overdue_count,
        "due_today_count": due_today_count,
        "upcoming_7_days_count": upcoming_seven_days_count,
    }


@app.get("/api/tasks/{task_id}", response_model=Task)
def get_task(task_id: int, username: str = Depends(get_current_username)):
    task = get_user_tasks(username).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@app.post("/api/tasks", response_model=Task, status_code=201)
def create_task(payload: TaskCreate, username: str = Depends(get_current_username)):
    clean_title = payload.title.strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="Task title is required.")

    user_tasks = get_user_tasks(username)
    task_id = get_next_task_id(user_tasks)
    new_task = Task(
        task_id=task_id,
        task_title=clean_title,
        task_notes=payload.notes.strip(),
        task_status=TaskStatus.TODO,
        due_date=payload.due_date,
        priority=payload.priority,
    )
    user_tasks[task_id] = new_task
    save_user_tasks(username, user_tasks)
    return new_task


@app.patch("/api/tasks/{task_id}/status", response_model=Task)
def update_task_status(
    task_id: int, payload: TaskUpdateStatus, username: str = Depends(get_current_username)
):
    user_tasks = get_user_tasks(username)
    task = user_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    updated_task = task.model_copy(update={"task_status": payload.status})
    user_tasks[task_id] = updated_task
    save_user_tasks(username, user_tasks)
    return updated_task


@app.patch("/api/tasks/{task_id}/content", response_model=Task)
def update_task_content(
    task_id: int, payload: TaskUpdateContent, username: str = Depends(get_current_username)
):
    user_tasks = get_user_tasks(username)
    task = user_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    clean_title = payload.task_title.strip()
    if not clean_title:
        raise HTTPException(status_code=400, detail="Task title is required.")

    updated_task = task.model_copy(
        update={"task_title": clean_title, "task_notes": payload.task_notes.strip()}
    )
    user_tasks[task_id] = updated_task
    save_user_tasks(username, user_tasks)
    return updated_task


@app.patch("/api/tasks/{task_id}/details", response_model=Task)
def update_task_details(
    task_id: int, payload: TaskUpdateDetails, username: str = Depends(get_current_username)
):
    user_tasks = get_user_tasks(username)
    task = user_tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return task

    updated_task = task.model_copy(update=updates)
    user_tasks[task_id] = updated_task
    save_user_tasks(username, user_tasks)
    return updated_task


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, username: str = Depends(get_current_username)):
    user_tasks = get_user_tasks(username)
    if task_id not in user_tasks:
        raise HTTPException(status_code=404, detail="Task not found.")
    del user_tasks[task_id]
    resequence_task_ids(user_tasks)
    save_user_tasks(username, user_tasks)
    return None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
