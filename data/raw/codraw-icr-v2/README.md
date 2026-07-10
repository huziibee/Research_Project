# CoDraw-iCR (v2)

This is the data repository accompanying the following publication:

> “Are you telling me to put glasses on the dog?” Content-Grounded Annotation of Instruction Clarification Requests in the CoDraw Dataset. (Madureira, B. & Schlangen, D., upcoming).

In visual instruction-following dialogue games, players can engage in repair mechanisms in face of an ambiguous or underspecified instruction that cannot be fully mapped to actions in the world. In this work, we annotate **Instruction Clarification Requests (iCRs)** in CoDraw, an existing dataset of interactions in a multi-modal collaborative dialogue game. We show that it contains lexically and semantically diverse iCRs being produced self-motivatedly by players deciding to clarify in order to solve the task successfully. With >8k iCRs found in 9.9k dialogues, CoDraw-iCR (v2) is a large spontaneous iCR corpus, making it a valuable resource for data-driven research on clarification in dialogue.

This is a continuation to CoDraw-iCR (v1). Here, the iCRs' content and form are identified, using categories grounded in the underlying dialogue game. Besides, all types occurring more than one time, which were first collapsed into one observation (during iCR identification), are then also annotated in their own context.

Details about the annotation can be found in the paper.

The whole annotation process occurred as follows:

1. Annotator 1 identified iCRs among all drawer utterance types. Types occurring more than once were collapsed into a single datapoint, without context.
2. Annotator 2, after more training, decided whether they agreed with Annotator 1 for all utterance types, and annotated the fine-grained categories.
3. Annotator 2 performed the fine-grained annotation on all identified iCR types that occurred more than once, each in its own context.

## Directory Structure

- ```codraw-icr-v2.tsv```: The main data file used in the analysis, which should preferably be used in subsequent works. It is a filtered version of the raw data, containing only the iCRs (as judged by the second annotator, who had more training) and, for types occurring in multiple utterances, it contains only the in-context annotation.
- ```codraw-icr-v2_raw.tsv```: For documentation and inspection purposes, this file contains all the data from the all annotation rounds.
- ```clipmap.json```: A dictionary mapping png files to the names used in the annotation. Note: all boys/girls are collapsed into a single boy/girls category, respectively. In this file, only the prefix of their cliparts is given.
- ```annotation-report.pdf```: Documentation of the annotation process and of some decisions for specific cases.

## Data Structure

- ```drawer```: The utterance being annotated, from the drawer (instruction follower), extracted from the fields msg_d in the CoDraw JSON file.
- ```teller_before```: The immediately preceding utterance by the teller (instruction giver), extracted from the fields msg_t in the CoDraw JSON file.
- ```teller_after```: The immediately following utterance by the teller (instruction giver), extracted from the fields msg_t in the CoDraw JSON file.
- ```is_CR_annotator_1```: ```1``` if annotator 1 considers this utterance an iCR and ```0``` otherwise.
- ```is_CR_annotator_2```: ```1``` if annotator 2 considers this utterance an iCR and ```0``` otherwise. This was programatically computed based on the agreement decision performed by annotator 2.
- ```do_annotators_agree```: ```1``` if annotators agree and ```0``` otherwise.

Columns with values annotating the drawer's utterances in the row:

- ```mood```: A comma-separated list of moods. Options: ```declarative```, ```polar question```, ```alternative question```, ```wh- question```, ```imperative``` and ```other```.
- ```is_source_utterance_last_turn```: ```1``` if the iCR refers to an instruction in ```teller_before```, ```0``` otherwise.
- ```next_turn_contains_response```: ```1``` if the iCR refers to an instruction in ```teller_after```, ```0``` otherwise.
- ```clipart```: Is it possible to identify which clipart the CR refer to? Options: ```unknown```, ```many```, ```two```, ```one```.
- ```clipart_{1, 2, 3, 4, 5}```: If it was possible to identify the cliparts, they were selected in these columns, in the order they occur. Options: the list of cliparts in ```clipmap.json```.
- ```position```: ```1``` if the iCR about an object's position, else ```0```.
- ```size```: ```1``` if the iCR is about an object's size, else ```0```.
- ```direction```: ```1``` if the iCR is about an object's direction/orientation, else ```0```.
- ```relation_to_other_cliparts```: ```1``` if the iCR is about relations between two or more objects, else ```0```.
- ```disambig_object```: ```1``` if the iCR is trying to disambiguate between similar objects (e.g. trees, glasses, balls, etc), else ```0```.
- ```disambig_person```: ```1``` if the iCR is trying to disambiguate the facial expression or pose of the boy or the girl, else ```0```,

Metadata columns:

- ```game_name```: The dialogue id in which the utterance occurs in the in the CoDraw JSON file, or ```multiple``` for types occurring more than once (in their annotation without context).
- ```turn```: The turn id in which the utterance occurs in dialogue ```game_name```, or ```multiple``` for types occurring more than once (in their annotation without context).
- ```annotation_round```: ```all types``` for the annotation round of unique types or ```repeated types in own context``` for the annotation round where the subset of repeated types was annotated with their own context.
- ```freq```: How many times this utterance type occurred in CoDraw dataset (only relevant for the ```all types``` annotation round.)

## Attribution

This repository contains annotation on the CoDraw dataset, available at [https://github.com/facebookresearch/CoDraw](https://github.com/facebookresearch/CoDraw), which was published as:

> Jin-Hwa Kim, Nikita Kitaev, Xinlei Chen, Marcus Rohrbach, Byoung-Tak Zhang, Yuandong Tian, Dhruv Batra, and Devi Parikh. 2019. [CoDraw: Collaborative Drawing as a Testbed for Grounded Goal-driven Communication](https://aclanthology.org/P19-1651/). In Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics, pages 6495–6513, Florence, Italy. Association for Computational Linguistics.

If you use this resource, please cite our work and the original work.

```
@misc{madureira2023icrv2,
      title={"Are you telling me to put glasses on the dog?'' Content-Grounded Annotation of Instruction Clarification Requests in the CoDraw Dataset},
      author={Brielen Madureira and David Schlangen},
      year={2023},
      eprint={2306.02377},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```

```
@inproceedings{kim-etal-2019-codraw,
    title = "{C}o{D}raw: Collaborative Drawing as a Testbed for Grounded Goal-driven Communication",
    author = "Kim, Jin-Hwa  and
      Kitaev, Nikita  and
      Chen, Xinlei  and
      Rohrbach, Marcus  and
      Zhang, Byoung-Tak  and
      Tian, Yuandong  and
      Batra, Dhruv  and
      Parikh, Devi",
    booktitle = "Proceedings of the 57th Annual Meeting of the Association for Computational Linguistics",
    month = jul,
    year = "2019",
    address = "Florence, Italy",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/P19-1651",
    doi = "10.18653/v1/P19-1651",
    pages = "6495--6513",
}
```

## License

The annotation is licensed under the same license of the original dataset, i.e. the Creative Commons Attribution-NonCommercial 4.0 International Public License. Please check the complete terms in the```license.txt``` file.
