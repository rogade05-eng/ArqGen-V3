"""Repositories for rules, formulas, calculations, events, audit, versions, settings."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from core.audit.models import AuditEvent
from core.calculations.contracts import CalculationMode, CalculationResult, CalculationStatus
from core.entities.base import CalculationStatus, parse_datetime, utc_now
from core.events.bus import Event
from core.rules.models import Rule, RuleSeverity, Ruleset
from persistence.sqlite.connection import Session, json_dumps, json_loads


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str, default: str = "") -> str:
        row = self.session.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.session.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def all(self) -> Dict[str, str]:
        return {r["key"]: r["value"] for r in self.session.query_all("SELECT key, value FROM settings")}


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: Event) -> None:
        self.session.execute(
            "INSERT INTO events (id, type, payload_json, source, timestamp) VALUES (?, ?, ?, ?, ?)",
            (str(__import__("uuid").uuid4()), event.type, json_dumps(event.payload),
             event.source, event.timestamp.isoformat()),
        )

    def recent(self, limit: int = 100, event_type: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT type, payload_json, source, timestamp FROM events"
        params: tuple = ()
        if event_type:
            sql += " WHERE type = ?"
            params = (event_type,)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        rows = self.session.query_all(sql, params + (limit,))
        return [
            {"type": r["type"], "payload": json_loads(r["payload_json"], {}),
             "source": r["source"], "timestamp": r["timestamp"]}
            for r in rows
        ]


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, event: AuditEvent) -> None:
        self.session.execute(
            "INSERT INTO audit_log (id, user, timestamp, object_id, object_type, command, "
            "old_value_json, new_value_json, reason, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.id, event.user, event.timestamp.isoformat(), event.object_id,
                event.object_type, event.command, json_dumps(event.old_value) if event.old_value is not None else None,
                json_dumps(event.new_value) if event.new_value is not None else None,
                event.reason, event.result,
            ),
        )

    def recent(self, limit: int = 100, object_id: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM audit_log"
        params: tuple = ()
        if object_id:
            sql += " WHERE object_id = ?"
            params = (object_id,)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        rows = self.session.query_all(sql, params + (limit,))
        return [self._row_to_dict(r) for r in rows]

    # -- FASE 36: filtered queries, stats and full export -----------------
    def query(self, limit: int = 100, object_id: str = "", user: str = "",
              command: str = "", object_type: str = "", since: str = "",
              until: str = "", result: str = "") -> List[Dict[str, Any]]:
        """Filtered audit query (spec 71 fields as optional filters)."""
        clauses: List[str] = []
        params: List[Any] = []
        if object_id:
            clauses.append("object_id = ?")
            params.append(object_id)
        if user:
            clauses.append("user = ?")
            params.append(user)
        if command:
            clauses.append("command LIKE ?")
            params.append(f"%{command}%")
        if object_type:
            clauses.append("object_type = ?")
            params.append(object_type)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until:
            clauses.append("timestamp <= ?")
            params.append(until)
        if result:
            clauses.append("result = ?")
            params.append(result)
        sql = "SELECT * FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.session.query_all(sql, tuple(params))
        return [self._row_to_dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        """Aggregate audit statistics (counts by command/object/user/result)."""
        def group(column: str) -> Dict[str, int]:
            rows = self.session.query_all(
                f"SELECT {column} AS key, COUNT(*) AS n FROM audit_log "
                f"GROUP BY {column} ORDER BY n DESC, key", ())
            return {str(r["key"] or "(sin dato)"): int(r["n"]) for r in rows}

        total_row = self.session.query_one("SELECT COUNT(*) AS n FROM audit_log", ())
        return {
            "total": int(total_row["n"]) if total_row else 0,
            "by_command": group("command"),
            "by_object_type": group("object_type"),
            "by_user": group("user"),
            "by_result": group("result"),
        }

    def iter_all(self, batch: int = 500) -> List[Dict[str, Any]]:
        """All audit events ordered ascending (export in batches)."""
        offset = 0
        events: List[Dict[str, Any]] = []
        while True:
            rows = self.session.query_all(
                "SELECT * FROM audit_log ORDER BY timestamp ASC LIMIT ? OFFSET ?",
                (batch, offset))
            if not rows:
                break
            events.extend(self._row_to_dict(r) for r in rows)
            offset += batch
        return events

    def _row_to_dict(self, r) -> Dict[str, Any]:
        return {
            "id": r["id"], "user": r["user"], "timestamp": r["timestamp"],
            "object_id": r["object_id"], "object_type": r["object_type"],
            "command": r["command"],
            "old_value": json_loads(r["old_value_json"]),
            "new_value": json_loads(r["new_value_json"]),
            "reason": r["reason"], "result": r["result"],
        }


class RuleRepository:
    """Persists rulesets + rules (rules as data, never in code — spec 12)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_ruleset(self, ruleset: Ruleset) -> Ruleset:
        self.session.execute(
            "INSERT INTO rulesets (code, jurisdiction, discipline, version, effective_date, source) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET jurisdiction=excluded.jurisdiction, "
            "discipline=excluded.discipline, version=excluded.version, "
            "effective_date=excluded.effective_date, source=excluded.source",
            (ruleset.code, ruleset.jurisdiction, ruleset.discipline, ruleset.version,
             ruleset.effective_date, ruleset.source),
        )
        for rule in ruleset.rules:
            self.save_rule(rule, ruleset.code)
        return ruleset

    def save_rule(self, rule: Rule, ruleset_code: str = "") -> None:
        self.session.execute(
            "INSERT INTO rules (code, ruleset_code, discipline, category, severity, expression, "
            "message, parameters_json, source, version, applies_to) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(code, ruleset_code) DO UPDATE SET discipline=excluded.discipline, "
            "category=excluded.category, severity=excluded.severity, expression=excluded.expression, "
            "message=excluded.message, parameters_json=excluded.parameters_json, "
            "source=excluded.source, version=excluded.version, applies_to=excluded.applies_to",
            (rule.code, ruleset_code, rule.discipline, rule.category, rule.severity.value,
             rule.expression, rule.message, json_dumps(rule.parameters), rule.source,
             rule.version, rule.applies_to),
        )

    def load_ruleset(self, code: str) -> Optional[Ruleset]:
        row = self.session.query_one("SELECT * FROM rulesets WHERE code = ?", (code,))
        if not row:
            return None
        rules = self.session.query_all("SELECT * FROM rules WHERE ruleset_code = ? ORDER BY code", (code,))
        return Ruleset(
            code=row["code"], jurisdiction=row["jurisdiction"], discipline=row["discipline"],
            version=row["version"], effective_date=row["effective_date"], source=row["source"],
            rules=[self._rule_from_row(r) for r in rules],
        )

    def list_rulesets(self) -> List[str]:
        rows = self.session.query_all("SELECT code FROM rulesets ORDER BY code")
        return [r["code"] for r in rows]

    @staticmethod
    def _rule_from_row(row: sqlite3.Row) -> Rule:
        return Rule(
            code=row["code"], discipline=row["discipline"], category=row["category"],
            severity=RuleSeverity(row["severity"]), expression=row["expression"],
            message=row["message"], parameters=json_loads(row["parameters_json"], {}) or {},
            source=row["source"], version=row["version"], applies_to=row["applies_to"],
        )


