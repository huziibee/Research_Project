import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("ambik",Path(__file__).parents[1]/"scripts"/"score_ambik_ambiguity_type.py"); module=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
def test_exact_set_scoring():
    key=[]; prediction=[]
    for i in range(1000):
        row={"record_id":str(i),"source_fingerprint_sha256":str(i),"ambiguity_types":["preference"]}; key.append(row); prediction.append(dict(row))
    prediction[0]["ambiguity_types"]=["commonsense"]
    result=module.score_rows(key,prediction)
    assert result["correct"]==999 and result["accuracy"]==.999
