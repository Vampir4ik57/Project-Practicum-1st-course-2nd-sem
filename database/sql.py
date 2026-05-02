import sqlite3
from sqlite3 import Error

def connection(db_file="workouts.db"):
    try:
        connect = sqlite3.connect(db_file)
        connect.execute("PRAGMA foreign_keys = ON;")
        return connect
    except Error as e:
        print(f"Ошибка подключения: {e}")
        return None

def insert_user(conn, username, password_hash, name=None):
    """Добавляет нового пользователя. Возвращает его ID."""
    sql = "INSERT INTO users (username, password_hash, name) VALUES (?, ?, ?)"
    cur = conn.cursor()
    try:
        cur.execute(sql, (username, password_hash, name))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        print(f"Ошибка вставки пользователя: {e}")
        return None

def insert_workout_session(conn, user_id, name, date, status='planned', template_id=None, times=None, notes=None):
    """Добавляет тренировочную сессию. Возвращает её ID."""
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
    """Добавляет упражнение в справочник. Возвращает его ID."""
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
    """Добавляет шаблон тренировки. Возвращает его ID."""
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
    """Добавляет упражнение в шаблон. Возвращает ID записи."""
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
    """Добавляет выполненное упражнение в тренировку. Возвращает ID записи."""
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
    """Добавляет запись о весе пользователя. Возвращает ID записи."""
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
    """
    Возвращает все строки таблицы, удовлетворяющие условиям.
    conditions – строка WHERE, например "user_id = 1".
    order_by – строка ORDER BY, например "date DESC".
    """
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
    """
    Возвращает одну запись по значению ID (или другому указанному полю).
    """
    sql = f"SELECT * FROM {table} WHERE {id_column} = ?"
    cur = connect.cursor()
    try:
        cur.execute(sql, (record_id,))
        return cur.fetchone()
    except Error as e:
        print(f"Ошибка выборки по ID: {e}")
        return None

def update(connect, table, data, condition):
    """
    Обновляет записи в таблице.
    Возвращает количество изменённых строк.
    """
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
    """
    Удаляет записи из таблицы по условию.
    Возвращает количество удалённых строк.
    """
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
    """
    Выполняет SELECT и выводит результат в виде красивой таблицы.
    """
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

def init_db(conn, sql_filename="Create DB.sql"):
    """Читает SQL файл и создает таблицы."""
    with open(sql_filename, "r", encoding="utf-8") as f:
        sql_script = f.read()
    try:
        conn.executescript(sql_script)
        print("База данных успешно инициализирована.")
    except Error as e:
        print(f"Ошибка создания таблиц: {e}")
