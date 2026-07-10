"""Build tiny Parquet fixtures for the VAGUE converter tests."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

FIXTURES_DIR = Path(__file__).parent

MCQ_STRUCT = pa.struct(
    [
        ("1_correct", pa.string()),
        ("2_fake_scene", pa.string()),
        ("3_surface_understanding", pa.string()),
        ("4_wrong_entity", pa.string()),
        ("ordering", pa.list_(pa.string())),
    ]
)

META_STRUCT = pa.struct(
    [
        ("caption", pa.string()),
        ("ram_entity", pa.list_(pa.string())),
        (
            "img_size",
            pa.struct([("width", pa.float32()), ("height", pa.float32())]),
        ),
        ("person_bbox", pa.list_(pa.list_(pa.float32()))),
        (
            "rating",
            pa.struct([("direct", pa.int32()), ("indirect", pa.int32())]),
        ),
        ("fake_caption", pa.string()),
    ]
)

SCHEMA = pa.schema(
    [
        ("image_name", pa.string()),
        ("direct", pa.string()),
        ("indirect", pa.string()),
        ("solution", pa.string()),
        ("mcq", MCQ_STRUCT),
        ("meta", META_STRUCT),
    ]
)

IMAGE_STRUCT = pa.struct([("bytes", pa.binary()), ("path", pa.string())])

SCHEMA_WITH_IMAGE = pa.schema(list(SCHEMA) + [("image", IMAGE_STRUCT)])


def _mcq(
    correct: str,
    fake_scene: str,
    surface: str,
    wrong_entity: str,
    ordering: list[str] | None = None,
) -> dict:
    return {
        "1_correct": correct,
        "2_fake_scene": fake_scene,
        "3_surface_understanding": surface,
        "4_wrong_entity": wrong_entity,
        "ordering": ordering or ["A", "B", "C", "D"],
    }


def _meta(caption: str) -> dict:
    return {
        "caption": caption,
        "ram_entity": ["binocular"],
        "img_size": {"width": 1280.0, "height": 720.0},
        "person_bbox": [[1.0, 2.0, 3.0, 4.0]],
        "rating": {"direct": 5, "indirect": 4},
        "fake_caption": "A synthetic fake caption for tests.",
    }


def _row(
    image_name: str,
    *,
    direct: str = "Hey, person1, please hand over the binocular to person2.",
    indirect: str = "Hey person1, why not share the view with person2?",
    solution: str = "(person1, hand over, binocular)",
    caption: str = "Three people outdoors; person1 holds binoculars.",
) -> dict:
    return {
        "image_name": image_name,
        "direct": direct,
        "indirect": indirect,
        "solution": solution,
        "mcq": _mcq(
            "The speaker wants person1 to hand over the binocular to person2.",
            "The speaker wants person1 to share scrolls with friends.",
            "The speaker wants person1 to act like a fortune teller.",
            "The speaker wants person1 to hand over the telescope to person2.",
        ),
        "meta": _meta(caption),
    }


def write_parquet(path: Path, rows: list[dict], *, include_image: bool = False) -> None:
    schema = SCHEMA_WITH_IMAGE if include_image else SCHEMA
    if include_image:
        enriched = []
        for row in rows:
            item = dict(row)
            item["image"] = {
                "bytes": b"\xff\xd8\xff" + b"\x00" * 100,
                "path": f"{row['image_name']}_annot.jpg",
            }
            enriched.append(item)
        rows = enriched
    table = pa.Table.from_pylist(rows, schema=schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def build() -> None:
    write_parquet(
        FIXTURES_DIR / "tiny_vague.parquet",
        [
            _row("fixture_img_a@1"),
            _row("fixture_img_b@2", indirect="Hey person2, nice hat today."),
            _row("fixture_ego_001", solution="(person2, adjust, strap)"),
        ],
    )
    bad = pa.table({"foo": pa.array(["bar"])})
    pq.write_table(bad, FIXTURES_DIR / "bad_schema.parquet")

    write_parquet(
        FIXTURES_DIR / "quarantine.parquet",
        [
            _row("fixture_missing_indirect", indirect="   "),
            _row("fixture_bad_triplet", solution="(person1, only_two)"),
            _row("fixture_empty_triplet_part", solution="(person1, , binocular)"),
            _row("fixture_missing_caption", caption=""),
        ],
    )
    write_parquet(
        FIXTURES_DIR / "missing_source_id.parquet",
        [
            {
                "image_name": "",
                "direct": "Hey, person1, please wave.",
                "indirect": "Hey person1, look lively.",
                "solution": "(person1, wave, hand)",
                "mcq": _mcq("c1", "c2", "c3", "c4"),
                "meta": _meta("A scene."),
            },
            _row("fixture_valid_after_blank_id"),
        ],
    )
    write_parquet(
        FIXTURES_DIR / "dup_image_name.parquet",
        [
            _row("fixture_dup@1", indirect="   "),
            _row("fixture_dup@1", indirect="Hey person1, second duplicate row."),
        ],
    )
    write_parquet(
        FIXTURES_DIR / "with_image_column.parquet",
        [_row("fixture_with_image@1")],
        include_image=True,
    )

    write_parquet(
        FIXTURES_DIR / "ordering_valid_permutation.parquet",
        [
            {
                **_row("fixture_order_perm@1"),
                "mcq": _mcq(
                    "The speaker wants person1 to hand over the binocular to person2.",
                    "The speaker wants person1 to share scrolls with friends.",
                    "The speaker wants person1 to act like a fortune teller.",
                    "The speaker wants person1 to hand over the telescope to person2.",
                    ordering=["D", "C", "B", "A"],
                ),
            }
        ],
    )

    write_parquet(
        FIXTURES_DIR / "ordering_quarantine.parquet",
        [
            {
                **_row("fixture_order_missing"),
                "mcq": {
                    "1_correct": "c1",
                    "2_fake_scene": "c2",
                    "3_surface_understanding": "c3",
                    "4_wrong_entity": "c4",
                    "ordering": None,
                },
            },
            {
                **_row("fixture_order_dup"),
                "mcq": _mcq("c1", "c2", "c3", "c4", ordering=["A", "A", "B", "C"]),
            },
            {
                **_row("fixture_order_unknown"),
                "mcq": _mcq("c1", "c2", "c3", "c4", ordering=["A", "B", "C", "E"]),
            },
            {
                **_row("fixture_order_wrong_len"),
                "mcq": _mcq("c1", "c2", "c3", "c4", ordering=["A", "B", "C"]),
            },
        ],
    )

    _write_bad_schema_fixtures()


def _write_bad_schema_fixtures() -> None:
    base_row = _row("fixture_schema@1")
    top = [
        ("image_name", pa.string()),
        ("direct", pa.string()),
        ("indirect", pa.string()),
        ("solution", pa.string()),
    ]

    mcq_missing_correct = pa.struct(
        [
            ("2_fake_scene", pa.string()),
            ("3_surface_understanding", pa.string()),
            ("4_wrong_entity", pa.string()),
            ("ordering", pa.list_(pa.string())),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(
            [{**base_row, "mcq": base_row["mcq"]}],
            schema=pa.schema(top + [("mcq", mcq_missing_correct), ("meta", META_STRUCT)]),
        ),
        FIXTURES_DIR / "bad_mcq_missing_1_correct.parquet",
    )

    mcq_bad_ordering_type = pa.struct(
        [
            ("1_correct", pa.string()),
            ("2_fake_scene", pa.string()),
            ("3_surface_understanding", pa.string()),
            ("4_wrong_entity", pa.string()),
            ("ordering", pa.list_(pa.int32())),
        ]
    )
    bad_ordering_row = dict(base_row)
    bad_ordering_row["mcq"] = {
        "1_correct": base_row["mcq"]["1_correct"],
        "2_fake_scene": base_row["mcq"]["2_fake_scene"],
        "3_surface_understanding": base_row["mcq"]["3_surface_understanding"],
        "4_wrong_entity": base_row["mcq"]["4_wrong_entity"],
        "ordering": [1, 2, 3, 4],
    }
    pq.write_table(
        pa.Table.from_pylist(
            [bad_ordering_row],
            schema=pa.schema(top + [("mcq", mcq_bad_ordering_type), ("meta", META_STRUCT)]),
        ),
        FIXTURES_DIR / "bad_mcq_ordering_type.parquet",
    )

    meta_missing_caption = pa.struct(
        [
            ("ram_entity", pa.list_(pa.string())),
            (
                "img_size",
                pa.struct([("width", pa.float32()), ("height", pa.float32())]),
            ),
            ("person_bbox", pa.list_(pa.list_(pa.float32()))),
            (
                "rating",
                pa.struct([("direct", pa.int32()), ("indirect", pa.int32())]),
            ),
            ("fake_caption", pa.string()),
        ]
    )
    pq.write_table(
        pa.Table.from_pylist(
            [base_row],
            schema=pa.schema(top + [("mcq", MCQ_STRUCT), ("meta", meta_missing_caption)]),
        ),
        FIXTURES_DIR / "bad_meta_missing_caption.parquet",
    )

    meta_bad_rating = pa.struct(
        [
            ("caption", pa.string()),
            ("ram_entity", pa.list_(pa.string())),
            (
                "img_size",
                pa.struct([("width", pa.float32()), ("height", pa.float32())]),
            ),
            ("person_bbox", pa.list_(pa.list_(pa.float32()))),
            (
                "rating",
                pa.struct([("direct", pa.int32()), ("indirect", pa.float32())]),
            ),
            ("fake_caption", pa.string()),
        ]
    )
    bad_rating_row = dict(base_row)
    bad_rating_row["meta"] = {
        **base_row["meta"],
        "rating": {"direct": 5, "indirect": 4.0},
    }
    pq.write_table(
        pa.Table.from_pylist(
            [bad_rating_row],
            schema=pa.schema(top + [("mcq", MCQ_STRUCT), ("meta", meta_bad_rating)]),
        ),
        FIXTURES_DIR / "bad_meta_rating_indirect_type.parquet",
    )


if __name__ == "__main__":
    build()
