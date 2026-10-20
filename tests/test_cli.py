"""The command line, with the database call faked."""
from datetime import date

import pytest

from agent_memory import cli, db
from agent_memory.config import Config


def test_query_sends_the_local_date(monkeypatch):
    """fn::overdue's default "today" is the caller's local date, not SurrealDB's UTC one."""
    seen = {}

    def fake_sql(cfg, q, root=False, db=None, vars=None):
        seen["vars"] = vars
        return [{"status": "OK", "result": []}]

    monkeypatch.setattr(db, "sql", fake_sql)
    with pytest.raises(SystemExit):
        cli._query(Config(), ["RETURN fn::overdue()"])
    assert seen["vars"] == {"local_today": date.today().isoformat()}
