import os
import atexit
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

DB_URI = os.environ["DATABASE_URL"]

# Use a connection pool instead of a single shared connection to avoid
# contention under concurrent requests and Neon cold-start delays.
pool = ConnectionPool(
    DB_URI,
    min_size=0,
    max_size=10,
    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    check=ConnectionPool.check_connection,
    max_idle=60,
    max_lifetime=300,
    reconnect_timeout=30,
)

checkpointer = PostgresSaver(pool)

checkpointer.setup()

atexit.register(pool.close)

def retrieve_all_threads():
    """Return all existing thread IDs from memory."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT thread_id FROM checkpoints")
                return [row["thread_id"] for row in cur.fetchall()]
    except Exception:
        all_threads = set()
        for checkpoint in checkpointer.list(None):
            thread_id = checkpoint.config["configurable"]["thread_id"]
            all_threads.add(thread_id)
        return list(all_threads)


def retrieve_threads_with_preview():
    """Return thread IDs with a preview name from the first user message."""
    thread_ids = retrieve_all_threads()
    threads = []
    for tid in thread_ids:
        preview = _get_thread_preview(tid)
        threads.append({"id": tid, "name": preview})
    return threads


def _get_thread_preview(thread_id: str, max_length: int = 40) -> str:
    """Extract the first human message from a thread to use as its name."""
    try:
        from core.graph import CFOBuddy
        config = {"configurable": {"thread_id": thread_id}}
        state = CFOBuddy.get_state(config)
        messages = state.values.get("messages", [])
        for msg in messages:
            if msg.type == "human":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                content = content.strip()
                if len(content) > max_length:
                    return content[:max_length].rsplit(" ", 1)[0] + "..."
                return content
    except Exception:
        pass
    # Fallback: short ID
    return f"Chat {thread_id[:8]}"


def delete_thread(thread_id: str) -> bool:
    """Delete all checkpoint data for a given thread."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                    (thread_id,),
                )
                cur.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                    (thread_id,),
                )
                cur.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s",
                    (thread_id,),
                )
        return True
    except Exception:
        return False
