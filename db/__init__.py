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
from db.user_profile import (
    remember as profile_remember,
    forget as profile_forget,
    list_facts as profile_list,
    clear_facts as profile_clear,
)
from db.workflows import (
    add_workflow, list_workflows, cancel_workflow,
    fetch_due as workflows_fetch_due,
    mark_done as workflow_mark_done,
    update_next_run as workflow_update_next_run,
    cleanup_workflows,
)
from db.expenses import (
    add_expense, list_expenses, get_expense, delete_expense,
    summarize as expense_summarize,
)

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
    "profile_remember", "profile_forget", "profile_list", "profile_clear",
    "add_workflow", "list_workflows", "cancel_workflow",
    "workflows_fetch_due", "workflow_mark_done", "workflow_update_next_run",
    "cleanup_workflows",
    "add_expense", "list_expenses", "get_expense", "delete_expense",
    "expense_summarize",
]
