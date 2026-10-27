"""Persistent undo/redo over the audit trail (spec sections 71, 76, 77).

Because the CLI is process-per-command, undo works through the audit
journal: every mutation stored full entity snapshots (old/new). One undo
reverts the complete operation; redo re-applies it. Deterministic and
traceable: every undo/redo is audited too.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.audit.models import make_audit_event
from core.errors import DomainError
from services.commands_impl import snapshot_to_entity, _repo_for
from services.context import ProjectContext

_UNDOABLE = ("CREATE_ENTITY", "UPDATE_ENTITY", "DELETE_ENTITY")


class PersistentUndoService:
    def __init__(self, context: ProjectContext) -> None:
        self.ctx = context

    def _last_entry(self, command: Optional[str] = None) -> Optional[Dict[str, Any]]:
        entries = self.ctx.audit_repo.recent(limit=500)
        for entry in entries:
            if entry["command"] not in _UNDOABLE:
                continue
            if entry["result"] != "OK":
                continue
            if command and entry["command"] != command:
                continue
            return entry
        return None

    def undo(self) -> Dict[str, Any]:
        entry = self._last_entry()
        if entry is None:
            raise DomainError(
                message="No hay operaciones que deshacer",
                code="ARQ-DOM-080",
                suggested_action="Realice una operación modificadora primero.")
        command = entry["command"]
        object_type = entry["object_type"]
        new_value = entry["new_value"] or {}
        old_value = entry["old_value"]
        object_id = entry["object_id"]
        repo = _repo_for(self.ctx, object_type)

        if command == "CREATE_ENTITY":
            repo.delete(object_type, object_id)
            self.ctx.quantities_repo.delete_for_object(object_id)
        elif command == "UPDATE_ENTITY":
            if old_value:
                repo.save(snapshot_to_entity(old_value))
        elif command == "DELETE_ENTITY":
            if old_value:
                # New shape: {"entity": {...}, "cascade":[...]}; legacy: plain snapshot.
                entity_snapshot = old_value.get("entity", old_value) if isinstance(old_value, dict) and "ENTITY_TYPE" not in old_value else old_value
                repo.save(snapshot_to_entity(entity_snapshot))
                for cascade_snapshot in (old_value.get("cascade", []) if isinstance(old_value, dict) and "ENTITY_TYPE" not in old_value else []):
                    _repo_for(self.ctx, cascade_snapshot.get("ENTITY_TYPE", "")).save(
                        snapshot_to_entity(cascade_snapshot))
                self.ctx.calculations_repo.mark_stale_for_object(object_id)

        self.ctx.audit_repo.append(make_audit_event(
            user=self.ctx.user, object_id=object_id, object_type=object_type,
            command="UNDO", old_value=new_value, new_value=old_value,
            reason=f"undo de {command} #{entry['id'][:8]}", result="OK"))
        self.ctx.calculations_repo.mark_stale_for_object(object_id)
        return {"command": command, "object_id": object_id, "object_type": object_type}

    def redo(self) -> Dict[str, Any]:
        # The last entry must be an UNDO; redo re-applies its new_value.
        entries = self.ctx.audit_repo.recent(limit=500)
        target: Optional[Dict[str, Any]] = None
        for entry in entries:
            if entry["command"] == "UNDO":
                target = entry
                break
            if entry["command"] in _UNDOABLE:
                break  # something newer than the last undo → nothing to redo
        if target is None:
            raise DomainError(
                message="No hay operaciones que rehacer",
                code="ARQ-DOM-081")
        new_value = target["new_value"] or {}
        old_value = target["old_value"] or {}
        object_type = target["object_type"]
        object_id = target["object_id"]

        # The UNDO audit entry stores: old_value = the state the mutation had
        # produced (create→snapshot, update→new snapshot), new_value = the state
        # before the mutation (None for create, old snapshot for update/delete).
        if not old_value and new_value:
            # UNDO of a deletion → redo deletes again
            repo = _repo_for(self.ctx, object_type)
            repo.delete(object_type, object_id)
            self.ctx.quantities_repo.delete_for_object(object_id)
        elif old_value and not new_value:
            # UNDO of a creation → redo recreates the entity
            entity_snapshot = old_value.get("entity", old_value) if isinstance(old_value, dict) and "ENTITY_TYPE" not in old_value else old_value
            _repo_for(self.ctx, entity_snapshot.get("ENTITY_TYPE", object_type)).save(
                snapshot_to_entity(entity_snapshot))
            for cascade_snapshot in (old_value.get("cascade", []) if isinstance(old_value, dict) and "ENTITY_TYPE" not in old_value else []):
                _repo_for(self.ctx, cascade_snapshot.get("ENTITY_TYPE", "")).save(
                    snapshot_to_entity(cascade_snapshot))
        else:
            # UNDO of an update → redo re-applies the new state (stored in old_value)
            _repo_for(self.ctx, object_type).save(snapshot_to_entity(old_value))

        self.ctx.audit_repo.append(make_audit_event(
            user=self.ctx.user, object_id=object_id, object_type=object_type,
            command="REDO", old_value=old_value, new_value=new_value,
            reason=f"redo #{target['id'][:8]}", result="OK"))
        self.ctx.calculations_repo.mark_stale_for_object(object_id)
        return {"command": "REDO", "object_id": object_id, "object_type": object_type}


__all__ = ["PersistentUndoService"]