class FormulaRepository:
    """Formula catalogue as data (spec 58): code, target type, expression, unit, waste."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, code: str, target_type: str, expression: str, unit: str,
             description: str = "", waste_factor: float = 0.0,
             variables: Optional[List[str]] = None, version: str = "1.0", source: str = "",
             condition: str = "") -> None:
        self.session.execute(
            "INSERT INTO formulas (code, target_type, description, expression, unit, waste_factor, "
            "variables_json, version, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET target_type=excluded.target_type, "
            "description=excluded.description, expression=excluded.expression, unit=excluded.unit, "
            "waste_factor=excluded.waste_factor, variables_json=excluded.variables_json, "
            "version=excluded.version, source=excluded.source",
            (code, target_type, description, expression, unit, waste_factor,
             json_dumps(variables or []), version, source),
        )
        try:
            self.session.execute(
                "UPDATE formulas SET condition_sql = ? WHERE code = ?",
                (condition, code),
            )
        except Exception:  # pragma: no cover - pre-m005 schema without condition_sql
            pass

    def for_type(self, target_type: str) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT * FROM formulas WHERE target_type = ? ORDER BY code", (target_type,))
        return [
            {
                "code": r["code"], "target_type": r["target_type"],
                "description": r["description"], "expression": r["expression"],
                "unit": r["unit"], "waste_factor": r["waste_factor"],
                "variables": json_loads(r["variables_json"], []) or [],
                "version": r["version"], "source": r["source"],
                "condition": r["condition_sql"] if "condition_sql" in r.keys() else "",
            }
            for r in rows
        ]

    def get(self, code: str) -> Optional[Dict[str, Any]]:
        rows = self.session.query_all("SELECT * FROM formulas WHERE code = ?", (code,))
        return rows[0] and {
            "code": rows[0]["code"], "target_type": rows[0]["target_type"],
            "description": rows[0]["description"], "expression": rows[0]["expression"],
            "unit": rows[0]["unit"], "waste_factor": rows[0]["waste_factor"],
            "variables": json_loads(rows[0]["variables_json"], []) or [],
            "version": rows[0]["version"], "source": rows[0]["source"],
        } or None


class CalculationRepository:
    """Stores CalculationResults and supports incremental invalidation (spec 74, 102)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, result: CalculationResult, project_id: str, stale: bool = False) -> None:
        data = result.to_dict()
        self.session.execute(
            "INSERT INTO calculations (id, calculation_type, input_hash, input_objects_json, "
            "parameters_json, values_json, units_json, warnings_json, errors_json, formula_version, "
            "ruleset_version, engine_version, mode, status, duration_ms, objects_processed, timestamp, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET input_hash=excluded.input_hash, "
            "values_json=excluded.values_json, warnings_json=excluded.warnings_json, "
            "errors_json=excluded.errors_json, status=excluded.status, "
            "duration_ms=excluded.duration_ms, objects_processed=excluded.objects_processed, "
            "timestamp=excluded.timestamp, stale=excluded.stale",
            (
                data["id"], data["calculation_type"], data["input_hash"],
                json_dumps(data["input_objects"]), json_dumps(data["parameters"]),
                json_dumps(data["values"]), json_dumps(data["units"]),
                json_dumps(data["warnings"]), json_dumps(data["errors"]),
                data["formula_version"], data["ruleset_version"], data["engine_version"],
                data["mode"], data["status"], data["duration_ms"],
                data["objects_processed"], data["timestamp"], 1 if stale else 0,
            ),
        )

    def find_fresh(self, calculation_type: str, input_hash: str) -> Optional[CalculationResult]:
        row = self.session.query_one(
            "SELECT * FROM calculations WHERE calculation_type = ? AND input_hash = ? AND stale = 0 "
            "ORDER BY timestamp DESC LIMIT 1",
            (calculation_type, input_hash),
        )
        return self._from_row(row) if row else None

    def mark_stale_for_object(self, object_id: str) -> int:
        """Mark stale every calculation whose input includes object_id."""
        rows = self.session.query_all(
            "SELECT id, input_objects_json FROM calculations WHERE stale = 0")
        count = 0
        for row in rows:
            objects = json_loads(row["input_objects_json"], []) or []
            if any(obj.get("id") == object_id for obj in objects):
                self.session.execute("UPDATE calculations SET stale = 1 WHERE id = ?", (row["id"],))
                count += 1
        return count

    def mark_all_stale(self, calculation_type: str = "") -> int:
        if calculation_type:
            cursor = self.session.execute(
                "UPDATE calculations SET stale = 1 WHERE calculation_type = ?", (calculation_type,))
        else:
            cursor = self.session.execute("UPDATE calculations SET stale = 1")
        return cursor.rowcount

    def count_fresh(self, calculation_type: str) -> int:
        row = self.session.query_one(
            "SELECT COUNT(*) AS n FROM calculations WHERE calculation_type = ? AND stale = 0",
            (calculation_type,))
        return int(row["n"]) if row else 0

    def recent(self, limit: int = 50, status: str = "") -> List[Dict[str, Any]]:
        """Latest calculation rows for the UI status panel (spec 90, 93)."""
        sql = ("SELECT calculation_type, status, mode, objects_processed, "
               "duration_ms, timestamp, stale FROM calculations")
        params: tuple = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        rows = self.session.query_all(sql, params + (limit,))
        return [dict(r) for r in rows]

    def delete_for_object(self, object_id: str) -> int:
        """Deletes calculation rows that used an object (cascade on delete)."""
        rows = self.session.query_all(
            "SELECT id FROM calculations WHERE input_objects_json LIKE ?",
            (f"%{object_id}%",))
        deleted = 0
        for row in rows:
            cursor = self.session.execute("DELETE FROM calculations WHERE id = ?", (row["id"],))
            deleted += cursor.rowcount
        return deleted

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CalculationResult:
        return CalculationResult(
            id=row["id"], calculation_type=row["calculation_type"],
            input_objects=json_loads(row["input_objects_json"], []) or [],
            parameters=json_loads(row["parameters_json"], {}) or {},
            values=json_loads(row["values_json"], {}) or {},
            units=json_loads(row["units_json"], {}) or {},
            warnings=json_loads(row["warnings_json"], []) or [],
            errors=json_loads(row["errors_json"], []) or [],
            formula_version=row["formula_version"], ruleset_version=row["ruleset_version"],
            engine_version=row["engine_version"], mode=CalculationMode(row["mode"]),
            status=CalculationStatus(row["status"]) if row["status"] in CalculationStatus._value2member_map_ else CalculationStatus.COMPLETED,
            duration_ms=row["duration_ms"], objects_processed=row["objects_processed"],
            input_hash=row["input_hash"], timestamp=parse_datetime(row["timestamp"]) or utc_now(),
        )


class VersionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def next_number(self) -> int:
        row = self.session.query_one("SELECT COALESCE(MAX(number), 0) + 1 AS n FROM project_versions")
        return int(row["n"]) if row else 1

    def save(self, number: int, author: str, description: str, snapshot_json: str) -> str:
        version_id = str(__import__("uuid").uuid4())
        self.session.execute(
            "INSERT INTO project_versions (id, number, author, description, created_at, snapshot_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (version_id, number, author, description, utc_now().isoformat(), snapshot_json),
        )
        return version_id

    def list(self) -> List[Dict[str, Any]]:
        rows = self.session.query_all(
            "SELECT id, number, author, description, created_at, LENGTH(snapshot_json) AS size "
            "FROM project_versions ORDER BY number")
        return [dict(r) for r in rows]

    def get_snapshot(self, number: int) -> Optional[str]:
        row = self.session.query_one(
            "SELECT snapshot_json FROM project_versions WHERE number = ?", (number,))
        return row["snapshot_json"] if row else None


__all__ = [
    "SettingsRepository", "EventRepository", "AuditRepository",
    "RuleRepository", "FormulaRepository", "CalculationRepository", "VersionRepository",
]
