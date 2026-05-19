from fastapi import FastAPI, HTTPException, Request, Form, Query, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List
import sqlite3
import uvicorn
from datetime import date, datetime, timedelta
import re
import sys
from passlib.context import CryptContext
import os
import shutil
from urllib.parse import quote
from pathlib import Path

app = FastAPI(title="Workout Planner API")

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
STATIC_DIR = PROJECT_ROOT / "frontend" / "static"
TEMPLATES_DIR = PROJECT_ROOT / "frontend" / "templates"
sys.path.append(str(PROJECT_ROOT / "database"))
import sql  # Модуль работы с БД
from sql import connection, insert

# Настройка веб-интерфейса FastAPI с учетом новой структуры
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Настройка хэширования
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Создаем папку для аватарок внутри новой структуры frontend/static/, если её нет
UPLOAD_DIR = STATIC_DIR / "uploads" / "avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Схемы данных (Pydantic) с валидацией (для этапа 4)
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

# 1. Отдаем HTML страницу авторизации при заходе на корень сайта
@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
async def show_auth_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth.html",
        context={}
    )

# 2. Обработка регистрации из HTML-формы
@app.post("/web/register", tags=["Web UI"])
async def web_register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    name: Optional[str] = Form(None) 
):
    conn = sql.connection("workouts.db")
    
    existing_user = sql.select_all(conn, "users", conditions=f"username = '{username}'")
    
    if existing_user:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={
                "reg_error": "Этот логин уже занят", 
                "show_reg": True
            }
        )

    # 2. Если логин свободен, создаем пользователя
    hashed_password = pwd_context.hash(password.encode('utf-8'))
    user_id = sql.insert_user(conn, username, hashed_password, name)
    if user_id:
        sql.update(
            conn, 
            "users", 
            {"avatar_url": "/static/images/default-avatar.jpg"}, 
            f"id = {user_id}"
        )
        conn.commit()
    conn.close()
    
    if user_id:
        return RedirectResponse(url="/?registered=true", status_code=303)
    else:
        return templates.TemplateResponse(
            request=request,
            name="auth.html",
            context={"reg_error": "Ошибка при создании аккаунта", "show_reg": True}
        )

# 3. Обработка входа из HTML-формы
@app.post("/web/login", tags=["Web UI"])
async def web_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    conn = get_db_connection() 
    try:
        # Ищем юзера
        users = sql.select_all(conn, "users", f"username = '{username}'")
    finally:
        conn.close()

    if users:
        user = users[0]
        stored_password = user['password_hash']

        is_valid = False
        
        if stored_password.startswith('$2b$'):
            try:
                is_valid = pwd_context.verify(password, stored_password)
            except Exception:
                is_valid = False
        
        if not is_valid:
            is_valid = (password == stored_password)

        if is_valid:
            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="user_id", value=str(user['id']), httponly=True)
            return response

    return templates.TemplateResponse(
        request=request, 
        name="auth.html", 
        context={"error": "Неверный логин или пароль"}
    )
