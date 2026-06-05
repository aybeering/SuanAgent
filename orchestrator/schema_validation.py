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


def load_schema(path: Path) -> dict[str, Any]:
    """Load a JSON schema document."""
    return json.loads(path.read_text(encoding="utf-8"))


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
    schema: dict[str, Any],
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
    schema: dict[str, Any],
    path: str,
    errors: list[str],
    root_schema: dict[str, Any],
    schema_dir: Path,
) -> None:
    """Validate a JSON value against a schema node."""
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
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                errors.append(f"{path}: missing required property {key}")

    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        for key, property_schema in properties.items():
            if key in value and isinstance(property_schema, dict):
                validate_node(
                    value=value[key],
                    schema=property_schema,
                    path=f"{path}.{key}",
                    errors=errors,
                    root_schema=root_schema,
                    schema_dir=schema_dir,
                )

    if schema.get("additionalProperties") is False and isinstance(properties, dict):
        allowed = set(properties)
        for key in sorted(set(value) - allowed):
            errors.append(f"{path}: unexpected property {key}")


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
    if isinstance(min_items, int) and len(value) < min_items:
        errors.append(f"{path}: expected at least {min_items} items")

    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
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
    return True


def type_label(expected_type: object) -> str:
    """Return a readable expected type label."""
    if isinstance(expected_type, list):
        return " or ".join(str(item) for item in expected_type)
    return str(expected_type)


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
