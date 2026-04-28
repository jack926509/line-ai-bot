"""DDL：建表、補欄位、索引"""
from db.pool import get_db, logger


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                content    TEXT NOT NULL,
                done       BOOLEAN DEFAULT FALSE,
                category   TEXT DEFAULT '一般',
                due_date   DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if not _column_exists(cur, "todos", "category"):
            cur.execute("ALTER TABLE todos ADD COLUMN category TEXT DEFAULT '一般'")
        if not _column_exists(cur, "todos", "due_date"):
            cur.execute("ALTER TABLE todos ADD COLUMN due_date DATE")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversations(user_id, id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    TEXT PRIMARY KEY,
                briefing   BOOLEAN DEFAULT TRUE,
                brief_time TIME    DEFAULT '08:00',
                tz         TEXT    DEFAULT 'Asia/Taipei',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_log (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                kind       TEXT NOT NULL,
                ref_date   DATE NOT NULL,
                pushed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, kind, ref_date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS doc_templates (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                category   TEXT DEFAULT '一般',
                body       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tpl_user ON doc_templates(user_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date   DATE NOT NULL,
                places     JSONB DEFAULT '[]'::jsonb,
                gcal_ids   JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id           SERIAL PRIMARY KEY,
                user_id      TEXT NOT NULL,
                name         TEXT NOT NULL,
                steps        JSONB DEFAULT '[]'::jsonb,
                state        TEXT DEFAULT 'pending',
                next_run_at  TIMESTAMP,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_proc_msg_created ON processed_messages(created_at)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_profile (
                user_id    TEXT NOT NULL,
                fact_key   TEXT NOT NULL,
                fact_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, fact_key)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_profile_user ON user_profile(user_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                user_id            TEXT NOT NULL,
                usage_date         DATE NOT NULL,
                model              TEXT NOT NULL,
                input_tokens       BIGINT DEFAULT 0,
                cache_write_tokens BIGINT DEFAULT 0,
                cache_read_tokens  BIGINT DEFAULT 0,
                output_tokens      BIGINT DEFAULT 0,
                cost_usd           NUMERIC(10, 6) DEFAULT 0,
                calls              INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date, model)
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_token_user_date ON token_usage(user_id, usage_date DESC)")
    logger.info("PostgreSQL 初始化完成（含 Stage 0 推播相關表）")
