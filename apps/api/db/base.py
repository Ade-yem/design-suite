"""
db/base.py
==========
SQLAlchemy declarative base shared by all ORM models.

All database models must import ``Base`` from this module and subclass it.
The ``Base`` uses the standard ``DeclarativeBase`` from SQLAlchemy 2.0+.

Usage
-----
    from db.base import Base

    class MyModel(Base):
        __tablename__ = "my_table"
        ...
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Shared SQLAlchemy declarative base.

    Attributes
    ----------
    None — all columns are defined on individual model subclasses.
    """
    pass
