import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    field_serializer,
)
from pydantic.alias_generators import to_camel

from xrocket._core.serialization import RequestModel, RequestMoney, serialize_request
from xrocket.pay import Balance


class AmountRequest(RequestModel):
    amount: RequestMoney
    client_reference: str | None = Field(default=None, alias="clientReference")
    enabled: bool = True


class NestedRequest(RequestModel):
    nested_request: AmountRequest = Field(alias="nestedRequest")
    children: list[AmountRequest] = Field(default_factory=list)


class PayloadRequest(RequestModel):
    payload: Any


class OtherModel(BaseModel):
    pass


def test_secret_values_stay_masked_without_an_explicit_product_wire_serializer() -> None:
    secret = SecretStr("synthetic-secret-marker")
    request = PayloadRequest(payload={"nested": [secret]})
    assert json.loads(serialize_request(request)) == {"payload": {"nested": ["**********"]}}
    assert secret.get_secret_value() == "synthetic-secret-marker"


@pytest.mark.parametrize("codepoint", [0xD800, 0xDBFF, 0xDC00, 0xDFFF])
@pytest.mark.parametrize("location", ["value", "key", "serialized"])
def test_surrogates_are_rejected_without_an_encoding_exception(
    codepoint: int, location: str
) -> None:
    invalid = chr(codepoint)

    class SerializedRequest(RequestModel):
        payload: str

        @field_serializer("payload")
        def serialize_payload(self, value: str) -> str:
            return invalid

    if location == "serialized":
        request = SerializedRequest(payload="valid")
    else:
        request = PayloadRequest(payload={invalid: "valid"} if location == "key" else [invalid])
    with pytest.raises(ValueError, match="surrogate code points") as caught:
        serialize_request(request)
    assert type(caught.value) is ValueError
    assert caught.value.args == ("Request strings must not contain surrogate code points",)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_unicode_scalar_keys_and_values_keep_exact_utf8_wire_bytes() -> None:
    text = "Привет 🎁 🚀 𐀀 \uffff"
    serialized = serialize_request(PayloadRequest(payload={text: [text]}))
    assert text.encode("utf-8") in serialized
    assert json.loads(serialized) == {"payload": {text: [text]}}


@pytest.mark.parametrize(
    "value",
    [
        "123456789012345678901234567890.00000000000000000001",
        Decimal("999999999999999999999999999999.12345000000000000000"),
        Decimal("-0.0000"),
        "1E-40",
        Decimal("1.0000E+30"),
    ],
)
def test_request_money_remains_exact_and_serializes_as_string(value: str | Decimal) -> None:
    request = AmountRequest.model_validate({"amount": value})

    assert isinstance(request.amount, Decimal)
    assert request.amount.as_tuple() == Decimal(value).as_tuple()
    assert json.loads(serialize_request(request)) == {"amount": str(Decimal(value))}
    assert request.model_dump(mode="json")["amount"] == str(Decimal(value))


@pytest.mark.parametrize(
    "value",
    [
        0.1,
        0,
        1,
        True,
        False,
        None,
        b"1.0",
        [],
        {},
        "",
        "not-a-decimal",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        float("nan"),
        float("inf"),
    ],
)
def test_request_money_rejects_coercion_and_non_finite_values(value: object) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(RequestMoney).validate_python(value)


def test_request_fields_accept_python_names_and_product_wire_aliases() -> None:
    request = AmountRequest(amount="1.0", client_reference="client-id")

    assert json.loads(serialize_request(request)) == {
        "amount": "1.0",
        "clientReference": "client-id",
    }
    assert (
        AmountRequest.model_validate({"amount": "1.0", "clientReference": "client-id"}) == request
    )


def test_core_leaves_alias_generation_to_the_product() -> None:
    class CoreRequest(RequestModel):
        snake_case: str

    class ProductRequest(CoreRequest):
        model_config = ConfigDict(alias_generator=to_camel)

    assert json.loads(serialize_request(CoreRequest(snake_case="value"))) == {"snake_case": "value"}
    assert json.loads(serialize_request(ProductRequest(snake_case="value"))) == {
        "snakeCase": "value"
    }


