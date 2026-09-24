import aiosqlite
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/app.db")

async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pending_choices (
                task_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        await db.commit()

async def save_pending_choice(task_id: str, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT OR REPLACE INTO pending_choices (task_id, data) VALUES (?, ?)',
            (task_id, json.dumps(data))
        )
        await db.commit()

async def get_pending_choice(task_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT data FROM pending_choices WHERE task_id = ?', (task_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
    return None

async def delete_pending_choice(task_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM pending_choices WHERE task_id = ?', (task_id,))
        await db.commit()

async def get_all_pending_choices() -> dict:
    choices = {}
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT task_id, data FROM pending_choices') as cursor:
            async for row in cursor:
                choices[row[0]] = json.loads(row[1])
    return choices
