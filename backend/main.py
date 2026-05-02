from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import sqlite3
import sql  # Модуль работы с БД
import uvicorn

app = FastAPI(title="Workout Planner API")

# Схемы данных (Pydantic) с валидацией

class UserCreate(BaseModel):
    # Логин: от 3 до 20 символов, без спецсимволов (только буквы, цифры и _)
    username: str = Field(..., min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    # Пароль должен быть не короче 6 символов
    password_hash: str = Field(..., min_length=6)
    name: Optional[str] = Field(None, max_length=50)

class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=50)
    password_hash: Optional[str] = Field(None, min_length=6)

class WorkoutSessionCreate(BaseModel):
    user_id: int = Field(..., gt=0) # ID не может быть нулем или отрицательным
    name: str = Field(..., min_length=2, max_length=100)
    # Ожидаем дату в формате YYYY-MM-DD
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Статус может быть только planned или completed
    status: str = Field("planned", pattern=r"^(planned|completed)$")
    times: Optional[int] = Field(None, gt=0, le=1440) # Время в минутах (максимум 24 часа)
    notes: Optional[str] = Field(None, max_length=500)

class WorkoutSessionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    status: Optional[str] = Field(None, pattern=r"^(planned|completed)$")
    times: Optional[int] = Field(None, gt=0, le=1440)
    notes: Optional[str] = Field(None, max_length=500)

class SessionExerciseCreate(BaseModel):
    session_id: int = Field(..., gt=0)
    exercise_id: int = Field(..., gt=0)
    sets: int = Field(..., gt=0, le=50) # Подходов больше 0, но не больше 50
    reps: int = Field(..., gt=0, le=1000) # Повторений больше 0
    weight: float = Field(..., ge=0.0, le=1000.0) # Вес больше или равен 0, до 1000 кг
    notes: Optional[str] = Field(None, max_length=255)

class SessionExerciseUpdate(BaseModel):
    sets: Optional[int] = Field(None, gt=0, le=50)
    reps: Optional[int] = Field(None, gt=0, le=1000)
    weight: Optional[float] = Field(None, ge=0.0, le=1000.0)
    notes: Optional[str] = Field(None, max_length=255)

class WeightLogCreate(BaseModel):
    user_id: int = Field(..., gt=0)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Вес человека от 20 до 300 кг
    weight: float = Field(..., gt=20.0, le=300.0)

class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    user_id: Optional[int] = Field(None, gt=0) # None для системных
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=50)
    is_public: int = Field(0, ge=0, le=1) # 1 - публичный, 0 - приватный

class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=50)
    is_public: Optional[int] = Field(None, ge=0, le=1)

class TemplateExerciseCreate(BaseModel):
    template_id: int = Field(..., gt=0)
    exercise_id: int = Field(..., gt=0)
    sets: int = Field(..., gt=0, le=50)
    reps: int = Field(..., gt=0, le=1000)
    weight: float = Field(..., ge=0.0, le=1000.0)
    order_index: int = Field(..., ge=0)

class TemplateExerciseUpdate(BaseModel):
    sets: Optional[int] = Field(None, gt=0, le=50)
    reps: Optional[int] = Field(None, gt=0, le=1000)
    weight: Optional[float] = Field(None, ge=0.0, le=1000.0)
    order_index: Optional[int] = Field(None, ge=0)

# Вспомогательная функция

def get_db_connection():
    conn = sql.connection("workouts.db")
    if conn:
        conn.row_factory = sqlite3.Row
    return conn

# Эндпоинты (API)

# Пользователи (Users)

@app.post("/users/", tags=["Users"])
def create_user(user: UserCreate):
    conn = get_db_connection()
    user_id = sql.insert_user(conn, user.username, user.password_hash, user.name)
    conn.close()
    if user_id: return {"id": user_id, "status": "user created"}
    raise HTTPException(status_code=400, detail="User already exists")

@app.get("/users/", tags=["Users"])
def get_users():
    # Получить список всех пользователей
    conn = get_db_connection()
    users = sql.select_all(conn, "users")
    conn.close()
    return [dict(u) for u in users]

@app.get("/users/{user_id}", tags=["Users"])
def get_user(user_id: int):
    # Получить пользователя по ID
    conn = get_db_connection()
    user = sql.select_by_id(conn, "users", user_id)
    conn.close()
    if user: return dict(user)
    raise HTTPException(status_code=404, detail="User not found")

@app.put("/users/{user_id}", tags=["Users"])
def update_user(user_id: int, user_data: UserUpdate):
    conn = get_db_connection()
    data = user_data.model_dump(exclude_unset=True)
    result = sql.update(conn, "users", data, f"id = {user_id}")
    conn.close()
    return {"updated": result}

@app.delete("/users/{user_id}", tags=["Users"])
def delete_user(user_id: int):
    conn = get_db_connection()
    result = sql.delete(conn, "users", f"id = {user_id}")
    conn.close()
    return {"deleted": result}

# Тренировки (Sessions)

