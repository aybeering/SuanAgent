"""Tiny JSON schema subset validator for repository contracts.

The project keeps runtime dependencies intentionally small, so this module
implements only the JSON Schema keywords used by the local contract schemas.
It is not a general-purpose replacement for the jsonschema package.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


VALIDATED_SCHEMA_KEYWORDS = frozenset(
    {
        "$ref",
        "additionalProperties",
        "const",
        "enum",
        "items",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "properties",
        "required",
        "type",
    }
)
ANNOTATION_SCHEMA_KEYWORDS = frozenset(
    {
        "$defs",
        "$ref_note",
        "$schema",
        "description",
        "title",
    }
)
SUPPORTED_SCHEMA_KEYWORDS = VALIDATED_SCHEMA_KEYWORDS | ANNOTATION_SCHEMA_KEYWORDS
PROPERTY_CONTAINER_KEYWORDS = frozenset({"$defs", "properties"})
SCHEMA_OBJECT_KEYWORDS = frozenset({"additionalProperties", "items"})
SCHEMA_ARRAY_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
SAFE_PROPERTY_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORTED_JSON_TYPES = frozenset(
    {
        "array",
        "boolean",
        "integer",
        "null",
        "number",
        "object",
        "string",
    }
)


def load_schema(path: Path) -> dict[str, Any]:
    """Load a JSON schema document."""
    return json.loads(path.read_text(encoding="utf-8"))


def collect_schema_keywords(schema: dict[str, Any]) -> tuple[str, ...]:
    """Return schema-node keywords without treating property names as keywords."""
    keywords: set[str] = set()

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for key, child in node.items():
            keywords.add(key)
            if key in PROPERTY_CONTAINER_KEYWORDS and isinstance(child, dict):
                for property_schema in child.values():
                    walk(property_schema)
            elif key in SCHEMA_OBJECT_KEYWORDS and isinstance(child, dict):
                walk(child)
            elif key in SCHEMA_ARRAY_KEYWORDS and isinstance(child, list):
                for item_schema in child:
                    walk(item_schema)

    walk(schema)
    return tuple(sorted(keywords))


def validate_json_file(*, payload_path: Path, schema_path: Path) -> tuple[str, ...]:
    """Validate one JSON file against one local contract schema."""
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    schema = load_schema(schema_path)
    return validate_json_payload(
        payload=payload,
        schema=schema,
        schema_dir=schema_path.parent,
    )


def validate_json_payload(
    *,
    payload: Any,
    schema: dict[str, Any] | bool,
    schema_dir: Path = Path("schemas"),
) -> tuple[str, ...]:
    """Return validation errors for the supported JSON Schema subset."""
    errors: list[str] = []
    validate_node(
        value=payload,
        schema=schema,
        path="$",
        errors=errors,
        root_schema=schema,
        schema_dir=schema_dir,
    )
    return tuple(errors)


def validate_node(
    *,
    value: Any,
    schema: dict[str, Any] | bool,
    path: str,
    errors: list[str],
    root_schema: dict[str, Any],
    schema_dir: Path,
) -> None:
    """Validate a JSON value against a schema node."""
    if isinstance(schema, bool):
        if not schema:
            errors.append(f"{path}: rejected by false schema")
        return

    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved, resolved_root_schema = resolve_ref(
            root_schema=root_schema,
            ref=ref,
            schema_dir=schema_dir,
        )
        if not isinstance(resolved, dict):
            errors.append(f"{path}: unsupported or unresolved schema ref {ref!r}")
            return
        validate_node(
            value=value,
            schema=resolved,
            path=path,
            errors=errors,
            root_schema=resolved_root_schema,
            schema_dir=schema_dir,
        )
        return

    expected_type = schema.get("type")
    unsupported_types = unsupported_schema_types(expected_type)
    if unsupported_types:
        errors.append(f"{path}: unsupported schema type {type_label(unsupported_types)}")
        return
    if expected_type is not None and not matches_type(value, expected_type):
        errors.append(f"{path}: expected {type_label(expected_type)}, got {json_type(value)}")
        return

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append(f"{path}: expected one of {enum_values}, got {value!r}")

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}, got {value!r}")

    if isinstance(value, str):
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            errors.append(f"{path}: expected string length >= {min_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                matched = re.search(pattern, value) is not None
            except re.error as exc:
                errors.append(f"{path}: invalid schema pattern {pattern!r}: {exc}")
            else:
                if not matched:
                    errors.append(f"{path}: expected string to match pattern {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: expected number >= {minimum}")

    if isinstance(value, dict):
        validate_object(
            value=value,
            schema=schema,
            path=path,
            errors=errors,
            root_schema=root_schema,
            schema_dir=schema_dir,
        )
    elif isinstance(value, list):
        validate_array(
            value=value,
            schema=schema,
            path=path,
            errors=errors,
            root_schema=root_schema,
            schema_dir=schema_dir,
        )


def validate_object(
    *,
    value: dict[str, Any],
    schema: dict[str, Any],
    path: str,
    errors: list[str],
    root_schema: dict[str, Any],
    schema_dir: Path,
) -> None:
    """Validate object-specific schema keywords."""
    required = schema.get("required", [])
    if "required" in schema and not isinstance(required, list):
        errors.append(
            f"{path}: unsupported required keyword {schema_value_label(required)}"
        )
    elif isinstance(required, list):
        for key in required:
            if not isinstance(key, str):
                errors.append(
                    f"{path}: unsupported required property name "
                    f"{schema_value_label(key)}"
                )
            elif key not in value:
                errors.append(f"{path}: missing required property {key}")

    properties = schema.get("properties", {})
    if "properties" in schema and not isinstance(properties, dict):
        errors.append(
            f"{path}: unsupported properties keyword {schema_value_label(properties)}"
        )
    elif isinstance(properties, dict):
        for key, property_schema in properties.items():
            if not isinstance(property_schema, (dict, bool)):
                errors.append(
                    f"{property_path(path, key)}: unsupported property schema "
                    f"{schema_value_label(property_schema)}"
                )
            elif key in value:
                validate_node(
                    value=value[key],
                    schema=property_schema,
                    path=property_path(path, key),
                    errors=errors,
                    root_schema=root_schema,
                    schema_dir=schema_dir,
                )

    additional_properties = schema.get("additionalProperties")
    if (
        "additionalProperties" in schema
        and not isinstance(additional_properties, (bool, dict))
    ):
        errors.append(
            f"{path}: unsupported additionalProperties keyword "
            f"{schema_value_label(additional_properties)}"
        )
    elif additional_properties is False and isinstance(properties, dict):
        allowed = set(properties)
        for key in sorted(set(value) - allowed):
            errors.append(f"{path}: unexpected property {key}")
    elif isinstance(additional_properties, dict) and isinstance(properties, dict):
        allowed = set(properties)
        for key in sorted(set(value) - allowed):
            validate_node(
                value=value[key],
                schema=additional_properties,
                path=property_path(path, key),
                errors=errors,
                root_schema=root_schema,
                schema_dir=schema_dir,
            )


def validate_array(
    *,
    value: list[Any],
    schema: dict[str, Any],
    path: str,
    errors: list[str],
    root_schema: dict[str, Any],
    schema_dir: Path,
) -> None:
    """Validate array-specific schema keywords."""
    min_items = schema.get("minItems")
    if "minItems" in schema and (
        not isinstance(min_items, int)
        or isinstance(min_items, bool)
        or min_items < 0
    ):
        errors.append(
            f"{path}: unsupported minItems keyword "
            f"{schema_value_label(min_items)}"
        )
    elif isinstance(min_items, int) and len(value) < min_items:
        errors.append(f"{path}: expected at least {min_items} items")

    item_schema = schema.get("items")
    if "items" in schema and not isinstance(item_schema, (dict, bool)):
        errors.append(
            f"{path}: unsupported items keyword {schema_value_label(item_schema)}"
        )
    elif isinstance(item_schema, (dict, bool)):
        for index, item in enumerate(value):
            validate_node(
                value=item,
                schema=item_schema,
                path=f"{path}[{index}]",
                errors=errors,
                root_schema=root_schema,
                schema_dir=schema_dir,
            )


def resolve_ref(
    *,
    root_schema: dict[str, Any],
    ref: str,
    schema_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    """Resolve local or same-directory schema JSON references."""
    if ref.startswith("#/"):
        return resolve_local_ref(root_schema=root_schema, ref=ref), root_schema
    if "#" not in ref:
        return None, root_schema
    schema_file, local_ref = ref.split("#", 1)
    schema_path = Path(schema_file)
    if schema_path.is_absolute() or ".." in schema_path.parts:
        return None, root_schema
    external_path = schema_dir / schema_path
    if not external_path.is_file():
        return None, root_schema
    try:
        external_schema = load_schema(external_path)
    except json.JSONDecodeError:
        return None, root_schema
    if not local_ref:
        return external_schema, external_schema
    return (
        resolve_local_ref(root_schema=external_schema, ref=f"#{local_ref}"),
        external_schema,
    )


def resolve_local_ref(*, root_schema: dict[str, Any], ref: str) -> Any:
    """Resolve the small local JSON pointer subset used by repository schemas."""
    if not ref.startswith("#/"):
        return None
    current: Any = root_schema
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def property_path(parent_path: str, key: str) -> str:
    """Return a readable JSONPath-like child path for one object property."""
    if SAFE_PROPERTY_NAME_PATTERN.fullmatch(key):
        return f"{parent_path}.{key}"
    return f"{parent_path}[{json.dumps(key)}]"


def matches_type(value: Any, expected_type: object) -> bool:
    """Return whether a value matches a supported JSON Schema type."""
    if isinstance(expected_type, list):
        return any(matches_type(value, item) for item in expected_type)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return False


def unsupported_schema_types(expected_type: object) -> tuple[object, ...]:
    """Return unsupported JSON Schema type labels from a schema type value."""
    if expected_type is None:
        return ()
    if isinstance(expected_type, str):
        if expected_type in SUPPORTED_JSON_TYPES:
            return ()
        return (expected_type,)
    if isinstance(expected_type, list):
        unsupported: list[object] = []
        for item in expected_type:
            if not isinstance(item, str) or item not in SUPPORTED_JSON_TYPES:
                unsupported.append(item)
        return tuple(unsupported)
    return (expected_type,)


def type_label(expected_type: object) -> str:
    """Return a readable expected type label."""
    if isinstance(expected_type, (list, tuple)):
        return " or ".join(type_label(item) for item in expected_type)
    if isinstance(expected_type, (dict, bool, int, float)):
        return json.dumps(expected_type, sort_keys=True)
    return str(expected_type)


def schema_value_label(value: object) -> str:
    """Return a stable label for malformed schema keyword values."""
    if isinstance(value, (dict, list, bool, int, float)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def json_type(value: Any) -> str:
    """Return a JSON-style type label."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__
