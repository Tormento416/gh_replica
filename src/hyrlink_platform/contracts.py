"""Versioned, language-neutral module contract with fail-closed validation."""

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

CORE_VERSION = "0.1.0"
IDENTIFIER = r"^[a-z][a-z0-9-]{1,63}$"
VERSION = r"^\d+\.\d+\.\d+$"
MODULE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:hyrlink:module:v1",
    "type": "object",
    "additionalProperties": False,
    "required": ["schemaVersion", "id", "version", "coreVersion", "requires", "agent", "tools"],
    "properties": {
        "schemaVersion": {"const": 1},
        "id": {"type": "string", "pattern": IDENTIFIER},
        "version": {"type": "string", "pattern": VERSION},
        "coreVersion": {"type": "string", "pattern": VERSION},
        "requires": {"type": "array", "uniqueItems": True, "items": {"type": "string", "pattern": IDENTIFIER}},
        "agent": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "maxToolCalls", "intents"],
            "properties": {
                "id": {"type": "string", "pattern": IDENTIFIER},
                "maxToolCalls": {"type": "integer", "minimum": 1, "maximum": 20},
                "intents": {"type": "object", "minProperties": 1,
                            "propertyNames": {"pattern": IDENTIFIER},
                            "additionalProperties": {"type": "string", "pattern": IDENTIFIER}},
            },
        },
        "tools": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "permission", "risk", "inputSchema", "outputSchema"],
                "properties": {
                    "name": {"type": "string", "pattern": IDENTIFIER},
                    "permission": {"type": "string", "pattern": r"^[a-z][a-z0-9-]+:[a-z][a-z0-9-]+$"},
                    "risk": {"enum": ["read", "controlled"]},
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            },
        },
    },
}


class PlatformError(ValueError):
    """Safe error code; do not include request payloads or credentials."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlatformError("duplicate_json_key")
        result[key] = value
    return result


def parse_json(data):
    """Reject duplicate keys and non-JSON numeric constants."""
    try:
        return json.loads(data, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(PlatformError("invalid_json")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PlatformError("invalid_json") from exc


def validate_instance(value, schema):
    if next(Draft202012Validator(schema).iter_errors(value), None) is not None:
        raise PlatformError("schema_validation_failed")


def validate_module(module):
    validate_instance(module, MODULE_SCHEMA)
    if module["coreVersion"] != CORE_VERSION:
        raise PlatformError("incompatible_core_version")
    names = [tool["name"] for tool in module["tools"]]
    if len(set(names)) != len(names):
        raise PlatformError("duplicate_tool")
    if not set(module["agent"]["intents"].values()).issubset(names):
        raise PlatformError("unknown_agent_tool")
    if module["id"] in module["requires"]:
        raise PlatformError("dependency_cycle")
    for tool in module["tools"]:
        if not tool["permission"].startswith(module["id"] + ":"):
            raise PlatformError("permission_namespace_mismatch")
        for key in ("inputSchema", "outputSchema"):
            schema = tool[key]
            # No remote references or unconstrained data contracts in v1.
            def inspect(node):
                if isinstance(node, dict):
                    if "$ref" in node or "$dynamicRef" in node:
                        raise PlatformError("schema_references_not_supported")
                    for child in node.values():
                        inspect(child)
                elif isinstance(node, list):
                    for child in node:
                        inspect(child)
            inspect(schema)
            Draft202012Validator.check_schema(schema)
            if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
                raise PlatformError("object_schema_must_be_closed")
    return module


def load_catalog(directory):
    catalog = {}
    for path in sorted(Path(directory).glob("*/module.json")):
        module = validate_module(parse_json(path.read_bytes()))
        if module["id"] in catalog:
            raise PlatformError("duplicate_module")
        catalog[module["id"]] = module
    return catalog


def resolve(catalog, selected):
    """Dependencies must be explicitly selected; never silently add modules."""
    if len(selected) != len(set(selected)):
        raise PlatformError("duplicate_selection")
    selected = set(selected)
    if selected - catalog.keys():
        raise PlatformError("unknown_module")
    ordered, visiting, visited = [], set(), set()

    def visit(name):
        if name in visiting:
            raise PlatformError("dependency_cycle")
        if name in visited:
            return
        visiting.add(name)
        for dependency in sorted(catalog[name]["requires"]):
            if dependency not in selected:
                raise PlatformError("missing_required_module")
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in sorted(selected):
        visit(name)
    return ordered