@app.post("/sessions/", tags=["Workouts"])
def create_session(session: WorkoutSessionCreate):
    conn = get_db_connection()
    s_id = sql.insert_workout_session(
        conn, session.user_id, session.name, session.date,
        session.status, times=session.times, notes=session.notes
    )
    conn.close()
    return {"session_id": s_id}

@app.get("/sessions/", tags=["Workouts"])
def get_all_sessions():
    # Получить список вообще всех тренировок в базе
    conn = get_db_connection()
    sessions = sql.select_all(conn, "workout_sessions")
    conn.close()
    return [dict(s) for s in sessions]

@app.get("/sessions/{session_id}", tags=["Workouts"])
def get_session(session_id: int):
    # Получить данные конкретной тренировки по ID
    conn = get_db_connection()
    session = sql.select_by_id(conn, "workout_sessions", session_id)
    conn.close()
    if session: return dict(session)
    raise HTTPException(status_code=404, detail="Session not found")

@app.get("/sessions/user/{user_id}", tags=["Workouts"])
def get_user_history(user_id: int):
    # История тренировок конкретного пользователя
    conn = get_db_connection()
    sessions = sql.select_all(conn, "workout_sessions", conditions=f"user_id = {user_id}", order_by="date DESC")
    conn.close()
    return [dict(s) for s in sessions]

@app.put("/sessions/{session_id}", tags=["Workouts"])
def update_session(session_id: int, session_data: WorkoutSessionUpdate):
    conn = get_db_connection()
    data = session_data.model_dump(exclude_unset=True)
    result = sql.update(conn, "workout_sessions", data, f"id = {session_id}")
    conn.close()
    return {"updated": result}

@app.delete("/sessions/{session_id}", tags=["Workouts"])
def delete_session(session_id: int):
    conn = get_db_connection()
    result = sql.delete(conn, "workout_sessions", f"id = {session_id}")
    conn.close()
    return {"deleted": result}

# Упражнения внутри сессии (Session Exercises)

@app.post("/sessions/exercises/", tags=["Exercises"])
def add_exercise_to_session(ex: SessionExerciseCreate):
    conn = get_db_connection()
    res_id = sql.insert_session_exercise(
        conn, ex.session_id, ex.exercise_id, ex.sets, ex.reps, ex.weight, ex.notes
    )
    conn.close()
    return {"id": res_id}

@app.get("/sessions/{session_id}/details", tags=["Exercises"])
def get_workout_details(session_id: int):
    # Список упражнений в конкретной тренировке
    conn = get_db_connection()
    query = """
        SELECT se.*, e.name as exercise_name 
        FROM session_exercises se
        JOIN exercises e ON se.exercise_id = e.id
        WHERE se.session_id = ?
    """
    cur = conn.cursor()
    cur.execute(query, (session_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/sessions/exercises/{entry_id}", tags=["Exercises"])
def get_session_exercise(entry_id: int):
    # Получить данные конкретного подхода по ID
    conn = get_db_connection()
    result = sql.select_by_id(conn, "session_exercises", entry_id)
    conn.close()
    if result: return dict(result)
    raise HTTPException(status_code=404, detail="Exercise entry not found")

@app.put("/sessions/exercises/{entry_id}", tags=["Exercises"])
def update_session_exercise(entry_id: int, ex_data: SessionExerciseUpdate):
    conn = get_db_connection()
    data = ex_data.model_dump(exclude_unset=True)
    result = sql.update(conn, "session_exercises", data, f"id = {entry_id}")
    conn.close()
    return {"updated": result}

@app.delete("/sessions/exercises/{entry_id}", tags=["Exercises"])
def delete_session_exercise(entry_id: int):
    conn = get_db_connection()
    result = sql.delete(conn, "session_exercises", f"id = {entry_id}")
    conn.close()
    return {"deleted": result}

# Вес пользователя (Weight Log)

@app.post("/weight/", tags=["Progress"])
def add_weight(entry: WeightLogCreate):
    conn = get_db_connection()
    res_id = sql.insert_weight_log(conn, entry.user_id, entry.date, entry.weight)
    conn.close()
    return {"id": res_id}

@app.get("/weight/user/{user_id}", tags=["Progress"])
def get_weight_history(user_id: int):
    conn = get_db_connection()
    history = sql.select_all(conn, "weight_log", conditions=f"user_id = {user_id}", order_by="date DESC")
    conn.close()
    return [dict(h) for h in history]

@app.get("/weight/{entry_id}", tags=["Progress"])
def get_weight_entry(entry_id: int):
    # Получить конкретную запись о весе по ID
    conn = get_db_connection()
    result = sql.select_by_id(conn, "weight_log", entry_id)
    conn.close()
    if result: return dict(result)
    raise HTTPException(status_code=404, detail="Weight entry not found")

@app.delete("/weight/{entry_id}", tags=["Progress"])
def delete_weight(entry_id: int):
    conn = get_db_connection()
    result = sql.delete(conn, "weight_log", f"id = {entry_id}")
    conn.close()
    return {"deleted": result}


# --- ШАБЛОНЫ ТРЕНИРОВОК (Templates) ---

@app.post("/templates/", tags=["Templates"])
def create_template(temp: TemplateCreate):
    """Создать новый шаблон тренировки"""
    conn = get_db_connection()
    t_id = sql.insert_workout_template(
        conn, temp.user_id, temp.name, temp.description, temp.category, temp.is_public
    )
    conn.close()
    return {"id": t_id, "status": "template created"}


@app.get("/templates/", tags=["Templates"])
def get_templates(user_id: Optional[int] = None):
    """Получить список шаблонов (системные + публичные + личные пользователя)"""
    conn = get_db_connection()
    condition = "is_public = 1 OR user_id IS NULL"
    if user_id:
        condition = f"({condition}) OR (user_id = {user_id})"

    templates = sql.select_all(conn, "workout_templates", conditions=condition)
    conn.close()
    return [dict(t) for t in templates]


@app.get("/templates/{template_id}", tags=["Templates"])
def get_template(template_id: int):
    """Получить данные конкретного шаблона"""
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)
    conn.close()
    if template:
        return dict(template)
    raise HTTPException(status_code=404, detail="Template not found")


@app.put("/templates/{template_id}", tags=["Templates"])
def update_template(template_id: int, temp_data: TemplateUpdate, current_user_id: int):
    """Обновить шаблон (только если он принадлежит пользователю)"""
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)

    if not template:
        conn.close()
        raise HTTPException(status_code=404, detail="Template not found")

    if template['user_id'] is None:
        conn.close()
        raise HTTPException(status_code=403, detail="System templates cannot be modified")

    if template['user_id'] != current_user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="You can only edit your own templates")

    data = temp_data.model_dump(exclude_unset=True)
    result = sql.update(conn, "workout_templates", data, f"id = {template_id}")
    conn.close()
    return {"updated": result}


