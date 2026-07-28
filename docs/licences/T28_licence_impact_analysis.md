# T28-R2 licence impact analysis

These are non-mutating decision-support scenarios. No reduced corpus was created and the frozen T15 manifests were not changed.

## all_current_primary_sources

- train: 11294; dev: 2396; task targets: 13058
- source balance: `{"ambik": 850, "clara": 4664, "codraw_icr_v2": 5980, "indirect_requests": 770, "vague": 1426}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 1426, "capability": 0, "clarification_target": 0, "compound_ambiguity": 5652, "context_blind_pairing": 0, "cpc": 1426, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 3912, "None": 7406, "True": 2372}`
- route: `{"None": 10741, "clarify": 1384, "execute": 1565}`
- risk: `{"None": 13690}`
- capability: `{"None": 9026, "capable": 2949, "unknown": 1715}`
- groups: 5498; train/dev group-disjoint: True; minimum coverage satisfiable: False

## only_explicitly_licensed_sources

- train: 0; dev: 0; task targets: 0
- source balance: `{}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 0, "capability": 0, "clarification_target": 0, "compound_ambiguity": 0, "context_blind_pairing": 0, "cpc": 0, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{}`
- route: `{}`
- risk: `{}`
- capability: `{}`
- groups: 0; train/dev group-disjoint: True; minimum coverage satisfiable: False

## only_sources_verified_for_noncommercial_academic_training

- train: 0; dev: 0; task targets: 0
- source balance: `{}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 0, "capability": 0, "clarification_target": 0, "compound_ambiguity": 0, "context_blind_pairing": 0, "cpc": 0, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{}`
- route: `{}`
- risk: `{}`
- capability: `{}`
- groups: 0; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_ambik

- train: 10594; dev: 2246; task targets: 12208
- source balance: `{"clara": 4664, "codraw_icr_v2": 5980, "indirect_requests": 770, "vague": 1426}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 1426, "capability": 0, "clarification_target": 0, "compound_ambiguity": 4802, "context_blind_pairing": 0, "cpc": 1426, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 3912, "None": 7406, "True": 1522}`
- route: `{"None": 9891, "clarify": 1384, "execute": 1565}`
- risk: `{"None": 12840}`
- capability: `{"None": 8176, "capable": 2949, "unknown": 1715}`
- groups: 4648; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_indirect_requests

- train: 10660; dev: 2260; task targets: 12920
- source balance: `{"ambik": 850, "clara": 4664, "codraw_icr_v2": 5980, "vague": 1426}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 1426, "capability": 0, "clarification_target": 0, "compound_ambiguity": 5514, "context_blind_pairing": 0, "cpc": 1426, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 3280, "None": 7406, "True": 2234}`
- route: `{"None": 9971, "clarify": 1384, "execute": 1565}`
- risk: `{"None": 12920}`
- capability: `{"None": 8256, "capable": 2949, "unknown": 1715}`
- groups: 5114; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_codraw_icr_v2

- train: 6371; dev: 1339; task targets: 7078
- source balance: `{"ambik": 850, "clara": 4664, "indirect_requests": 770, "vague": 1426}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 1426, "capability": 0, "clarification_target": 0, "compound_ambiguity": 5652, "context_blind_pairing": 0, "cpc": 1426, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 3912, "None": 1426, "True": 2372}`
- route: `{"None": 4761, "clarify": 1384, "execute": 1565}`
- risk: `{"None": 7710}`
- capability: `{"None": 3046, "capable": 2949, "unknown": 1715}`
- groups: 2273; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_vague

- train: 10121; dev: 2143; task targets: 11632
- source balance: `{"ambik": 850, "clara": 4664, "codraw_icr_v2": 5980, "indirect_requests": 770}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 0, "capability": 0, "clarification_target": 0, "compound_ambiguity": 5652, "context_blind_pairing": 0, "cpc": 0, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 3912, "None": 5980, "True": 2372}`
- route: `{"None": 9315, "clarify": 1384, "execute": 1565}`
- risk: `{"None": 12264}`
- capability: `{"None": 7600, "capable": 2949, "unknown": 1715}`
- groups: 4474; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_clara

- train: 7430; dev: 1596; task targets: 8394
- source balance: `{"ambik": 850, "codraw_icr_v2": 5980, "indirect_requests": 770, "vague": 1426}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 1426, "capability": 0, "clarification_target": 0, "compound_ambiguity": 988, "context_blind_pairing": 0, "cpc": 1426, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{"False": 632, "None": 7406, "True": 988}`
- route: `{"None": 9026}`
- risk: `{"None": 9026}`
- capability: `{"None": 9026}`
- groups: 5483; train/dev group-disjoint: True; minimum coverage satisfiable: False

## remove_all_unresolved_sources

- train: 0; dev: 0; task targets: 0
- source balance: `{}`
- per-task counts: `{"adapter_training": 0, "ambiguity_presence_types": 0, "candidate_interpretations": 0, "capability": 0, "clarification_target": 0, "compound_ambiguity": 0, "context_blind_pairing": 0, "cpc": 0, "rejection": 0, "risk": 0, "route": 0, "source_development_evaluation": 0, "speech_act_intent": 0, "uncertainty_sampling": 0}`
- ambiguity: `{}`
- route: `{}`
- risk: `{}`
- capability: `{}`
- groups: 0; train/dev group-disjoint: True; minimum coverage satisfiable: False