def test_recursive_aliases_and_omission_preserve_explicit_null_and_defaults() -> None:
    omitted = AmountRequest(amount="1.00")
    explicit = AmountRequest(amount="2.00", client_reference=None, enabled=True)
    request = NestedRequest(nested_request=omitted, children=[omitted, explicit])

    assert json.loads(serialize_request(request)) == {
        "nestedRequest": {"amount": "1.00"},
        "children": [
            {"amount": "1.00"},
            {"amount": "2.00", "clientReference": None, "enabled": True},
        ],
    }
    assert omitted.model_fields_set == {"amount"}
    assert explicit.model_fields_set == {"amount", "client_reference", "enabled"}


def test_serialization_does_not_mark_defaults_as_explicitly_supplied() -> None:
    request = NestedRequest(nested_request=AmountRequest(amount="1"))

    assert json.loads(serialize_request(request)) == {"nestedRequest": {"amount": "1"}}
    assert request.model_fields_set == {"nested_request"}


def test_unknown_request_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        AmountRequest.model_validate({"amount": "1", "futureResponseField": True})


@pytest.mark.parametrize("value", [{"amount": "1"}, [], OtherModel(), None])
def test_serializer_requires_an_explicit_request_model(value: Any) -> None:
    with pytest.raises(TypeError, match="RequestModel"):
        serialize_request(value)


def test_response_extra_fields_cannot_be_reused_as_an_outbound_body() -> None:
    response = Balance.model_validate(
        {"asset": "USDT", "balance": "1.00", "available": "1.00", "holds": "0", "future": True}
    )

    assert response.model_extra == {"future": True}
    with pytest.raises(TypeError, match="RequestModel"):
        serialize_request(response)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        AmountRequest.model_validate(response.model_dump())


@pytest.mark.parametrize(
    "wrapper", [lambda value: value, lambda value: [value], lambda value: {"x": value}]
)
def test_response_models_nested_in_any_do_not_implicitly_become_requests(wrapper: Any) -> None:
    response = Balance.model_validate(
        {"asset": "USDT", "balance": "1", "available": "1", "holds": "0", "future": True}
    )

    with pytest.raises(TypeError, match="response models"):
        serialize_request(PayloadRequest(payload=wrapper(response)))


def test_response_models_in_declared_fields_are_rejected() -> None:
    class InvalidRequest(RequestModel):
        response: Balance

    response = Balance.model_validate(
        {"asset": "USDT", "balance": "1", "available": "1", "holds": "0"}
    )
    with pytest.raises(TypeError, match="response models"):
        serialize_request(InvalidRequest(response=response))


@pytest.mark.parametrize("value", [0.1, 1, True, "invalid"])
def test_serialization_revalidates_mutated_money(value: Any) -> None:
    request = AmountRequest(amount="1")
    request.amount = value

    with pytest.raises(ValidationError):
        serialize_request(request)


@pytest.mark.parametrize("value", [0.1, 1, True, "invalid"])
def test_serialization_revalidates_constructed_money(value: object) -> None:
    request = AmountRequest.model_construct(amount=value)

    with pytest.raises(ValidationError):
        serialize_request(request)


@pytest.mark.parametrize("location", ["field", "list"])
def test_serialization_revalidates_nested_request_instances(location: str) -> None:
    child = AmountRequest(amount="1")
    request = NestedRequest(nested_request=child, children=[child])
    mutated = request.nested_request if location == "field" else request.children[0]
    mutated.amount = 0.1  # type: ignore[assignment]

    with pytest.raises(ValidationError):
        serialize_request(request)


def test_constructed_nested_request_instances_are_revalidated() -> None:
    child = AmountRequest.model_construct(amount=False)
    request = NestedRequest.model_construct(nested_request=child)

    with pytest.raises(ValidationError):
        serialize_request(request)


