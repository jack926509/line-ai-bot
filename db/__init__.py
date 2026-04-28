"""db package：依關注點分檔，並 re-export 公開 API 維持 `import db; db.add_todo(...)` 用法。"""
from db.pool import get_db, DATABASE_URL
from db.schema import init_db
from db.conversations import save_message, clear_history, get_history, MAX_HISTORY
from db.todos import add_todo, get_todos, complete_todo, delete_todo, clear_todos
from db.notes import add_note, get_notes, delete_note, clear_notes
from db.subscriptions import (
    upsert_subscription, get_subscription, set_briefing, get_briefing_subscribers,
)
from db.push_log import has_pushed_today, mark_pushed, cleanup_push_log
from db.templates import add_template, list_templates, delete_template
from db.trips import add_trip, list_trips, delete_trip
from db.processed_messages import is_processed, mark_processed, cleanup_processed_messages
from db.token_usage import record_usage, get_usage_summary, cleanup_token_usage

__all__ = [
    "get_db", "DATABASE_URL", "init_db",
    "save_message", "clear_history", "get_history", "MAX_HISTORY",
    "add_todo", "get_todos", "complete_todo", "delete_todo", "clear_todos",
    "add_note", "get_notes", "delete_note", "clear_notes",
    "upsert_subscription", "get_subscription", "set_briefing", "get_briefing_subscribers",
    "has_pushed_today", "mark_pushed", "cleanup_push_log",
    "add_template", "list_templates", "delete_template",
    "add_trip", "list_trips", "delete_trip",
    "is_processed", "mark_processed", "cleanup_processed_messages",
    "record_usage", "get_usage_summary", "cleanup_token_usage",
]
