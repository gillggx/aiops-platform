"""phase 1: add agent_experience_memory with pgvector

Revision ID: 1a8992c9a339
Revises: cf7faa81d74c
Create Date: 2026-04-06 05:19:00.325295

Adds the reflective experience memory table for Phase 1 of the agentic
memory system. See docs/memory_management.md.

Components:
  - Enable pgvector extension (idempotent)
  - Create agent_experience_memory table with a Vector(1024) embedding column
  - HNSW index for cosine similarity search
  - Btree index on status (retrieval filter)
  - Partial btree index on (user_id, status=ACTIVE) for the hot path

Downgrade drops the table and indexes (but not the extension — other
objects may depend on it).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a8992c9a339'
down_revision: Union[str, None] = 'cf7faa81d74c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Create the table (skip if it already exists — early adopters may have
    #    created it via create_all during Phase 1 development)
    conn = op.get_bind()
    has_table = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='agent_experience_memory'"
    )).scalar()

    if not has_table:
        op.execute("""
            CREATE TABLE agent_experience_memory (
                id                 SERIAL PRIMARY KEY,
                user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                intent_summary     VARCHAR(500) NOT NULL,
                abstract_action    TEXT NOT NULL,
                embedding          VECTOR(1024),
                confidence_score   INTEGER NOT NULL DEFAULT 5,
                use_count          INTEGER NOT NULL DEFAULT 0,
                success_count      INTEGER NOT NULL DEFAULT 0,
                fail_count         INTEGER NOT NULL DEFAULT 0,
                status             VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
                source             VARCHAR(50) NOT NULL DEFAULT 'auto',
                source_session_id  VARCHAR(100),
                last_used_at       TIMESTAMP WITH TIME ZONE,
                created_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        op.execute("CREATE INDEX ix_agent_experience_memory_user_id ON agent_experience_memory (user_id)")

    # 3. Supporting indexes — create IF NOT EXISTS so this migration is safe
    #    to run on DBs that already had them manually created.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_experience_memory_embedding_hnsw
        ON agent_experience_memory
        USING hnsw (embedding vector_cosine_ops)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_experience_memory_status
        ON agent_experience_memory (status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_experience_memory_user_active
        ON agent_experience_memory (user_id, status)
        WHERE status = 'ACTIVE'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_experience_memory_user_active")
    op.execute("DROP INDEX IF EXISTS idx_experience_memory_status")
    op.execute("DROP INDEX IF EXISTS idx_experience_memory_embedding_hnsw")
    op.execute("DROP TABLE IF EXISTS agent_experience_memory")
    # Note: extension 'vector' is NOT dropped — other code may depend on it
