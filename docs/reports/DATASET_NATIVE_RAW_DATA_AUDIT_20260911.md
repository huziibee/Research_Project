# Dataset-native raw-data audit

This is a pre-results source-data audit. It contains no model outputs or scores.

## VAGUE

- Records: 1677; prepared rows: 3354.
- Pair-integrity failures: 0.
- Duplicate normalized-command groups: 1; groups with conflicting source targets: 1.
- command_only: 1676 unique effective inputs; 1 repeated groups; 1 target-conflicting groups.
- command_plus_textual_caption: 1677 unique effective inputs; 0 repeated groups; 0 target-conflicting groups.
- Manual review IDs (longest provided context): vague:diteeSODzTQ@1, vague:etyH2OUxVuQ@6, vague:gV4WFBjc01I@33, vague:gYhC67R4g64@9, vague:gvKBHCBBdf0@23, vague:jLo7tHDHgOc@4, vague:lhGtoYnSdl8@1, vague:lhGtoYnSdl8@38, vague:n3BgbwW6PXc@3, vague:nLTcdOr66lA@36.

## AmbiK

- Records: 1000; prepared rows: 1000.
- Duplicate normalized-command groups: 2; groups with conflicting source targets: 0.
- Unique effective inputs: 1000; repeated effective-input groups: 0; target conflicts among repeated inputs: 0.
- Literal-label-token screen: 0/1000 records. This is only a manual-review signal, not evidence of leakage.
- Manual review IDs (longest provided context): ambik:909, ambik:868, ambik:618, ambik:801, ambik:910, ambik:878, ambik:753, ambik:709, ambik:883, ambik:689.

## CLARA

- Records: 5222; prepared rows: 10444.
- Full/blind ID-set mismatch examples: 0.
- Duplicate normalized-command groups: 563; groups with conflicting source targets: 23.
- Unique effective inputs: 2738; repeated effective-input groups: 670; target conflicts among repeated inputs: 9.
- Literal-label-token screen: 0/5222 records. This is only a manual-review signal, not evidence of leakage.
- Manual review IDs (longest provided context): clara:1260, clara:1261, clara:1262, clara:1263, clara:1264, clara:1265, clara:1266, clara:1267, clara:1268, clara:1269.

## Indirect Requests

- Records: 906; prepared rows: 906.
- Duplicate normalized-command groups: 452; groups with conflicting source targets: 0.
- Unique effective inputs: 452; repeated effective-input groups: 452; target conflicts among repeated inputs: 0.
- Literal-label-token screen: 0/906 records. This is only a manual-review signal, not evidence of leakage.
- Manual review IDs (longest provided context): indirect_requests:train:1, indirect_requests:train:3, indirect_requests:train:4, indirect_requests:train:5, indirect_requests:train:9, indirect_requests:train:10, indirect_requests:train:11, indirect_requests:train:12, indirect_requests:train:13, indirect_requests:train:14.

## Interpretation rule

A duplicate command with different source targets means command-only accuracy is conditional on supplied context, not that the dataset is invalid. Literal expected-label words in text can be legitimate task language; inspect those records before making a leakage claim.
