from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base


class Target(Base):
    __tablename__ = "targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RegionProfile(Base):
    __tablename__ = "region_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    storage_path: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_profile_id: Mapped[int] = mapped_column(ForeignKey("region_profiles.id"))
    status: Mapped[str] = mapped_column(String, default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)

    region: Mapped["RegionProfile"] = relationship()


class PricePoint(Base):
    __tablename__ = "price_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))

    price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # в копейках
    old_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # цена с Ozon картой
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    raw_json: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")

    target: Mapped["Target"] = relationship()
