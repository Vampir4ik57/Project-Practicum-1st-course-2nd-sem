import sqlite3
from sqlite3 import Error
from pathlib import Path
# Папка, где лежит текущий файл sql.py (это папка проекта/database)
DATABASE_DIR = Path(__file__).resolve().parent

def connection(db_file="workouts.db"):
    """Создает подключение к SQLite, всегда сохраняя файл в папке database/"""
    db_path = DATABASE_DIR / db_file
    try:
        # Конвертируем путь Path в обычную строку для sqlite3
        connect = sqlite3.connect(str(db_path))
        connect.execute("PRAGMA foreign_keys = ON;")
        return connect
    except Error as e:
        print(f"[DB ERROR] Ошибка подключения к базе данных: {e}")
        return None

def insert_user(conn, username, password_hash, name=None):
    # Добавляет нового пользователя. Возвращает его ID.
    sql = "INSERT INTO users (username, password_hash, name) VALUES (?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (username, password_hash, name))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки пользователя: {e}")
        return None
def insert(conn, table, data: dict):
    # Универсальная вставка данных. data: словарь вида {"column_name": value}
    cursor = conn.cursor()
    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?" for _ in data])
    values = tuple(data.values())
    
    query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
    try:
        cursor.execute(query, values)
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"Ошибка универсальной вставки в {table}: {e}")
        return None

def insert_workout_session(conn, user_id, name, date, status='planned', template_id=None, times=None, notes=None):
    # Добавляет тренировочную сессию. Возвращает её ID.
    sql = """INSERT INTO workout_sessions 
             (user_id, template_id, name, date, times, notes, status) 
             VALUES (?, ?, ?, ?, ?, ?, ?)"""
    cur = conn.cursor()
    try:
        cur.execute(sql, (user_id, template_id, name, date, times, notes, status))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки тренировки: {e}")
        return None

def insert_exercise(conn, name, description=None, muscle_group=None):
    # Добавляет упражнение в справочник. Возвращает его ID.
    sql = "INSERT INTO exercises (name, description, muscle_group) VALUES (?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (name, description, muscle_group))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки упражнения: {e}")
        return None

def insert_workout_template(conn, user_id, name, description=None, category=None, is_public=0):
    # Добавляет шаблон тренировки. Возвращает его ID.
    sql = "INSERT INTO workout_templates (user_id, name, description, category, is_public) VALUES (?, ?, ?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (user_id, name, description, category, is_public))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки шаблона: {e}")
        return None

def insert_template_exercise(conn, template_id, exercise_id, sets, reps, weight, order_index):
    # Добавляет упражнение в шаблон. Возвращает ID записи.
    sql = "INSERT INTO template_exercises (template_id, exercise_id, sets, reps, weight, order_index) VALUES (?, ?, ?, ?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (template_id, exercise_id, sets, reps, weight, order_index))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки упражнения в шаблон: {e}")
        return None

def insert_session_exercise(conn, session_id, exercise_id, sets, reps, weight, notes=None):
    # Добавляет выполненное упражнение в тренировку. Возвращает ID записи.
    sql = "INSERT INTO session_exercises (session_id, exercise_id, sets, reps, weight, notes) VALUES (?, ?, ?, ?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (session_id, exercise_id, sets, reps, weight, notes))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки упражнения в сессию: {e}")
        return None

def insert_weight_log(conn, user_id, date, weight):
    # Добавляет запись о весе пользователя. Возвращает ID записи.
    sql = "INSERT INTO weight_log (user_id, date, weight) VALUES (?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (user_id, date, weight))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки веса: {e}")
        return None


def select_all(connect, table, conditions=None, order_by=None):
    # Возвращает все строки таблицы, удовлетворяющие условиям. conditions – строка WHERE, например "user_id = 1". order_by – строка ORDER BY, например "date DESC".
    sql = f"SELECT * FROM {table}"
    if conditions:
        sql += f" WHERE {conditions}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    cur = connect.cursor()
    try:
        cur.execute(sql)
        return cur.fetchall()
    except Error as e:
        print(f"Ошибка выборки: {e}")
        return []

