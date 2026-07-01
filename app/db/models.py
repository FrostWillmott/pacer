from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Track(StrEnum):
    algo = "algo"
    sql = "sql"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class Status(StrEnum):
    introduced = "introduced"
    learning = "learning"
    maintenance = "maintenance"


class Problem(Base):
    __tablename__ = "problems"

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    difficulty: Mapped[Difficulty] = mapped_column(Enum(Difficulty), nullable=False)
    track: Mapped[Track] = mapped_column(Enum(Track), nullable=False)
    pattern: Mapped[str] = mapped_column(String, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    submissions: Mapped[list[Submission]] = relationship(back_populates="problem")
    progress: Mapped[Progress | None] = relationship(back_populates="problem")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_slug: Mapped[str] = mapped_column(
        String, ForeignKey("problems.slug"), nullable=False
    )
    solved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    problem: Mapped[Problem] = relationship(back_populates="submissions")

    __table_args__ = (
        UniqueConstraint("problem_slug", "solved_at", name="uq_submission_slug_time"),
    )


class Progress(Base):
    __tablename__ = "progress"

    problem_slug: Mapped[str] = mapped_column(
        String, ForeignKey("problems.slug"), primary_key=True
    )
    status: Mapped[Status] = mapped_column(Enum(Status), nullable=False)
    introduced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    interval_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    problem: Mapped[Problem] = relationship(back_populates="progress")
