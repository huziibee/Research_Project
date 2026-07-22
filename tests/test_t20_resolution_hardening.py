"""RED/GREEN regression tests for T20 context-resolution hardening.

Locks in the intended contract for ``ContextResolver``:

* no unconditional ``or True`` escape hatch -- resolving a unique scene
  referent still requires the value to be compatible with the command;
* only explicitly unresolved slots are ever targeted (an empty
  ``unresolved_slots`` must not silently trigger object/destination lookup);
* object/destination evidence patterns must not bleed into each other;
* the entire ``capability_context`` string must never become a tool value;
* resolution must never produce duplicate records or overwrite an
  already-filled, supported value;
* risk-blocked slots remain unresolved and evidence conflicts are detected;
* an already-clear analysis must not gain extra, context-derived specificity.
"""

from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import ResolvedSlotValue, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import RiskLevel
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput


def _resolver() -> ContextResolver:
    return ContextResolver(
        policy={
            "block_silent_resolve_risk_levels": ["medium", "high"],
            "approved_defaults": {},
        }
    )


def _input(
    *,
    command: str = "Bring me the mug.",
    scene: str | None = None,
    dialogue: list[str] | None = None,
    capability: str | None = None,
) -> SystemInput:
    return SystemInput(
        record_id="rec-1",
        command=command,
        scene_context=scene,
        dialogue_history=tuple(dialogue or []),
        capability_context=capability,
    )


def _analysis(*slots: str, risk: RiskLevel | None = None) -> StructuredAnalysis:
    return StructuredAnalysis(
        unresolved_slots=[UnresolvedSlot(slot_name=slot, reason="test") for slot in slots],
        risk_level=risk,
    )


class T20ResolutionHardeningTests(unittest.TestCase):
    def test_unique_scene_referent_requires_command_compatibility(self) -> None:
        resolver = _resolver()

        result = resolver.resolve(
            _input(command="Bring it to me please.", scene="objects: red mug"),
            _analysis("object"),
            target_slots=["object"],
        )

        self.assertNotEqual(
            result.events[0].outcome,
            "resolved",
            msg="unique_scene_referent must not fire unconditionally (no bare `or True`)",
        )
        self.assertEqual(result.resolved_slots, [])

    def test_empty_unresolved_slots_are_not_silently_targeted(self) -> None:
        resolver = _resolver()
        analysis = StructuredAnalysis(unresolved_slots=[])

        result = resolver.resolve(
            _input(scene="objects: red mug; destinations: left table"),
            analysis,
        )

        self.assertEqual(
            result.events,
            [],
            msg="an explicitly empty unresolved_slots list must not fall back to object/destination",
        )
        self.assertEqual(result.resolved_slots, [])

    def test_object_slot_not_confused_by_destination_evidence(self) -> None:
        resolver = _resolver()

        result = resolver.resolve(
            _input(scene="destinations: left table", command="Bring the left table."),
            _analysis("object"),
            target_slots=["object"],
        )

        self.assertNotEqual(result.events[0].outcome, "resolved")

    def test_capability_context_whole_string_not_used_as_tool_value(self) -> None:
        resolver = _resolver()
        full_capability_string = "capable: pick, place; tool: gripper"

        result = resolver.resolve(
            _input(capability=full_capability_string),
            _analysis("tool"),
            target_slots=["tool"],
        )

        resolved_values = [r.value for r in result.resolved_slots if r.slot_name == "tool"]
        self.assertNotIn(
            full_capability_string,
            resolved_values,
            msg="the entire capability_context string must not become the resolved tool value",
        )

    def test_duplicate_resolution_records_prevented(self) -> None:
        resolver = _resolver()
        analysis = _analysis("destination")

        first = resolver.resolve(
            _input(scene="destinations: left table"), analysis, target_slots=["destination"]
        )
        applied = resolver.apply(analysis, first)

        second = resolver.resolve(
            _input(scene="destinations: left table"), applied, target_slots=["destination"]
        )
        final = resolver.apply(applied, second)

        destination_entries = [r for r in final.resolved_slots if r.slot_name == "destination"]
        self.assertEqual(
            len(destination_entries),
            1,
            msg="re-resolving an already-resolved slot must not append a duplicate record",
        )

    def test_conflicting_scene_evidence_detected(self) -> None:
        resolver = _resolver()

        result = resolver.resolve(
            _input(scene="destinations: left table, right table"),
            _analysis("destination"),
            target_slots=["destination"],
        )

        self.assertEqual(result.events[0].outcome, "conflicting_context")
        self.assertEqual(result.resolved_slots, [])

    def test_does_not_overwrite_already_filled_supported_value(self) -> None:
        resolver = _resolver()
        analysis = StructuredAnalysis(
            unresolved_slots=[],
            resolved_slots=[ResolvedSlotValue(slot_name="object", value="blue mug")],
        )

        result = resolver.resolve(
            _input(scene="objects: red mug"),
            analysis,
            target_slots=["object"],
        )
        applied = resolver.apply(analysis, result)

        object_entries = [r for r in applied.resolved_slots if r.slot_name == "object"]
        self.assertEqual(
            len(object_entries),
            1,
            msg="an already-filled supported value must not be duplicated or overwritten",
        )
        self.assertEqual(object_entries[0].value, "blue mug")

    def test_risk_blocked_slots_remain_unresolved(self) -> None:
        resolver = _resolver()

        result = resolver.resolve(
            _input(scene="objects: red mug"),
            _analysis("object", risk=RiskLevel.HIGH),
            target_slots=["object"],
        )

        self.assertEqual(result.unresolved_slots[0].slot_name, "object")
        self.assertEqual(result.resolved_slots, [])

    def test_clear_analysis_gets_no_added_specificity(self) -> None:
        resolver = _resolver()
        analysis = StructuredAnalysis(unresolved_slots=[], resolved_slots=[])

        result = resolver.resolve(
            _input(scene="objects: red mug; destinations: left table"),
            analysis,
        )
        applied = resolver.apply(analysis, result)

        self.assertEqual(
            applied.resolved_slots,
            [],
            msg="a clear analysis with no unresolved slots must not gain context-derived specificity",
        )
        self.assertIsNone(applied.resolution_method)


if __name__ == "__main__":
    unittest.main()