@app.get("/dashboard", response_class=HTMLResponse, tags=["Web UI"])
async def dashboard_page(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
        
    def get_db_connection():
        conn = sqlite3.connect("../database/workouts.db")
        conn.row_factory = sqlite3.Row
        return conn

    conn = get_db_connection()
    user = sql.select_by_id(conn, "users", int(user_id))
    
    if not user:
        conn.close()
        return RedirectResponse(url="/", status_code=303)

    # Получаем сегодняшнюю дату в формате YYYY-MM-DD
    today_str = datetime.now().strftime("%Y-%m-%d")

    # перевод в пропущенные
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE workout_sessions
        SET status = 'missed'
        WHERE status = 'planned' 
          AND substr(date, 1, 10) < ? 
          AND user_id = ?
    """, (today_str, int(user_id)))
    conn.commit()             
    # Напоминание о тренировке
    has_flash_params = request.query_params.get("error") or request.query_params.get("success")
    
    if not has_flash_params:
        today_plans = sql.select_all(
            conn,
            "workout_sessions",
            conditions=f"user_id = {user_id} AND status = 'planned' AND substr(date, 1, 10) = '{today_str}'",
            order_by="date ASC LIMIT 1"
        )
        if today_plans:
            today_workout_name = today_plans[0]["name"] or "Обычная тренировка"
            raw_date = today_plans[0]["date"]
            
            # Извлекаем время (HH:MM) из строки ISO
            workout_time = ""
            if "T" in raw_date:
                workout_time = raw_date.split("T")[1][:5]
            
            conn.close()
            
            if workout_time:
                msg = f" Сегодня в {workout_time} по плану: {today_workout_name}!"
            else:
                msg = f" Сегодня по плану: {today_workout_name}!"
                
            return RedirectResponse(
                url=f"/dashboard?success={quote(msg, safe='')}",
                status_code=303
            )
    # Стрик по неделям
    user_dict = dict(user) # делаем копию для передачи в шаблон
    
    # Получаем цель из профиля (если еще не настроена, ставим 3 по умолчанию)
    weekly_goal = user_dict.get('weekly_goal') if user_dict.get('weekly_goal') is not None else 3
    
    # Извлекаем ВСЕ выполненные тренировки пользователя для исторического анализа недель
    all_completed_for_streak = sql.select_all(
        conn,
        "workout_sessions",
        conditions=f"user_id = {user_id} AND status = 'completed'"
    )
    
    # Группируем тренировки по ISO-неделям (ключ формата "Год-НомерНедели", например "2026-20")
    weeks_count = {}
    for s in all_completed_for_streak:
        d_str = s['date'].split('T')[0]
        try:
            d_obj = datetime.strptime(d_str, "%Y-%m-%d")
            year, week, _ = d_obj.isocalendar()
            key = f"{year}-{week}"
            weeks_count[key] = weeks_count.get(key, 0) + 1
        except Exception:
            continue

    calculated_streak = 0
    now = datetime.now()
    curr_year, curr_week, _ = now.isocalendar()
    curr_week_key = f"{curr_year}-{curr_week}"
     
    # Если норма уже выполнена, она сразу идет в зачет стрика
    if weeks_count.get(curr_week_key, 0) >= weekly_goal:
        calculated_streak += 1
    
    # Шагаем неделя за неделей назад в прошлое и проверяем выполнение нормы
    check_time = now - timedelta(days=7)
    while True:
        prev_year, prev_week, _ = check_time.isocalendar()
        prev_week_key = f"{prev_year}-{prev_week}"
        
        # Если в прошлую неделю цель была закрыта — стрик растет, идем дальше назад
        if weeks_count.get(prev_week_key, 0) >= weekly_goal:
            calculated_streak += 1
            check_time -= timedelta(days=7)
        else:
            break
            
    # Записываем актуальный стрик в БД
    sql.update(conn, "users", {"current_streak": calculated_streak}, f"id = {user_id}")
    user_dict['current_streak'] = calculated_streak
    
    completed_sessions = sql.select_all(
        conn,
        "workout_sessions",
        conditions=f"user_id = {user_id} AND status = 'completed'",
        order_by="date DESC LIMIT 8",
    )
    
    planned_sessions = sql.select_all(
        conn,
        "workout_sessions",
        conditions=f"user_id = {user_id} AND status = 'planned' AND substr(date, 1, 10) >= '{today_str}'",
        order_by="date ASC LIMIT 8",
    )

    templates_list = sql.select_all(
        conn,
        "workout_templates",
        conditions=f"user_id = {user_id} OR is_public = 1",
    )

    planned_count = len(sql.select_all(
        conn, "workout_sessions",
        conditions=f"user_id = {user_id} AND status = 'planned'",
    ))
    completed_count = len(sql.select_all(
        conn, "workout_sessions",
        conditions=f"user_id = {user_id} AND status = 'completed'",
    ))

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": user_dict,
            "completed_sessions": completed_sessions,
            "planned_sessions": planned_sessions,
            "templates_list": templates_list,
            "planned_count": planned_count,
            "completed_count": completed_count,
        },
    )

@app.get("/web/exercises", response_class=HTMLResponse, tags=["Web UI"])
async def get_exercises_page(request: Request, search: str = Query(None)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    cur = conn.cursor()
    
    # Логика поиска
    if search:
        query = "SELECT * FROM exercises WHERE LOWER(name) LIKE LOWER(?)"
        cur.execute(query, (f"%{search}%",))
    else:
        query = "SELECT * FROM exercises"
        cur.execute(query)

    exercises_list = cur.fetchall()
    conn.close()

    # Возвращаем ответ
    return templates.TemplateResponse(
        request=request, 
        name="exercises.html", 
        context={
            "exercises": exercises_list,
            "search_query": search
        }
    )

# Детальная страница упражнения
@app.get("/web/exercises/{exercise_id}", response_class=HTMLResponse, tags=["Web UI"])
async def get_exercise_detail(request: Request, exercise_id: int):
    conn = get_db_connection()
    exercise = sql.select_by_id(conn, "exercises", exercise_id)
    conn.close()
    return templates.TemplateResponse(
        request=request, 
        name="exercise_detail.html", 
        context={"ex": exercise}
    )

# Главная страница шаблонов
@app.get("/web/templates", response_class=HTMLResponse, tags=["Web UI"])
async def get_templates_page(
    request: Request, 
    search: str = Query(None), 
    category: str = Query(None),
    view: str = Query("my")
):
    current_user_id = int(request.cookies.get("user_id", 0))
    conn = get_db_connection()
    cur = conn.cursor()

    if view == "app":
        condition = "wt.user_id = 1"
    elif view == "community":
        condition = f"wt.is_public = 1 AND wt.user_id != 1"
    else:
        condition = f"wt.user_id = {current_user_id}"

    query = f"SELECT wt.*, u.username as author_name FROM workout_templates wt LEFT JOIN users u ON wt.user_id = u.id WHERE {condition}"
    params = []

    if search:
        query += " AND LOWER(wt.name) LIKE LOWER(?)"
        params.append(f"%{search}%")
    if category and category != "Все":
        query += " AND wt.category = ?"
        params.append(category)

    cur.execute(query, params)
    templates_list = cur.fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="templates_catalog.html", 
        context={
            "templates": templates_list,
            "search_query": search,
            "selected_category": category,
            "current_view": view,
            "categories": ["Силовая", "Кардио", "Растяжка", "Йога"]
        }
    )

# Страница создания шаблона
@app.get("/web/templates/create", response_class=HTMLResponse, tags=["Web UI"])
async def create_template_page(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
        
    conn = get_db_connection()
    exercises = sql.select_all(conn, "exercises")
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="create_template.html",
        context={
            "exercises": exercises,
            "categories": ["Силовая", "Кардио", "Растяжка", "Йога"]
        }
    )
# Обработка создания шаблона (Сохранение в БД)
@app.post("/web/templates/create", tags=["Web UI"])
async def web_create_template(
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    is_public: Optional[str] = Form(None), 
    exercise_ids: List[int] = Form(...),
    sets: List[int] = Form(...),
    reps: List[int] = Form(...),
    weights: List[float] = Form(...)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
        
    conn = get_db_connection()
    
    public_flag = 1 if is_public else 0
    
    # Создаем сам шаблон с обработанным флагом
    template_id = sql.insert_workout_template(
        conn, int(user_id), name, description, category, public_flag
    )
    
    # Добавляем упражнения в шаблон
    if template_id:
        for i in range(len(exercise_ids)):
            sql.insert_template_exercise(
                conn, 
                template_id, 
                exercise_ids[i], 
                sets[i], 
                reps[i], 
                weights[i], 
                i  # order_index
            )
    
    conn.commit()
    conn.close()
    ok_text = " Шаблон успешно создан и добавлен в ваш каталог!"
    return RedirectResponse(
        url=f"/web/templates?view=my&success={quote(ok_text, safe='')}", 
        status_code=303
    )

# Страница деталей шаблона
@app.get("/web/templates/{template_id}", response_class=HTMLResponse, tags=["Web UI"])
async def get_template_detail(request: Request, template_id: int):
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)
    # Получаем упражнения этого шаблона
    query = """
        SELECT te.*, e.name
        FROM template_exercises te
        JOIN exercises e ON te.exercise_id = e.id
        WHERE te.template_id = ?
        ORDER BY te.order_index ASC
    """
    cur = conn.cursor()
    cur.execute(query, (template_id,))
    exercises = cur.fetchall()
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="template_detail.html",
        context={"template": template, "exercises": exercises}
    )

@app.get("/web/templates/delete/{template_id}", tags=["Web UI"])
async def web_delete_template(request: Request, template_id: int):
    user_id_cookie = request.cookies.get("user_id")
    if not user_id_cookie:
        # Если куки нет — значит пользователь не залогинен
        return RedirectResponse(url="/", status_code=303)

    current_user_id = int(user_id_cookie)
    
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)

    if not template or template['user_id'] != current_user_id:
        conn.close()
        return RedirectResponse(url="/web/templates?view=my&error=forbidden", status_code=303)

    # Если проверка прошла — удаляем
    sql.delete(conn, "template_exercises", f"template_id = {template_id}")
    sql.delete(conn, "workout_templates", f"id = {template_id}")
    
    conn.close()
    ok_text = " Шаблон успешно удален из вашего каталога!"
    return RedirectResponse(
        url=f"/web/templates?view=my&success={quote(ok_text, safe='')}", 
        status_code=303
    )

# Страница редактирования шаблона
@app.get("/web/templates/edit/{template_id}", tags=["Web UI"])
async def web_edit_template_page(request: Request, template_id: int):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    # Получаем сам шаблон
    template = sql.select_by_id(conn, "workout_templates", template_id)
    
    # Проверка на владельца
    if not template or template['user_id'] != int(user_id):
        conn.close()
        return RedirectResponse(url="/web/templates?view=my&error=forbidden", status_code=303)

    # Получаем текущие упражнения этого шаблона
    current_exercises = sql.select_all(conn, "template_exercises", f"template_id = {template_id}")
    
    # Получаем список всех доступных упражнений для выпадающего списка
    all_exercises = sql.select_all(conn, "exercises")
    
    categories = ["Силовая", "Кардио", "Растяжка", "Йога"]
    conn.close()

    return templates.TemplateResponse(
    request=request, 
    name="edit_template.html", 
    context={
        "template": template,
        "current_exercises": current_exercises,
        "all_exercises": all_exercises,
        "categories": categories
    }
)

@app.post("/web/templates/edit/{template_id}", tags=["Web UI"])
async def web_edit_template_save(
    template_id: int,
    request: Request,
    name: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    is_public: Optional[str] = Form(None), 
    exercise_ids: List[int] = Form(...),
    sets: List[int] = Form(...),
    reps: List[int] = Form(...),
    weights: List[float] = Form(...) 
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    
    # Обновляем основные данные шаблона
    template_data = {
        "name": name,
        "category": category,
        "description": description,
        "is_public": 1 if is_public else 0
    }
    sql.update(conn, "workout_templates", template_data, f"id = {template_id}")

    # Очищаем старые упражнения
    sql.delete(conn, "template_exercises", f"template_id = {template_id}")
    
    # Записываем новые упражнения
    for i, (ex_id, s, r, w) in enumerate(zip(exercise_ids, sets, reps, weights)):
        ex_data = {
            "template_id": template_id,
            "exercise_id": int(ex_id),
            "sets": int(s),
            "reps": int(r),
            "weight": float(w),
            "order_index": i 
        }
        sql.insert(conn, "template_exercises", ex_data)

    conn.commit() 
    conn.close()
    
    ok_text = " Шаблон успешно обновлен!"
    return RedirectResponse(
        url=f"/web/templates?view=my&success={quote(ok_text, safe='')}", 
        status_code=303
    )

# профиль пользователя
@app.get("/web/profile", tags=["Web UI"])
async def web_profile_page(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    user_data = sql.select_by_id(conn, "users", int(user_id))
    
    # Получаем историю веса
    weight_history = sql.select_all(conn, "weight_log", f"user_id = {user_id} ORDER BY date ASC")
    conn.close()
    
    labels = [str(row['date']) for row in weight_history]
    values = [float(row['weight']) for row in weight_history]

    flash_error = request.query_params.get("error")
    flash_success = request.query_params.get("success")

    return templates.TemplateResponse(
        request=request, 
        name="profile.html", 
        context={
            "user": user_data,
            "labels": labels,
            "values": values,
            "error": flash_error,
            "success": flash_success,
        }
    )
# Обновление веса
@app.post("/web/profile/add-weight", tags=['Web UI'])
async def web_add_weight(request: Request, weight: float = Form(...)):
    user_id = request.cookies.get("user_id")
    if not user_id: return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    sql.insert(conn, "weight_log", {
        "user_id": user_id,
        "date": date.today().isoformat(),
        "weight": weight
    })
    conn.close()
    
    success_text = f" Вес успешно записан: {weight} кг! Так держать!"
    return RedirectResponse(
        url=f"/web/profile?success={quote(success_text, safe='')}", 
        status_code=303
    )

@app.post("/web/profile/update-settings", tags=["Web UI"])
async def web_update_settings(
    request: Request,
    current_password: str = Form(...),
    name: str = Form(default=""),
    new_password: str = Form(default=""),
    weekly_goal: int = Form(default=3)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    user = sql.select_by_id(conn, "users", int(user_id))
    user = dict(user)
    stored_password = user['password_hash']
    
    error_msg = None
    update_data = {}

    # Правильный ли текущий пароль? (Гибридная проверка)
    is_valid_password = False
    if stored_password.startswith('$2b$'):
        try:
            is_valid_password = pwd_context.verify(current_password, stored_password)
        except:
            is_valid_password = False
    else:
        is_valid_password = (current_password == stored_password)

    if not is_valid_password:
        error_msg = " Неверный текущий пароль! Изменения не сохранены."

    if not error_msg:
        # Проверяем изменение имени
        if name and name != user['name']:
            update_data['name'] = name
            
        current_db_goal = user.get('weekly_goal') if user.get('weekly_goal') is not None else 3
        if weekly_goal != current_db_goal:
            update_data['weekly_goal'] = weekly_goal
            
        # Проверяем изменение пароля
        if new_password:
            # Совпадает ли новый пароль с текущим?
            if pwd_context.verify(new_password, stored_password) or new_password == stored_password:
                error_msg = " Новый пароль не должен совпадать с текущим!"
            else:
                update_data['password_hash'] = pwd_context.hash(new_password)

        # Было ли вообще что-то изменено?
        if not update_data and not error_msg:
            error_msg = " Вы ввели те же данные. Изменений для сохранения нет."

    # Если нет ошибок и есть что обновлять — делаем UPDATE
    if not error_msg and update_data:
        sql.update(conn, "users", update_data, f"id = {user_id}")
        conn.commit()
        conn.close()
        
        ok_text = " Настройки профиля успешно обновлены и сохранены!"
        return RedirectResponse(
            url=f"/web/profile?success={quote(ok_text, safe='')}",
            status_code=303,
        )

    conn.close()

    msg = error_msg or " Не удалось сохранить изменения настроек."
    return RedirectResponse(
        url=f"/web/profile?error={quote(msg, safe='')}",
        status_code=303,
    )

@app.get("/web/logout", tags=["Web UI"])
async def web_logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response

@app.post("/web/profile/upload-avatar", tags=["Web UI"])
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    file_extension = file.filename.split(".")[-1]
    file_name = f"avatar_{user_id}.{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    # Сохраняем файл на диск
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_path = f"../frontend/static/uploads/avatars/{file_name}"
    conn = get_db_connection()
    sql.update(conn, "users", {"avatar_url": db_path}, f"id = {user_id}")
    conn.close()
    success_text = f"Ваш аватар успешно загружен!" 
    return RedirectResponse(
        url=f"/web/profile?success={quote(success_text, safe='')}", 
        status_code=303
    )

def _apply_streak_on_completed(conn, user_id: int, workout_date_str: str):
    # Увеличивает стрик, если тренировка отмечена выполненной.
    user = sql.select_by_id(conn, "users", user_id)
    if not user:
        return
    today_str = datetime.now().strftime("%Y-%m-%d")
    if workout_date_str != today_str or user["last_workout_date"] == today_str:
        return
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    new_streak = user["current_streak"] + 1 if user["last_workout_date"] == yesterday_str else 1
    sql.update(conn, "users", {
        "current_streak": new_streak,
        "last_workout_date": today_str,
    }, f"id = {user_id}")

def _snapshot_template_exercises(conn, session_id: int):
    # Автоматически находит шаблон сессии и переносит из него упражнения
    cur = conn.cursor()
    
    cur.execute("SELECT template_id FROM workout_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    if not row or not row['template_id']:
        print(f"[SNAPSHOT LOG] Шаблон для сессии {session_id} не найден.")
        return
        
    try:
        template_id = int(row['template_id'])
    except (ValueError, TypeError):
        print(f"[SNAPSHOT LOG] Некорректный ID шаблона: {row['template_id']}")
        return
    
    cur.execute("SELECT COUNT(*) FROM session_exercises WHERE session_id = ?", (session_id,))
    if cur.fetchone()[0] > 0:
        print(f"[SNAPSHOT LOG] Упражнения для сессии {session_id} уже существуют.")
        return

    cur.execute("""
        INSERT INTO session_exercises (session_id, exercise_id, sets, reps, weight, notes)
        SELECT ?, exercise_id, sets, reps, weight, ''
        FROM template_exercises
        WHERE template_id = ?
    """, (session_id, template_id))
    
    conn.commit()
    print(f"[SNAPSHOT LOG] Успешно скопированы упражнения из шаблона {template_id} в сессию {session_id}!")


# Для календаря
@app.get("/api/get-workouts")
async def get_workouts_api(request: Request, start: str = Query(...), end: str = Query(...)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return JSONResponse(content=[], status_code=401)

    start_day = start[:10]
    end_day = end[:10]

    conn = get_db_connection()
    sessions = sql.select_all(
        conn,
        "workout_sessions",
        conditions=(
            f"user_id = {user_id} AND substr(date, 1, 10) >= '{start_day}' "
            f"AND substr(date, 1, 10) < '{end_day}'"
        ),
        order_by="date ASC",
    )
    conn.close()

    events = []
    for s in sessions:
        is_completed = s["status"] == "completed"
        events.append({
            "id": str(s["id"]),
            "title": s["name"] or "Тренировка",
            "start": s["date"],
            "backgroundColor": "rgba(0, 255, 136, 0.2)" if is_completed else "rgba(0, 210, 255, 0.2)",
            "borderColor": "#00ff88" if is_completed else "#00d2ff",
            "textColor": "#ffffff",
            "classNames": ["fc-event-completed" if is_completed else "fc-event-planned"],
            "extendedProps": {
                "status": s["status"],
                "notes": s["notes"] or "",
                "template_id": s["template_id"],
                "date_raw": s["date"],
            },
        })

    return JSONResponse(content=events)

@app.get("/web/dashboard", response_class=HTMLResponse, tags = ['Web UI'])
async def web_calendar_page(request: Request):
    return RedirectResponse(url="/dashboard", status_code=303)

# Обработчик быстрого добавления тренировки из календаря
def _session_name_from_template(conn, template_id: int) -> str:
    template = sql.select_by_id(conn, "workout_templates", template_id)
    if not template:
        return "Тренировка"
    return template["name"]


@app.post("/web/dashboard/add-session", tags = ['Web UI'])
async def add_calendar_session(
    request: Request,
    template_id: Optional[int] = Form(None),
    custom_name: Optional[str] = Form(None),
    date_time: str = Form(...),
    status: str = Form(...),
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    chosen_date = datetime.strptime(date_time, "%Y-%m-%dT%H:%M")
    now_time = datetime.now().replace(second=0, microsecond=0)

    # Валидация времени для планов
    if status == "planned":
        if chosen_date < now_time:
            # Запрещаем планировать в прошлое. Перенаправляем с ошибкой
            return RedirectResponse(url="/dashboard?error=cannot_plan_in_past", status_code=303)

    # Защита от выполненных тренировок в будущем
    if status == "completed":
        if chosen_date.date() > now_time.date():
            # Запрещаем ставить статус "Выполнено" на завтра и более поздние дни
            return RedirectResponse(url="/dashboard?error=cannot_complete_in_future", status_code=303)

    conn = get_db_connection()
    
    name = custom_name
    if template_id and not name:
        template = sql.select_by_id(conn, "workout_templates", template_id)
        if template:
            name = template["name"]
            
    if not name or name.strip() == "":
        name = "Обычная тренировка"

    session_data = {
        "user_id": int(user_id),
        "template_id": template_id if template_id else None,
        "name": name,
        "date": date_time,
        "status": status,
        "notes": "",
    }
    res_id = sql.insert(conn, "workout_sessions", session_data)
    session_id = res_id if res_id else conn.cursor().lastrowid
    if status == "completed":
        _apply_streak_on_completed(conn, int(user_id), date_time.split("T")[0])
        _snapshot_template_exercises(conn, session_id)

    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/web/dashboard/session/{session_id}/update", tags = ['Web UI'])
async def update_calendar_session(
    request: Request,
    session_id: int,
    template_id: Optional[int] = Form(None),
    custom_name: Optional[str] = Form(None),
    date_time: str = Form(...),
    status: str = Form(...),
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
        
    chosen_date = datetime.strptime(date_time, "%Y-%m-%dT%H:%M")
    now_time = datetime.now().replace(second=0, microsecond=0)

    if status == "planned":
        if chosen_date < now_time:
            return RedirectResponse(url="/dashboard?error=cannot_plan_in_past", status_code=303)

    if status == "completed":
        if chosen_date.date() > now_time.date():
            return RedirectResponse(
                url="/dashboard?error=cannot_complete_in_future", 
                status_code=303
            )

    conn = get_db_connection()
    session = sql.select_by_id(conn, "workout_sessions", session_id)
    if not session or session["user_id"] != int(user_id):
        conn.close()
        return RedirectResponse(url="/dashboard", status_code=303)

    if session["status"] == "completed":
        conn.close()
        return RedirectResponse(url="/dashboard?error=completed_cannot_be_modified", status_code=303)

    name = custom_name
    if template_id and not name:
        template = sql.select_by_id(conn, "workout_templates", template_id)
        if template:
            name = template["name"]
    if not name or not str(name).strip():
        name = session["name"] or "Обычная тренировка"

    was_completed = session["status"] == "completed"

    sql.update(
        conn,
        "workout_sessions",
        {
            "template_id": template_id if template_id else None,
            "name": name,
            "date": date_time,
            "status": status,
        },
        f"id = {session_id}",
    )

    if status == "completed" and not was_completed:
        _apply_streak_on_completed(conn, int(user_id), date_time.split("T")[0])

        _snapshot_template_exercises(conn, session_id)
    conn.close()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/web/dashboard/session/{session_id}/complete", tags = ['Web UI'])
async def complete_calendar_session(request: Request, session_id: int):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return JSONResponse({"ok": False}, status_code=401)

    conn = get_db_connection()
    session = sql.select_by_id(conn, "workout_sessions", session_id)
    if not session or session["user_id"] != int(user_id):
        conn.close()
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    
    session_date_only = session['date'].split('T')[0]  # Из "2026-05-20T15:00" получаем "2026-05-20"
    today_only = datetime.now().strftime("%Y-%m-%d")

    if session_date_only != today_only:
        conn.close()
        return JSONResponse(
            status_code=400, 
            content={"detail": "Завершить тренировку можно только в день её проведения!"}
        )

    sql.update(conn, "workout_sessions", {"status": "completed"}, f"id = {session_id}")
    _apply_streak_on_completed(conn, int(user_id), session["date"].split("T")[0])
    _snapshot_template_exercises(conn, session_id)
    conn.close()
    return JSONResponse({"ok": True})


@app.post("/web/dashboard/session/{session_id}/delete", tags = ['Web UI'])
async def delete_calendar_session(request: Request, session_id: int):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return JSONResponse({"ok": False}, status_code=401)

    conn = get_db_connection()
    session = sql.select_by_id(conn, "workout_sessions", session_id)
    if not session or session["user_id"] != int(user_id):
        conn.close()
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)

    # Запрещаем удалять выполненные тренировки
    if session["status"] == "completed":
        conn.close()
        return JSONResponse({"ok": False, "error": "completed_cannot_be_deleted"}, status_code=400)

    sql.delete(conn, "workout_sessions", f"id = {session_id}")
    conn.close()
    return JSONResponse({"ok": True})

@app.get("/web/plates-calculator", response_class=HTMLResponse, tags=["Web UI"])
async def plates_calculator_page(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    user_data = sql.select_by_id(conn, "users", int(user_id))
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="plates_calculator.html",
        context={"user": user_data}
    )

@app.get("/web/feedback", response_class=HTMLResponse, tags=["Web UI"])
async def feedback_page(request: Request):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    conn = get_db_connection()
    user_data = sql.select_by_id(conn, "users", int(user_id))
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="feedback.html",
        context={
            "user": user_data,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error")
        }
    )

@app.post("/web/feedback/send", tags=["Web UI"])
async def send_feedback(
    request: Request,
    rating: int = Form(...),
    subject: Optional[str] = Form(None),
    message: str = Form(...)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    if not message.strip():
        return RedirectResponse(url="/web/feedback?error=Сообщение+не+может+быть+пустым", status_code=303)

    conn = get_db_connection()
    feedback_data = {
        "user_id": int(user_id),
        "rating": rating,
        "subject": subject,
        "message": message
    }
    
    sql.insert(conn, "feedback", feedback_data)
    conn.close()

    ok_text = "Спасибо! Ваш отзыв успешно отправлен."
    return RedirectResponse(url=f"/web/feedback?success={quote(ok_text, safe='')}", status_code=303)

@app.get("/web/history", response_class=HTMLResponse, tags=["Web UI"])
async def show_history_page(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
        
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = """
        SELECT ws.id, ws.name, ws.date, ws.template_id, wt.category as template_category
        FROM workout_sessions ws
        LEFT JOIN workout_templates wt ON ws.template_id = wt.id
        WHERE ws.user_id = ? AND ws.status = 'completed'
    """
    params = [int(user_id)]

    if date_from:
        query += " AND substr(ws.date, 1, 10) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND substr(ws.date, 1, 10) <= ?"
        params.append(date_to)

    query += " ORDER BY ws.date DESC"
    
    cur.execute(query, tuple(params))
    sessions_rows = cur.fetchall()
    sessions = []
    
    for row in sessions_rows:
        session_dict = dict(row)
        session_id = session_dict['id']
        
        workout_name = (session_dict.get('name') or "").lower()
        db_category = session_dict.get('template_category')
        
        # Если шаблон удален или у него нет категории, угадываем по названию тренировки
        if not db_category:
            if any(word in workout_name for word in ["жим", "присед", "тяга", "грудь", "руки", "спина", "ноги", "силов", "бицепс", "трицепс"]):
                session_dict['category'] = "Силовая"
            elif any(word in workout_name for word in ["бег", "кардио", "вело", "дорожка", "эллипс", "скакалка", "кросс"]):
                session_dict['category'] = "Кардио"
            elif any(word in workout_name for word in ["растяж", "шпагат", "гибкост", "flex"]):
                session_dict['category'] = "Растяжка"
            elif any(word in workout_name for word in ["йога", "yoga", "асана", "медитац"]):
                session_dict['category'] = "Йога"
            else:
                session_dict['category'] = "Общая" # Если вообще ничего не совпало
        else:
            # Если шаблон существует, берем его родную категорию
            session_dict['category'] = db_category
        
        cur.execute("""
            SELECT se.sets, se.reps, se.weight, se.notes, e.name as exercise_name
            FROM session_exercises se
            JOIN exercises e ON se.exercise_id = e.id
            WHERE se.session_id = ?
        """, (session_id,))
        
        exercises_rows = cur.fetchall()
        session_dict['exercises'] = [dict(ex) for ex in exercises_rows]
        
        try:
            dt_str = session_dict['date'].replace('Z', '')
            if 'T' in dt_str:
                dt = datetime.fromisoformat(dt_str)
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            session_dict['formatted_date'] = dt.strftime("%d.%m.%Y")
            session_dict['formatted_time'] = dt.strftime("%H:%M")
        except:
            session_dict['formatted_date'] = session_dict['date']
            session_dict['formatted_time'] = ""
            
        sessions.append(session_dict)
        
    conn.close()
    
    return templates.TemplateResponse( 
        request=request, 
        name="history.html", 
        context={
            "sessions": sessions, 
            "date_from": date_from, 
            "date_to": date_to
        }
    )

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


# шаблоны тренировок

@app.post("/templates/", tags=["Templates"])
def create_template(temp: TemplateCreate):
    # Создать новый шаблон тренировки
    conn = get_db_connection()
    t_id = sql.insert_workout_template(
        conn, temp.user_id, temp.name, temp.description, temp.category, temp.is_public
    )
    conn.close()
    return {"id": t_id, "status": "template created"}


@app.get("/templates/", tags=["Templates"])
def get_templates(user_id: Optional[int] = None):
    # Получить список шаблонов (системные + публичные + личные пользователя)
    conn = get_db_connection()
    condition = "is_public = 1 OR user_id IS NULL"
    if user_id:
        condition = f"({condition}) OR (user_id = {user_id})"

    templates = sql.select_all(conn, "workout_templates", conditions=condition)
    conn.close()
    return [dict(t) for t in templates]


@app.get("/templates/{template_id}", tags=["Templates"])
def get_template(template_id: int):
    # Получить данные конкретного шаблона
    conn = get_db_connection()
    template = sql.select_by_id(conn, "workout_templates", template_id)
    conn.close()
    if template:
        return dict(template)
    raise HTTPException(status_code=404, detail="Template not found")


@app.put("/templates/{template_id}", tags=["Templates"])
def update_template(template_id: int, temp_data: TemplateUpdate, current_user_id: int):
    # Обновить шаблон (только если он принадлежит пользователю)
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
    # Удалить шаблон (только свой)
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


# Упражнения в шаблонах

@app.get("/templates/{template_id}/exercises", tags=["Templates"])
def get_template_exercises(template_id: int):
    # Получить структуру упражнений в шаблоне
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
    # Добавить упражнение в свой шаблон
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
    # Изменить параметры упражнения в своем шаблоне
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
    # Удалить упражнение из своего шаблона
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