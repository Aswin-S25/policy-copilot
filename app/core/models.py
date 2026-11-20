import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Document(Base):
    __tablename__ = "documents"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    title: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )
    
    document_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    sections = relationship(
        "Section",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    
    chunks = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    
    acl_entries = relationship(
        "DocumentACL",
        back_populates="document",
        cascade="all, delete-orphan"
    )
    
class Section(Base):
    __tablename__ = 'sections'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        default=uuid.uuid4
    )
    
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=True
    )
    
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )
    
    section_path: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    document = relationship(
        "Document",
        back_populates="sections",
    )
    
    parent = relationship(
            "Section",
            remote_side="Section.id",
            back_populates="children",
    )
    
    children = relationship(
                "Section",
                back_populates="parent",
                cascade="all, delete-orphan"
    )
    
class Chunk(Base):
    __tablename__ = "chunks"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    
    content_hash : Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    
    embedding = mapped_column(
        Vector(384),
        nullable=True
    )
    
    embedding_model: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )
    
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    
    document = relationship(
        "Document",
        back_populates="chunks"
    )
    
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunk_index"
        ),
        # Created by migration 62318f15d849; declared here so that
        # autogenerate does not emit a migration that drops it.
        Index(
            "ix_chunks_search_vector",
            "search_vector",
            postgresql_using="gin"
        ),
    )
    

class DocumentACL(Base):
    __tablename__ = 'document_acl'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    role: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    
    permission: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="read"
    )
    
    document = relationship(
        "Document",
        back_populates="acl_entries"
    )
    
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "role",
            name="uq_document_role"
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    
    owner_sub: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.position",
    )
    
    __table_args__ = (
        # "List my conversations, most recent first."
        Index(
            "ix_conversations_owner_sub_updated_at",
            "owner_sub",
            "updated_at",
        ),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False
    )

    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    sender: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )

    # User turns: the rewritten, self-contained question used for retrieval.
    standalone_question: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # Assistant turns: chunks the answer was generated from. IDs only,
    # never content: history is re-authorized against these on every turn.
    source_chunk_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages"
    )

    __table_args__ = (
        # Also serves as the index for "messages of a conversation in order".
        UniqueConstraint(
            "conversation_id",
            "position",
            name="uq_message_conversation_position"
        ),
        CheckConstraint(
            "sender IN ('user', 'assistant')",
            name="ck_messages_sender"
        ),
    )

class User(Base):
    """A person who signs in with a username and password.

    The username becomes the token's "sub" claim, so it is also the owner
    key of the user's conversations. Roles are copied into each token at
    sign-in; a role change takes effect at the user's next sign-in.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Stored normalized (lowercase); see app/core/users.py.
    username: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )

    # Argon2id hash in PHC string format; never the password.
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )

    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)),
        nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
    )
