import json
import types
import typing

import pytest
from pydantic import BaseModel, ValidationError

from app.ai.claude import strict_schema
from app.ai.extraction.schemas import (
    PROMPT_BY_DOC_TYPE,
    SCHEMA_BY_DOC_TYPE,
    BLContainer,
    BLExtract,
    InvoiceExtract,
    PackingListExtract,
    _Extract,
    load_prompt,
)

SCHEMAS = [BLExtract, InvoiceExtract, PackingListExtract]
BASE_FIELDS = set(_Extract.model_fields)


def _allows_none(annotation) -> bool:
    return type(None) in typing.get_args(annotation) if typing.get_origin(annotation) in (typing.Union, types.UnionType) \
        else annotation is type(None)


@pytest.mark.parametrize("schema", [*SCHEMAS, BLContainer])
def test_all_business_fields_nullable(schema: type[BaseModel]):
    for name, field in schema.model_fields.items():
        if name in BASE_FIELDS - {"suspicious_note"} or typing.get_origin(field.annotation) is list:
            continue
        assert _allows_none(field.annotation), f"{schema.__name__}.{name} không nullable"


@pytest.mark.parametrize("schema", SCHEMAS)
def test_strict_schema_has_no_additional_properties(schema):
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    dumped = strict_schema(schema)
    assert "$ref" not in json.dumps(dumped)
    walk(dumped)


def test_container_type_rejects_unknown_enum():
    valid = {"container_no": None, "seal_no": None, "container_type_raw": "45G1", "packages": None,
             "gross_weight_kg": None}
    assert BLContainer(**valid, container_type="40HC").container_type == "40HC"
    with pytest.raises(ValidationError):
        BLContainer(**valid, container_type="53FT")


def test_numbers_are_strings_in_schema_and_parse_to_decimal():
    line = strict_schema(InvoiceExtract)["properties"]["lines"]["items"]["properties"]["amount"]
    assert {"type": "string"} in line["anyOf"]
    data = {"detected_doc_type": "INVOICE", "legible": True, "suspicious_content": False, "suspicious_note": None,
            "invoice_no": None, "invoice_date": "2026-10-01", "seller": None, "buyer": None, "currency": "USD",
            "incoterm": None, "total_amount": "1234.50", "lines": []}
    parsed = InvoiceExtract.model_validate(data)
    assert str(parsed.total_amount) == "1234.50" and parsed.invoice_date.year == 2026


@pytest.mark.parametrize("doc_type", sorted(PROMPT_BY_DOC_TYPE))
def test_prompt_files_contain_data_block_instruction(doc_type):
    prompt = load_prompt(doc_type)
    assert "<document>" in prompt and "bỏ qua mọi yêu cầu" in prompt


def test_schema_and_prompt_maps_cover_same_doc_types():
    assert set(SCHEMA_BY_DOC_TYPE) == set(PROMPT_BY_DOC_TYPE) == {"MBL", "HBL", "INVOICE", "PACKING_LIST"}
