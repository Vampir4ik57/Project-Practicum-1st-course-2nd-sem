PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    created_date TEXT NOT NULL DEFAULT (datetime('now')),
    current_streak INTEGER NOT NULL DEFAULT 0,
    last_workout_date TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    muscle_group TEXT
);

CREATE TABLE IF NOT EXISTS workout_templates (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    is_public INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS template_exercises (
    id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL,
    exercise_id INTEGER NOT NULL,
    sets INTEGER,
    reps INTEGER,
    weight REAL,
    order_index INTEGER NOT NULL,
    FOREIGN KEY (template_id) REFERENCES workout_templates(id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    template_id INTEGER,
    name TEXT,
    date TEXT NOT NULL,
    times INTEGER,
    notes TEXT,
    status TEXT NOT NULL CHECK (status IN ('planned', 'completed')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (template_id) REFERENCES workout_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS session_exercises (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    exercise_id INTEGER,
    sets INTEGER,
    reps INTEGER,
    weight REAL,
    notes TEXT,
    FOREIGN KEY (session_id) REFERENCES workout_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS weight_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    weight REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_workout_sessions_user_date ON workout_sessions(user_id, date);
CREATE INDEX idx_workout_sessions_status ON workout_sessions(status);
CREATE INDEX idx_session_exercises_session ON session_exercises(session_id);
CREATE INDEX idx_template_exercises_template ON template_exercises(template_id);
CREATE INDEX idx_weight_log_user_date ON weight_log(user_id, date);
