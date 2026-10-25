"""document chunks with pgvector embeddings

Revision ID: b7c1e4a9d2f0
Revises: 30a0d5793551
Create Date: 2026-10-25 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "b7c1e4a9d2f0"
down_revision: str | None = "30a0d5793551"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed when this migration was written; changing it requires a new migration.
DIMENSIONS = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(DIMENSIONS), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name=op.f("fk_document_chunks_document_id_documents"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_document_chunks_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
    )
    op.create_index("ix_document_chunks_owner_id_embedding_model", "document_chunks", ["owner_id", "embedding_model"])
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index("ix_document_chunks_owner_id_embedding_model", table_name="document_chunks")
    op.drop_table("document_chunks")
    # The extension is left installed: other objects may depend on it.
