"""Safe formula/expression evaluator (spec section 58).

A controlled formula language. NO eval(), NO exec(): the expression is
parsed with ``ast`` and only whitelisted nodes are evaluated.

Supported grammar:
    numbers, variables, + - * / % ** ( ),
    unary +/-, comparisons < <= > >= == != ,
    functions: min, max, abs, round, sqrt, pow, floor, ceil
    constants: pi, e
    boolean: and, or, not

Any other construct (attribute access, subscripts, calls to unknown
functions, lambdas, comprehensions...) is rejected with RuleError.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Dict, Mapping

from core.errors import RuleError

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

_ALLOWED_CMPOPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_ALLOWED_FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "pow": pow,
    "floor": math.floor,
    "ceil": math.ceil,
}

_ALLOWED_CONSTS: Dict[str, float] = {"pi": math.pi, "e": math.e}


class Expression:
    """A compiled, validated, reusable expression."""

    def __init__(self, expression: str) -> None:
        self.source = (expression or "").strip()
        if not self.source:
            raise RuleError(
                message="La expresión está vacía",
                code="ARQ-RUL-002",
                context={"expression": expression},
            )
        try:
            tree = ast.parse(self.source, mode="eval")
        except SyntaxError as exc:
            raise RuleError(
                message=f"Sintaxis de expresión inválida: {exc.msg}",
                code="ARQ-RUL-003",
                context={"expression": self.source, "position": exc.offset},
                suggested_action="Revise la sintaxis del lenguaje de fórmulas controlado.",
            ) from exc
        self._tree = tree
        self.variables: set[str] = set()
        self._collect_variables(tree, self.variables)
        self.validate_structure(tree)

    # -- inspection ----------------------------------------------------
    def validate_structure(self, node: ast.AST) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, (ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare)):
                continue
            if isinstance(sub, ast.Call):
                if not isinstance(sub.func, ast.Name) or sub.func.id not in _ALLOWED_FUNCS:
                    name = getattr(getattr(sub, "func", None), "id", "<desconocido>")
                    raise RuleError(
                        message=f"Llamada no permitida en expresión: {name}",
                        code="ARQ-RUL-004",
                        context={"expression": self.source, "function": name},
                        suggested_action="Use solo: " + ", ".join(sorted(_ALLOWED_FUNCS)),
                    )
                continue
            if isinstance(sub, ast.Name):
                continue
            if isinstance(sub, ast.Constant):
                if not isinstance(sub.value, (int, float, bool)):
                    raise RuleError(
                        message=f"Constante no permitida: {sub.value!r}",
                        code="ARQ-RUL-005",
                        context={"expression": self.source},
                    )
                continue
            if isinstance(sub, (ast.Load, ast.operator, ast.unaryop, ast.cmpop, ast.boolop)):
                continue
            if isinstance(sub, ast.Expression):
                continue
            raise RuleError(
                message=f"Construcción no permitida en expresión: {type(sub).__name__}",
                code="ARQ-RUL-006",
                context={"expression": self.source, "node": type(sub).__name__},
                suggested_action="El lenguaje de fórmulas solo admite aritmética, comparaciones y funciones básicas.",
            )

    def _collect_variables(self, node: ast.AST, out: set[str]) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id not in _ALLOWED_CONSTS:
                if not isinstance(sub.ctx, ast.Load):
                    raise RuleError(
                        message=f"Variable de solo lectura violada: {sub.id}",
                        code="ARQ-RUL-007",
                    )
                if sub.id in _ALLOWED_FUNCS:
                    continue
                out.add(sub.id)

    # -- evaluation ----------------------------------------------------
    def evaluate(self, variables: Mapping[str, Any]) -> Any:
        env: Dict[str, Any] = dict(_ALLOWED_CONSTS)
        env.update(dict(variables))
        missing = self.variables - set(env.keys())
        if missing:
            raise RuleError(
                message=f"Faltan variables para evaluar la expresión: {', '.join(sorted(missing))}",
                code="ARQ-RUL-008",
                context={"expression": self.source, "missing": sorted(missing)},
            )
        return self._eval(self._tree.body, env)

    def _eval(self, node: ast.AST, env: Dict[str, Any]) -> Any:
        if isinstance(node, ast.Expression):
            return self._eval(node.body, env)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in _ALLOWED_CONSTS:
                return _ALLOWED_CONSTS[node.id]
            return env[node.id]
        if isinstance(node, ast.BinOp):
            op = _ALLOWED_BINOPS.get(type(node.op))
            if op is None:
                raise RuleError(message=f"Operador no permitido: {type(node.op).__name__}",
                                code="ARQ-RUL-009")
            left = self._eval(node.left, env)
            right = self._eval(node.right, env)
            if isinstance(node.op, ast.Div) and right == 0:
                raise RuleError(message="División por cero en expresión",
                                code="ARQ-RUL-010", context={"expression": self.source})
            if isinstance(node.op, ast.Mod) and right == 0:
                raise RuleError(message="Módulo por cero en expresión",
                                code="ARQ-RUL-010", context={"expression": self.source})
            return op(left, right)
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, env)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value
            if isinstance(node.op, ast.Not):
                return not value
            raise RuleError(message=f"Operador unario no permitido: {type(node.op).__name__}",
                            code="ARQ-RUL-009")
        if isinstance(node, ast.BoolOp):
            values = [self._eval(v, env) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            return any(values)
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env)
            for cmp_op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, env)
                op = _ALLOWED_CMPOPS.get(type(cmp_op))
                if op is None:
                    raise RuleError(message=f"Comparador no permitido: {type(cmp_op).__name__}",
                                    code="ARQ-RUL-009")
                if not op(left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            func_name = node.func.id  # validated in validate_structure
            func = _ALLOWED_FUNCS[func_name]
            args = [self._eval(a, env) for a in node.args]
            if func_name == "sqrt" and args and args[0] < 0:
                raise RuleError(message="sqrt de número negativo", code="ARQ-RUL-011")
            return func(*args)
        raise RuleError(
            message=f"Nodo no evaluable: {type(node).__name__}",
            code="ARQ-RUL-012",
        )


def safe_evaluate(expression: str, variables: Mapping[str, Any]) -> Any:
    """Convenience one-shot evaluation."""
    return Expression(expression).evaluate(variables)


__all__ = ["Expression", "safe_evaluate"]
