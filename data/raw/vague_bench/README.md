---
dataset_info:
  features:
  - name: image
    dtype: image
  - name: image_name
    dtype: string
  - name: direct
    dtype: string
  - name: indirect
    dtype: string
  - name: solution
    dtype: string
  - name: mcq
    struct:
    - name: 1_correct
      dtype: string
    - name: 2_fake_scene
      dtype: string
    - name: 3_surface_understanding
      dtype: string
    - name: 4_wrong_entity
      dtype: string
    - name: ordering
      sequence: string
  - name: meta
    struct:
    - name: caption
      dtype: string
    - name: ram_entity
      sequence: string
    - name: img_size
      struct:
      - name: width
        dtype: float32
      - name: height
        dtype: float32
    - name: person_bbox
      sequence:
        sequence: float32
    - name: rating
      struct:
      - name: direct
        dtype: int32
      - name: indirect
        dtype: int32
    - name: fake_caption
      dtype: string
  splits:
  - name: train
    num_bytes: 204627243.718
    num_examples: 1677
  download_size: 220902219
  dataset_size: 204627243.718
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train-*
---
