import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


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
    