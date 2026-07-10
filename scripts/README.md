# scripts

Operational and audit scripts (for example the T02 dataset audit) are added by
later tickets. Scripts that write files must route target paths through
`ambiguity_manager.io_guard.resolve_writable_path` to avoid writing into
`data/raw`.