def select_by_id(connect, table, record_id, id_column='id'):
    # Возвращает одну запись по значению ID (или другому указанному полю).
    sql = f"SELECT * FROM {table} WHERE {id_column} = ?"
    cur = connect.cursor()
    try:
        cur.execute(sql, (record_id,))
        return cur.fetchone()
    except Error as e:
        print(f"Ошибка выборки по ID: {e}")
        return None

def update(connect, table, data, condition):
    # Обновляет записи в таблице. Возвращает количество изменённых строк.
    set_clause = ', '.join([f"{col} = ?" for col in data.keys()])
    sql = f"UPDATE {table} SET {set_clause} WHERE {condition}"
    cur = connect.cursor()
    try:
        cur.execute(sql, list(data.values()))
        connect.commit()
        return cur.rowcount
    except Error as e:
        print(f"Ошибка обновления: {e}")
        return 0

def delete(connect, table, condition):
    # Удаляет записи из таблицы по условию. Возвращает количество удалённых строк.
    sql = f"DELETE FROM {table} WHERE {condition}"
    cur = connect.cursor()
    try:
        cur.execute(sql)
        connect.commit()
        return cur.rowcount
    except Error as e:
        print(f"Ошибка удаления: {e}")
        return 0

def beautiful_select(conn, query, params=None):
    # Выполняет SELECT и выводит результат в виде красивой таблицы.
    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    rows = cursor.fetchall()
    if not rows:
        print("Нет данных.")
        return rows

    # Получаем имена столбцов
    names = [desc[0] for desc in cursor.description]
    # Вставляем строку с заголовками
    rows_with_header = [names] + list(rows)

    # Вычисляем ширину каждого столбца
    col_widths = []
    for i in range(len(names)):
        max_len = max(len(str(row[i])) for row in rows_with_header)
        col_widths.append(max_len + 2)

    # Формируем строку форматирования
    fmt = ''.join(f'{{:<{w}}}' for w in col_widths)
    # Печатаем заголовки
    print(fmt.format(*names))
    # Печатаем разделитель
    print('-' * sum(col_widths))
    # Печатаем строки данных
    for row in rows:
        safe_row = [str(val) if val is not None else "NULL" for val in row]
        print(fmt.format(*safe_row))
    return rows


def init_db(conn, schema_file="Create DB.sql"):
    """Ищет SQL-скрипт инициализации строго внутри папки database/"""
    schema_path = DATABASE_DIR / schema_file
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_schema = f.read()
        cursor = conn.cursor()
        cursor.executescript(sql_schema)
        conn.commit()
        print("[DB] Структура базы данных успешно инициализирована.")
    except Exception as e:
        print(f"[DB ERROR] Не удалось прочитать или выполнить файл схемы {schema_path}: {e}")

"""
# --- БЛОК ТЕСТИРОВАНИЯ ---
if __name__ == "__main__":
    # 1. Подключаемся к БД
    conn = connection("workouts.db")

    if conn is not None:
        # 2. Инициализируем таблицы (предполагается, что SQL код лежит в schema.sql)
        init_db(conn, "Create DB.sql")
        # 3. Тестируем добавление пользователя
        print("\n--- Добавление пользователя ---")
        user_id = insert_user(conn, "johndoe", "hashedpassword123", "John Doe")
        print(f"Добавлен пользователь с ID: {user_id}")

        # 4. Тестируем добавление упражнения
        exercise_id = insert_exercise(conn, "Жим лежа", "Базовое упражнение со штангой", "Грудь")

        # 5. Тестируем создание тренировочной сессии
        print("\n--- Добавление тренировки ---")
        # Убедись, что статус совпадает с CHECK в SQL таблице!
        session_id = insert_workout_session(
            conn,
            user_id=user_id,
            name="Грудь и трицепс",
            date="2024-05-20",
            status="planned"  # или "planned", если исправишь SQL
        )
        print(f"Создана тренировка с ID: {session_id}")

        # 6. Проверяем выборку данных с помощью твоей функции beautiful_select
        print("\n--- Таблица пользователей ---")
        beautiful_select(conn, "SELECT id, username, name, created_date, current_streak FROM users")

        print("\n--- Таблица тренировок ---")
        beautiful_select(conn, "SELECT id, user_id, name, date, status FROM workout_sessions")

        # Закрываем соединение
        conn.close()"""
