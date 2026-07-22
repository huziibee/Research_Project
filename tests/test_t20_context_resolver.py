from __future__ import annotations

import unittest

from ambiguity_manager.schema.v2.records import EvidenceRef, UnresolvedSlot
from ambiguity_manager.schema.v2.taxonomies import RiskLevel
from ambiguity_manager.systems.context_resolution import ContextResolver
from ambiguity_manager.systems.contracts import StructuredAnalysis, SystemInput


def _resolver() -> ContextResolver:
    return ContextResolver(
        policy={
            "block_silent_resolve_risk_levels": ["medium", "high"],
            "approved_defaults": {"destination": "home base"},
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


class T20ContextResolverTests(unittest.TestCase):
    def test_unique_referent_resolves(self) -> None:
        resolver = _resolver()
        result = resolver.resolve(
            _input(scene="objects: red mug"),
            _analysis("object"),
            target_slots=["object"],
        )

        self.assertEqual(result.events[0].outcome, "resolved")
        self.assertEqual(result.resolved_slots[0].value, "red mug")
        self.assertEqual(result.resolution_evidence[0].source, "scene_context")
        self.assertEqual(result.resolution_method, "deterministic_context_resolution_v1")

    def test_ambiguous_referent_stays_unresolved_with_conflict(self) -> None:
        resolver = _resolver()
        result = resolver.resolve(
            _input(scene="objects: red mug, blue mug"),
            _analysis("object"),
            target_slots=["object"],
        )

        self.assertEqual(result.events[0].outcome, "conflicting_context")
        self.assertEqual(result.unresolved_slots[0].slot_name, "object")
        self.assertEqual(result.resolution_method, None)

    def test_risk_blocks_resolution(self) -> None:
        resolver = _resolver()
        result = resolver.resolve(
            _input(scene="objects: red mug"),
            _analysis("object", risk=RiskLevel.HIGH),
            target_slots=["object"],
        )

        self.assertEqual(result.events[0].outcome, "resolution_blocked_by_risk")
        self.assertEqual(result.events[0].details["risk_level"], "high")
        self.assertEqual(result.resolved_slots, [])

    def test_unsupported_default_is_rejected(self) -> None:
        resolver = _resolver()
        result = resolver.resolve(
            _input(scene=None),
            _analysis("recipient"),
            target_slots=["recipient"],
        )

        self.assertEqual(result.events[0].outcome, "unresolved")
        self.assertEqual(result.events[0].rule_id, "no_world_knowledge_guess")
        self.assertEqual(result.events[0].details["reason"], "unsupported_default_rejected")

    def test_existing_evidence_is_retained_when_new_resolution_added(self) -> None:
        resolver = _resolver()
        analysis = _analysis("destination")
        analysis.resolution_evidence = [EvidenceRef(source="command", span="cup")]

        result = resolver.resolve(
            _input(scene="destinations: left table"),
            analysis,
            target_slots=["destination"],
        )
        applied = resolver.apply(analysis, result)

        self.assertEqual(len(applied.resolution_evidence), 2)
        self.assertEqual(applied.resolution_evidence[0].source, "command")
        self.assertEqual(applied.resolution_evidence[1].source, "scene_context")


if __name__ == "__main__":
    unittest.main()
