"""Units, safe evaluator, events, commands undo/redo (spec 11, 58, 75-77)."""

from __future__ import annotations

import unittest

from core.commands.bus import Command, CommandBus, MacroCommand
from core.errors import UnitError
from core.events.bus import Event, EventBus, EventType
from core.rules.evaluator import Expression
from core.rules.models import Rule, RuleSeverity
from core.units.quantity import Quantity


class TestUnits(unittest.TestCase):
    def test_conversion_same_dimension(self):
        self.assertAlmostEqual(Quantity(5, "m").to("cm").value, 500.0, places=9)
        self.assertAlmostEqual(Quantity(1, "t").to("kg").value, 1000.0, places=9)
        self.assertAlmostEqual(Quantity(3600, "L/s").to("m3/h").value, 12960.0, places=6)

    def test_cross_dimension_forbidden(self):
        with self.assertRaises(UnitError):
            Quantity(1, "m").to("kg")
        with self.assertRaises(UnitError):
            Quantity(1, "m2").to("m")
        with self.assertRaises(UnitError):
            Quantity(1, "V").to("A")

    def test_unknown_unit(self):
        with self.assertRaises(UnitError):
            Quantity(1, "parsec")

    def test_arithmetic(self):
        a = Quantity(3, "m")
        b = Quantity(2, "m")
        self.assertEqual((a + b).value, 5.0)
        self.assertEqual((a - b).value, 1.0)
        self.assertEqual((a * 2).value, 6.0)
        self.assertEqual((a / 2).value, 1.5)
        with self.assertRaises(UnitError):
            _ = a + Quantity(2, "kg")


class TestEvaluator(unittest.TestCase):
    def test_arithmetic_and_functions(self):
        self.assertEqual(Expression("1 + 2 * 3").evaluate({}), 7)
        self.assertEqual(Expression("max(a, b) + sqrt(c)").evaluate({"a": 1, "b": 2, "c": 16}), 6)
        self.assertAlmostEqual(Expression("pi * r * r").evaluate({"r": 2}), 12.566370614, places=8)
        self.assertEqual(Expression("(a - 1) / (a + 1)").evaluate({"a": 3}), 0.5)

    def test_comparisons_and_booleans(self):
        self.assertTrue(Expression("a >= 1 and b <= 2").evaluate({"a": 1, "b": 2}))
        self.assertFalse(Expression("a > 1 or not flag").evaluate({"a": 0.5, "flag": True}))
        self.assertTrue(Expression("x == y").evaluate({"x": 1.0, "y": 1.0}))

    def test_rejects_dangerous_constructs(self):
        for bad in (
            "__import__('os').system('dir')",
            "().__class__",
            "[x for x in range(10)]",
            "open('file')",
            "eval('1')",
            "lambda: 1",
            "'a' * 1000000 + secret",
        ):
            with self.assertRaises(Exception, msg=bad):
                Expression(bad).evaluate({})

    def test_missing_variable_reported(self):
        expr = Expression("a + b")
        with self.assertRaises(Exception):
            expr.evaluate({"a": 1})

    def test_division_by_zero(self):
        with self.assertRaises(Exception):
            Expression("1 / 0").evaluate({})

    def test_rule_model_compiles_expression(self):
        rule = Rule(code="T-1", discipline="ARCHITECTURE", category="G",
                    severity=RuleSeverity.WARNING, expression="thickness < min_t",
                    message="delgado", parameters={"min_t": 0.1})
        self.assertTrue(rule.compiled.evaluate({"thickness": 0.05, "min_t": 0.1}))


class TestEvents(unittest.TestCase):
    def test_pubsub_and_wildcard(self):
        bus = EventBus()
        seen = []
        bus.subscribe(EventType.OBJECT_CREATED, seen.append)
        bus.subscribe("*", seen.append)
        errors = bus.emit(Event(type=EventType.OBJECT_CREATED, payload={"x": 1}))
        self.assertEqual(len(seen), 2)
        self.assertEqual(errors, [])

    def test_handler_failure_does_not_break_emit(self):
        bus = EventBus()

        def boom(event):
            raise RuntimeError("boom")

        bus.subscribe(EventType.OBJECT_UPDATED, boom)
        errors = bus.emit(Event(type=EventType.OBJECT_UPDATED))
        self.assertEqual(len(errors), 1)
        self.assertIn("boom", errors[0])


class _Counter(Command):
    name = "COUNTER"

    def __init__(self, state: dict, delta: int):
        self.state = state
        self.delta = delta

    def execute(self, context=None):
        self.state["value"] += self.delta
        return self.state["value"]

    def undo(self, context=None, result=None):
        self.state["value"] -= self.delta


class TestCommandBus(unittest.TestCase):
    def test_undo_redo(self):
        bus = CommandBus()
        state = {"value": 0}
        bus.execute(_Counter(state, 5), None)
        bus.execute(_Counter(state, 3), None)
        self.assertEqual(state["value"], 8)
        bus.undo(None)
        self.assertEqual(state["value"], 5)
        bus.redo(None)
        self.assertEqual(state["value"], 8)
        bus.undo(None)
        bus.undo(None)
        self.assertEqual(state["value"], 0)
        self.assertFalse(bus.can_undo)
        self.assertTrue(bus.can_redo)

    def test_macro_transactional(self):
        bus = CommandBus()
        state = {"value": 0}

        class Failing(Command):
            name = "FAIL"

            def execute(self, context=None):
                raise RuntimeError("no")

            def undo(self, context=None, result=None):
                state["value"] -= 100

        macro = MacroCommand("m")
        macro.add(_Counter(state, 10))
        macro.add(Failing())
        with self.assertRaises(RuntimeError):
            bus.execute(macro, None)
        # Transactional: the first child was rolled back
        self.assertEqual(state["value"], 0)


if __name__ == "__main__":
    unittest.main()
