"""Command Bus and transactional Undo/Redo (spec sections 76, 77).

Every modifying operation is a command able to execute(), undo() and redo().
Undo is transactional: one UNDO reverts the complete operation, including
all derived updates (macro commands).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, List, Optional, TypeVar

from core.errors import DomainError

ContextT = TypeVar("ContextT")


class Command(ABC, Generic[ContextT]):
    """Base command contract (spec section 76)."""

    name: str = "Command"

    @abstractmethod
    def execute(self, context: ContextT) -> Any:
        """Apply the change. Must return enough data for undo()."""

    @abstractmethod
    def undo(self, context: ContextT, result: Any = None) -> None:
        """Revert the change performed by execute()."""

    def redo(self, context: ContextT, result: Any = None) -> Any:
        """Re-apply the change after an undo. Default: execute again."""
        return self.execute(context)


class MacroCommand(Command[ContextT]):
    """Transactional composite command: all children succeed or none applies.

    A single UNDO reverts the whole operation (spec section 77).
    """

    name = "MacroCommand"

    def __init__(self, name: str = "MacroCommand") -> None:
        self.name = name
        self.children: List[Command[ContextT]] = []
        self._executed_results: List[Any] = []

    def add(self, command: Command[ContextT]) -> "MacroCommand":
        self.children.append(command)
        return self

    def execute(self, context: ContextT) -> List[Any]:
        self._executed_results = []
        done: List[Command[ContextT]] = []
        try:
            for child in self.children:
                result = child.execute(context)
                self._executed_results.append(result)
                done.append(child)
        except Exception:
            # Roll back the already executed part (transactional behaviour).
            for child in reversed(done):
                try:
                    child.undo(context)
                except Exception:  # pragma: no cover - rollback best effort
                    pass
            raise
        return self._executed_results

    def undo(self, context: ContextT, result: Any = None) -> None:
        for child, child_result in zip(reversed(self.children), reversed(self._executed_results or [None] * len(self.children))):
            child.undo(context, child_result)

    def redo(self, context: ContextT, result: Any = None) -> List[Any]:
        return self.execute(context)


@dataclass
class _StackEntry(Generic[ContextT]):
    command: Command[ContextT]
    result: Any


class CommandBus:
    """Execution stack with undo/redo history."""

    def __init__(self) -> None:
        self._undo_stack: List[_StackEntry[ContextT]] = []
        self._redo_stack: List[_StackEntry[ContextT]] = []
        self.executed: List[str] = []

    def execute(self, command: Command[ContextT], context: ContextT) -> Any:
        result = command.execute(context)
        self._undo_stack.append(_StackEntry(command, result))
        self._redo_stack.clear()
        self.executed.append(command.name)
        return result

    def undo(self, context: ContextT) -> Optional[str]:
        if not self._undo_stack:
            raise DomainError(
                message="No hay operaciones que deshacer",
                code="ARQ-DOM-020",
                recoverable=True,
                suggested_action="Ejecute un comando antes de intentar UNDO.",
            )
        entry = self._undo_stack.pop()
        entry.command.undo(context, entry.result)
        self._redo_stack.append(entry)
        return entry.command.name

    def redo(self, context: ContextT) -> Optional[str]:
        if not self._redo_stack:
            raise DomainError(
                message="No hay operaciones que rehacer",
                code="ARQ-DOM-021",
                recoverable=True,
                suggested_action="Deshaga un comando antes de intentar REDO.",
            )
        entry = self._redo_stack.pop()
        new_result = entry.command.redo(context, entry.result)
        self._undo_stack.append(_StackEntry(entry.command, new_result))
        return entry.command.name

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.executed.clear()


__all__ = ["Command", "MacroCommand", "CommandBus"]
