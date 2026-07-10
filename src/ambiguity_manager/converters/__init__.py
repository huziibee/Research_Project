"""Dataset-specific converters into the canonical schema.

Each converter is intentionally isolated from the canonical schema module: it
maps a single source dataset onto :class:`CanonicalRecord` and reports full row
accounting. Converters must never fabricate labels the source does not provide.
"""
