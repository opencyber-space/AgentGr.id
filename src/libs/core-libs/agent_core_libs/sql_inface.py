# sql_helper.py
from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple, Union
from sqlalchemy.pool import StaticPool, NullPool
from urllib.parse import urlparse

from sqlalchemy import create_engine, text, Engine
from sqlalchemy.engine import Connection, CursorResult, Row, RowMapping
from sqlalchemy.exc import SQLAlchemyError

try:
    import pandas as pd  # optional, used in fetch_df
    _HAS_PANDAS = True
except Exception:
    _HAS_PANDAS = False

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

Params = None


@dataclass(frozen=True)
class SQLHelperConfig:
    url: str  # e.g. "sqlite:///data.db", "postgresql+psycopg://user:pass@host/db"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_pre_ping: bool = True
    future: bool = True  # SQLAlchemy 2.0 style


class SQLHelper:
    def __init__(self, config: SQLHelperConfig | str):
        if isinstance(config, str):
            config = SQLHelperConfig(url=config)
        self.config = config

        url = config.url
        is_sqlite = url.startswith("sqlite")
        is_memory = url.endswith(":memory:") or url.endswith(":///:memory:")

        engine_kwargs = dict(
            echo=config.echo,
            pool_pre_ping=config.pool_pre_ping,
            future=config.future,
        )

        if is_sqlite:
            # SQLite: don't pass pool_size / max_overflow
            if is_memory:
                # in-memory needs a static pool and same-thread disabled
                engine_kwargs.update(
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                )
            else:
                # file-based sqlite — use NullPool (or keep default SingletonThreadPool)
                engine_kwargs.update(
                    poolclass=NullPool,
                    connect_args={"check_same_thread": False},
                )
        else:
            # Non-sqlite DBs: normal pooling is fine
            engine_kwargs.update(
                pool_size=config.pool_size,
                max_overflow=config.max_overflow,
            )

        self.engine: Engine = create_engine(url, **engine_kwargs)
        self._dialect = self.engine.dialect.name.lower()
        log.info("SQLHelper connected (dialect=%s)", self._dialect)

    # ---------------------------- connections/tx ----------------------------

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        conn = self.engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.connect() as conn:
            trans = conn.begin()
            try:
                yield conn
                trans.commit()
            except Exception:
                trans.rollback()
                raise

    # ---------------------------- basic queries ----------------------------

    def execute(self, sql: str, params: Params = None) -> CursorResult:
        
        try:
            with self.transaction() as conn:
                if isinstance(params, Sequence) and params and isinstance(params[0], Mapping):
                    return conn.execute(text(sql), params)  # executemany
                return conn.execute(text(sql), params or {})
        except SQLAlchemyError as e:
            log.exception("Execute failed")
            raise

    def fetch_all(self, sql: str, params: Mapping[str, Any] | None = None) -> List[RowMapping]:
        """Return list of row-mappings (dict-like)."""
        with self.connect() as conn:
            res = conn.execute(text(sql), params or {})
            return [dict(r._mapping) for r in res.fetchall()]

    def fetch_one(self, sql: str, params: Mapping[str, Any] | None = None) -> Optional[RowMapping]:
        with self.connect() as conn:
            res = conn.execute(text(sql), params or {})
            row = res.fetchone()
            return dict(row._mapping) if row else None

    def fetch_val(self, sql: str, params: Mapping[str, Any] | None = None, default: Any = None) -> Any:
        with self.connect() as conn:
            res = conn.execute(text(sql), params or {})
            row = res.fetchone()
            return (row[0] if row is not None else default)

    def fetch_df(self, sql: str, params: Mapping[str, Any] | None = None):
        """Return a pandas DataFrame (requires pandas)."""
        if not _HAS_PANDAS:
            raise RuntimeError("pandas is not installed")
        with self.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})

    # ---------------------------- bulk helpers ----------------------------

    def bulk_execute(self, sql: str, param_seq: Sequence[Mapping[str, Any]]) -> CursorResult:
        """Efficient executemany for a parameterized statement."""
        if not param_seq:
            raise ValueError("param_seq cannot be empty")
        return self.execute(sql, param_seq)

    # ---------------------------- upsert helper ----------------------------

    def upsert(
        self,
        table: str,
        row: Mapping[str, Any],
        conflict_keys: Sequence[str],
        update_columns: Optional[Sequence[str]] = None,
    ) -> CursorResult:
        """
        Portable-ish UPSERT:
          - SQLite: INSERT ... ON CONFLICT(keys) DO UPDATE SET ...
          - Postgres: INSERT ... ON CONFLICT(keys) DO UPDATE SET ...
          - MySQL/MariaDB: INSERT ... ON DUPLICATE KEY UPDATE ...
        """
        cols = list(row.keys())
        params = {f"v_{c}": row[c] for c in cols}

        if update_columns is None:
            # default: update all non-conflict columns
            update_columns = [c for c in cols if c not in conflict_keys]

        col_list = ", ".join(cols)
        val_list = ", ".join(f":v_{c}" for c in cols)

        if self._dialect in ("sqlite", "postgresql"):
            conflict = ", ".join(conflict_keys)
            set_clause = ", ".join(f"{c}=excluded.{c}" for c in update_columns) or "NOTHING"
            sql = (
                f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) "
                f"ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
                if set_clause != "NOTHING"
                else f"INSERT INTO {table} ({col_list}) VALUES ({val_list}) ON CONFLICT ({conflict}) DO NOTHING"
            )
        elif self._dialect in ("mysql", "mariadb"):
            set_clause = ", ".join(f"{c}=VALUES({c})" for c in update_columns) if update_columns else ""
            sql = f"INSERT INTO {table} ({col_list}) VALUES ({val_list})"
            if set_clause:
                sql += f" ON DUPLICATE KEY UPDATE {set_clause}"
        else:
            # Fallback: try a MERGE-like pattern (not all DBs support this identically)
            key_pred = " AND ".join(f"t.{k}=s.{k}" for k in conflict_keys)
            set_clause = ", ".join(f"{c}=s.{c}" for c in update_columns) if update_columns else ""
            src_select = "SELECT " + ", ".join(f":v_{c} AS {c}" for c in cols)
            sql = (
                f"MERGE INTO {table} AS t USING ({src_select}) AS s ON ({key_pred}) "
                f"WHEN MATCHED THEN UPDATE SET {set_clause} "
                f"WHEN NOT MATCHED THEN INSERT ({col_list}) VALUES ({', '.join('s.'+c for c in cols)})"
            )

        return self.execute(sql, params)


    def run_script(self, path: Union[str, Path]) -> None:
        """Execute a .sql file (semicolon-separated statements)."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        sql_text = p.read_text(encoding="utf-8")
        # naive splitter—works for most migration files (no ';' in strings)
        statements = [s.strip() for s in sql_text.split(";") if s.strip()]
        with self.transaction() as conn:
            for stmt in statements:
                conn.execute(text(stmt))

    def table_exists(self, name: str) -> bool:
        insp = self.engine.inspect(self.engine)
        return insp.has_table(name)

    def close(self) -> None:
        self.engine.dispose()