def test_constructed_fields_set_cannot_hide_required_request_fields() -> None:
    request = AmountRequest.model_construct(_fields_set=set(), amount="1.0000")

    assert json.loads(serialize_request(request)) == {"amount": "1.0000"}
    assert request.model_fields_set == set()


def test_required_fields_in_any_are_sent_without_marking_optional_defaults() -> None:
    child = AmountRequest.model_construct(_fields_set=set(), amount="1.0000")
    request = PayloadRequest.model_construct(_fields_set=set(), payload={"child": child})

    assert json.loads(serialize_request(request)) == {"payload": {"child": {"amount": "1.0000"}}}
    assert request.model_fields_set == child.model_fields_set == set()


@pytest.mark.parametrize(
    "wrapper", [lambda value: value, lambda value: [value], lambda value: {"x": value}]
)
@pytest.mark.parametrize("constructed", [False, True])
@pytest.mark.parametrize("value", [0.1, 1, True])
def test_request_models_hidden_in_any_are_revalidated(
    wrapper: Any, constructed: bool, value: Any
) -> None:
    if constructed:
        child = AmountRequest.model_construct(amount=value)
    else:
        child = AmountRequest(amount="1")
        child.amount = value
    request = PayloadRequest(payload=wrapper(child))

    with pytest.raises(ValidationError):
        serialize_request(request)


def test_request_models_in_any_are_normalized_without_mutation_or_lost_omission() -> None:
    child = AmountRequest.model_construct(amount="1.0000", client_reference=None)
    request = PayloadRequest(payload={"child": child})

    assert json.loads(serialize_request(request)) == {
        "payload": {"child": {"amount": "1.0000", "clientReference": None}}
    }
    assert child.amount == "1.0000"
    assert child.model_fields_set == {"amount", "client_reference"}


def test_dataclass_wrappers_do_not_implicitly_serialize_hidden_response_models() -> None:
    @dataclass
    class Wrapper:
        response: Any

    response = Balance.model_validate(
        {"asset": "USDT", "balance": "1", "available": "1", "holds": "0", "future": True}
    )

    with pytest.raises(TypeError, match="JSON values or request models"):
        serialize_request(PayloadRequest(payload=Wrapper(response)))


def test_manual_json_payloads_keep_boolean_and_finite_numbers() -> None:
    request = PayloadRequest(payload={"count": 2, "enabled": True, "factor": 0.125})

    assert json.loads(serialize_request(request)) == {
        "payload": {"count": 2, "enabled": True, "factor": 0.125}
    }


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf"), Decimal("NaN"), Decimal("Infinity")]
)
@pytest.mark.parametrize("wrapper", [lambda value: value, lambda value: {"x": [value]}])
def test_non_finite_values_anywhere_in_a_payload_are_rejected(value: object, wrapper: Any) -> None:
    with pytest.raises(ValueError, match="finite"):
        serialize_request(PayloadRequest(payload=wrapper(value)))


def test_field_serializer_cannot_produce_non_finite_json() -> None:
    class InvalidRequest(RequestModel):
        amount: int

        @field_serializer("amount")
        def serialize_amount(self, value: int) -> float:
            return float("nan")

    with pytest.raises(ValueError, match="finite"):
        serialize_request(InvalidRequest(amount=1))


@pytest.mark.parametrize("payload", [{1: "value"}, {"nested": [{False: "value"}]}, {"s": {1, 2}}])
def test_non_json_keys_and_sets_are_rejected_before_implicit_conversion(payload: object) -> None:
    with pytest.raises(TypeError):
        serialize_request(PayloadRequest(payload=payload))


def test_recursive_payloads_fail_explicitly() -> None:
    payload: list[object] = []
    payload.append(payload)

    with pytest.raises(ValueError, match="cycles"):
        serialize_request(PayloadRequest(payload=payload))


def test_shared_non_recursive_payloads_are_serialized_normally() -> None:
    child = {"text": "Привет"}

    serialized = serialize_request(PayloadRequest(payload=[child, child]))

    assert isinstance(serialized, bytes)
    assert json.loads(serialized) == {"payload": [child, child]}
    assert "Привет".encode() in serialized