@app.delete("/templates/{template_id}", tags=["Templates"])
def delete_template(template_id: int, current_user_id: int):
    """Удалить шаблон (только свой)"""
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)

    if not template:
        conn.close()
        raise HTTPException(status_code=404, detail="Template not found")

    if template['user_id'] is None:
        conn.close()
        raise HTTPException(status_code=403, detail="System templates cannot be deleted")

    if template['user_id'] != current_user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="You can only delete your own templates")

    result = sql.delete(conn, "workout_templates", f"id = {template_id}")
    conn.close()
    return {"deleted": result}


# --- УПРАЖНЕНИЯ В ШАБЛОНАХ (Template Exercises) ---

@app.get("/templates/{template_id}/exercises", tags=["Templates"])
def get_template_exercises(template_id: int):
    """Получить структуру упражнений в шаблоне"""
    conn = get_db_connection()
    query = """
        SELECT te.*, e.name as exercise_name 
        FROM template_exercises te
        JOIN exercises e ON te.exercise_id = e.id
        WHERE te.template_id = ?
        ORDER BY te.order_index ASC
    """
    cur = conn.cursor()
    cur.execute(query, (template_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/templates/exercises/", tags=["Templates"])
def add_exercise_to_template(ex: TemplateExerciseCreate, current_user_id: int):
    """Добавить упражнение в свой шаблон"""
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", ex.template_id)

    if not template or template['user_id'] != current_user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot modify this template")

    res_id = sql.insert_template_exercise(
        conn, ex.template_id, ex.exercise_id, ex.sets, ex.reps, ex.weight, ex.order_index
    )
    conn.close()
    return {"id": res_id}


@app.put("/templates/exercises/{entry_id}", tags=["Templates"])
def update_template_exercise(entry_id: int, ex_data: TemplateExerciseUpdate, current_user_id: int):
    """Изменить параметры упражнения в своем шаблоне"""
    conn = get_db_connection()
    exercise_entry = sql.select_by_id(conn, "template_exercises", entry_id)

    if not exercise_entry:
        conn.close()
        raise HTTPException(status_code=404, detail="Exercise entry not found")

    template = sql.select_by_id(conn, "workout_templates", exercise_entry['template_id'])
    if not template or template['user_id'] != current_user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot modify this template")

    data = ex_data.model_dump(exclude_unset=True)
    result = sql.update(conn, "template_exercises", data, f"id = {entry_id}")
    conn.close()
    return {"updated": result}

@app.delete("/templates/exercises/{entry_id}", tags=["Templates"])
def delete_template_exercise(entry_id: int, current_user_id: int):
    """Удалить упражнение из своего шаблона"""
    conn = get_db_connection()
    exercise_entry = sql.select_by_id(conn, "template_exercises", entry_id)

    if not exercise_entry:
        conn.close()
        raise HTTPException(status_code=404, detail="Exercise entry not found")

    template = sql.select_by_id(conn, "workout_templates", exercise_entry['template_id'])
    if not template or template['user_id'] != current_user_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot modify this template")

    result = sql.delete(conn, "template_exercises", f"id = {entry_id}")
    conn.close()
    return {"deleted": result}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)