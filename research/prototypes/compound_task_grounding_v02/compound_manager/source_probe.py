"""Frozen exploratory rule-based source-only probe, NOT a language model.

Purpose: permit a 120-row *development* stress test without a GPU or LLM
inference API. A heuristic readiness prediction is NOT a validated task.
Never call this output action_ready or treat it as complete grounding.
No gold, prior routes, capability, or risk used during prediction.
"""
from __future__ import annotations
import re
from typing import Any

PROBE_VERSION = 'raw_source_readiness_heuristic_v0.2_frozen'

# Defined before the full Pilot-120 evaluation. Patterns are intentionally broad;
# their limitations and regressions must be reported, not optimized on the panel.
BLOCK_PATTERNS: tuple[tuple[str,str], ...] = (
    ('no_default', r'neither\s+(?:one\s+)?(?:is\s+)?(?:the\s+)?default|no\s+default\s+(?:is\s+)?(?:given|defined|specified)'),
    ('requires_specific_choice', r'(?:requires?|must)\s+(?:the\s+)?(?:requester|user|operator|human)?\s*(?:to\s+)?(?:choose|select|confirm|specify|identify)\b'),
    ('requires_exact_amount', r'requires?\s+an?\s+exact\s+(?:amount|quantity)\s+before'),
    ('choice_not_specified', r'(?:does\s+not|do\s+not|doesn.t|is\s+not|not)\s+(?:explicitly\s+)?(?:choose|identify|specify|select|name|provide|resolve|say|indicate)\b'),
    ('explicit_unresolved', r'\b(?:unresolved|undetermined|ambiguous|cannot\s+disambiguate|no\s+unique)\b'),
    ('confirmation_before_scope', r'requires?\s+(?:requester\s+)?confirmation\s+before\s+selecting'),
    ('physical_digital_unselected', r'(?:physical\s+(?:folder|filing)|digital\s+(?:filing|record)).{0,150}(?:does not choose|not selected|no medium)'),
    ('no_assignment', r'(?:no|without)\s+(?:assignment\s+code|recipient\s+name|task\s+identifier)'),
)


def probe(source: dict[str, Any]) -> dict[str, Any]:
    command = str(source.get('command', ''))
    scene = str(source.get('scene_context', ''))
    dialogue = ' '.join(source.get('dialogue_history') or [])
    combined = command + '\n' + scene + '\n' + dialogue
    evidence = []
    for reason, pat in BLOCK_PATTERNS:
        match = re.search(pat, combined, flags=re.I|re.S)
        if match:
            evidence.append({'reason':reason,'quote':match.group(0)})
    # One negation-scope construction is structurally ambiguous independently
    # of scene evidence when there is no disambiguating punctuation/emphasis.
    if re.search(r'\bdo not\s+\w+\s+and\s+\w+\b',command, re.I) and re.search(r'without punctuation|requires requester confirmation',scene,re.I):
        evidence.append({'reason':'negation_scope','quote':command})
    # A request with a model-inferred singular object may still have several
    # selected assignments; contexts explicitly requiring a choice are caught.
    status = 'needs_clarification' if evidence else 'readiness_candidate'
    return {'record_id':source.get('record_id'), 'probe_version':PROBE_VERSION,
            'predicted_readiness':'blocking_ambiguity' if evidence else 'ready_candidate',
            'evidence':evidence,
            'candidate_coverage_verified':False,
            'complete_task_verified':False,
            'research_limit':'lexical source-only diagnostic; cannot execute or certify grounding'}


def action_scaffold(source: dict[str,Any]) -> dict[str,Any]:
    """Coarse action skeleton only, not a complete grounded graph."""
    cmd=str(source.get('command','')).lower()
    ops=[]
    if 'do not move and inspect' in cmd:
        return {'record_id':source.get('record_id'),'alternative_action_sequences':[['INSPECT'],['CANCEL_MOVE','CANCEL_INSPECTION']],
                'status':'draft_unverified','grounded_arguments':False}
    if 'configuration and inspection' in cmd:
        ops=['CONFIGURE','INSPECT']
    elif 'inspection and movement' in cmd:
        ops=['INSPECT','MOVE']
    elif 'movement and inspection' in cmd:
        ops=['MOVE','INSPECT']
    elif 'place' in cmd and ('then handle' in cmd or 'then return' in cmd):
        ops=['PLACE','RETURN']
    elif ('top up' in cmd or 'refill' in cmd) and 'then return' in cmd:
        ops=['REFILL','RETURN']
    elif 'then return' in cmd:
        if 'open' in cmd: ops=['OPEN','RETURN']
        elif 'seal' in cmd: ops=['SEAL','RETURN']
        elif 'move' in cmd: ops=['MOVE','RETURN']
        else: ops=['TASK_UNRESOLVED','RETURN']
    elif 'then seal' in cmd:ops=['TASK_INHERIT','SEAL']
    elif 'then place' in cmd:ops=['TASK_INHERIT','PLACE']
    elif 'do the same' in cmd:ops=['TASK_INHERIT']
    else:
        for keyword,op in [('deliver','DELIVER'),('move','MOVE'),('relocate','MOVE'),('set','CONFIGURE'),('stock','STOCK'),('refill','REFILL'),('top up','REFILL'),('file','FILE'),('clean','CLEAN'),('recharge','RECHARGE'),('open','OPEN'),('seal','SEAL'),('inspect','INSPECT'),('measure','MEASURE'),('prepare','PREPARE'),('take','TRANSPORT'),('print','PRINT'),('contain','CONTAIN'),('add','ADD'),('carry out','TASK_UNRESOLVED')]:
            if keyword in cmd:
                ops=[op];break
    if not ops:ops=['UNPARSED']
    return {'record_id':source.get('record_id'), 'action_sequence':ops, 'status':'draft_unverified',
            'grounded_arguments':False,'coverage_verified':False}