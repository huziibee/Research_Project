"""Build tiny Arrow IPC stream fixtures for IndirectRequests converter tests."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa

FIXTURES_DIR = Path(__file__).parent

SCHEMA = pa.schema(
    [
        ("creation_date", pa.string()),
        ("utterance", pa.string()),
        ("slot_description", pa.string()),
        ("situation", pa.string()),
        ("service", pa.string()),
        ("possible_slot_values", pa.string()),
        ("bool_rephrased_slot_values", pa.string()),
        ("target_slot_value", pa.string()),
        ("mean_world_understanding", pa.float64()),
    ]
)


def write_ipc_stream(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        with pa.ipc.new_stream(handle, SCHEMA) as writer:
            writer.write_table(table)


def build() -> None:
    write_ipc_stream(
        FIXTURES_DIR / "train" / "data-00000-of-00001.arrow",
        [
            {
                "creation_date": "2023-07-26T00:55:08.699000",
                "utterance": "I feel like something spicy tonight.",
                "slot_description": "Cuisine of food served in the restaurant",
                "situation": "User is choosing a restaurant.",
                "service": "Restaurants_1",
                "possible_slot_values": "['Mexican', 'Chinese', 'Indian']",
                "bool_rephrased_slot_values": "['Mexican', 'Chinese', 'Indian']",
                "target_slot_value": "Mexican",
                "mean_world_understanding": 4.5,
            },
            {
                "creation_date": "2023-07-26T00:46:16.458000",
                "utterance": "Somewhere the kids would enjoy.",
                "slot_description": "Category to which the attraction belongs",
                "situation": "Planning a family outing.",
                "service": "Travel_1",
                "possible_slot_values": "['Theme Park', 'Museum', 'Park']",
                "bool_rephrased_slot_values": "['Theme Park', 'Museum', 'Park']",
                "target_slot_value": "<ambiguous>",
                "mean_world_understanding": 5.0,
            },
            {
                "creation_date": "2023-07-26T00:47:30.838000",
                "utterance": "I need a place with internet.",
                "slot_description": "Boolean flag indicating if the hotel has wifi",
                "situation": "Booking a hotel room.",
                "service": "Hotels_1",
                "possible_slot_values": "['True', 'False']",
                "bool_rephrased_slot_values": (
                    "['The hotel should have wifi.', 'The hotel should not have wifi.']"
                ),
                "target_slot_value": "True",
                "mean_world_understanding": 3.0,
            },
            {
                "creation_date": "2023-07-26T00:48:00.000000",
                "utterance": "A concrete request missing slot metadata.",
                "slot_description": "",
                "situation": "Synthetic quarantine case.",
                "service": "Restaurants_1",
                "possible_slot_values": "['cheap', 'moderate']",
                "bool_rephrased_slot_values": "['cheap', 'moderate']",
                "target_slot_value": "moderate",
                "mean_world_understanding": 2.0,
            },
        ],
    )
    write_ipc_stream(
        FIXTURES_DIR / "validation" / "data-00000-of-00001.arrow",
        [
            {
                "creation_date": "2023-07-26T01:02:16.825000",
                "utterance": "A never-before-seen cuisine please.",
                "slot_description": "Cuisine of food served in the restaurant",
                "situation": "User explores new food.",
                "service": "Restaurants_2",
                "possible_slot_values": "['Fusion', 'Experimental']",
                "bool_rephrased_slot_values": "['Fusion', 'Experimental']",
                "target_slot_value": "NeverSeenCuisine",
                "mean_world_understanding": 6.0,
            },
        ],
    )
    write_ipc_stream(
        FIXTURES_DIR / "test" / "data-00000-of-00001.arrow",
        [
            {
                "creation_date": "2023-07-26T01:04:46.083000",
                "utterance": "",
                "slot_description": "Price range for the restaurant",
                "situation": "Choosing dinner.",
                "service": "Restaurants_1",
                "possible_slot_values": "['cheap', 'moderate', 'expensive']",
                "bool_rephrased_slot_values": "['cheap', 'moderate', 'expensive']",
                "target_slot_value": "moderate",
                "mean_world_understanding": 2.0,
            },
        ],
    )
    bad_schema = pa.schema(
        [
            ("utterance", pa.string()),
            ("target_slot_value", pa.string()),
        ]
    )
    bad_table = pa.Table.from_pylist(
        [{"utterance": "hi", "target_slot_value": "True"}],
        schema=bad_schema,
    )
    bad_path = FIXTURES_DIR / "bad_schema.arrow"
    with bad_path.open("wb") as handle:
        with pa.ipc.new_stream(handle, bad_schema) as writer:
            writer.write_table(bad_table)

    float32_schema = pa.schema(
        [
            ("creation_date", pa.string()),
            ("utterance", pa.string()),
            ("slot_description", pa.string()),
            ("situation", pa.string()),
            ("service", pa.string()),
            ("possible_slot_values", pa.string()),
            ("bool_rephrased_slot_values", pa.string()),
            ("target_slot_value", pa.string()),
            ("mean_world_understanding", pa.float32()),
        ]
    )
    float32_table = pa.Table.from_pylist(
        [
            {
                "creation_date": "2023-07-26T00:55:08.699000",
                "utterance": "Example utterance.",
                "slot_description": "Example slot",
                "situation": "Example situation.",
                "service": "Restaurants_1",
                "possible_slot_values": "['A']",
                "bool_rephrased_slot_values": "['A']",
                "target_slot_value": "A",
                "mean_world_understanding": 1.0,
            }
        ],
        schema=float32_schema,
    )
    float32_path = FIXTURES_DIR / "bad_float32_schema.arrow"
    with float32_path.open("wb") as handle:
        with pa.ipc.new_stream(handle, float32_schema) as writer:
            writer.write_table(float32_table)


if __name__ == "__main__":
    build()
