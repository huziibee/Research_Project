"""Create a gold-free task-graph extraction prompt from a source record JSON."""
import argparse
import json
from pathlib import Path
from compound_manager.model_adapter import build_model_prompt

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path,help='JSON source with command/scene_context/dialogue_history')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
source=json.loads(args.source.read_text(encoding='utf-8'))
prompt=build_model_prompt(source)
if args.output:
    args.output.parent.mkdir(exist_ok=True,parents=True)
    args.output.write_text(prompt+'\n',encoding='utf-8')
else:
    print(prompt)