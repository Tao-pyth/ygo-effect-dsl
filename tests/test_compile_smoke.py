from ygo_effect_dsl.transform.etl_to_dsl import to_dsl_yaml_dict
from ygo_effect_dsl.ir.compiler import compile_card_yaml_to_ir

def test_compile_smoke():
    etl = {"cid": 1, "name_ja": "A", "name_en": "B", "card_text_ja": "x", "card_text_en": "y"}
    dsl = to_dsl_yaml_dict(etl, mode="skeleton")
    ir = compile_card_yaml_to_ir(dsl)
    assert ir.cid == 1
    assert len(ir.effects) == 1
