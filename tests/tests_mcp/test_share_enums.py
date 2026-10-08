# Unit test _share_enums

from skforecast_ai.mcp.server import _share_enums


def test_share_enums_writes_a_repeated_list_of_values_once():
    """
    Test that a list of allowed values written as one value and as the items
    of a list is moved to `$defs`, named after its property, and referenced
    from both places.
    """
    values = {"enum": ["mean_absolute_error", "mean_squared_error"], "type": "string"}
    schema = {
        "type": "object",
        "properties": {
            "primary_metric": {
                "anyOf": [
                    dict(values),
                    {"items": dict(values), "type": "array"},
                    {"type": "null"},
                ],
                "description": "Metric or list of metrics.",
            },
            "steps": {"type": "integer"},
        },
    }

    result = _share_enums(schema)

    assert result == {
        "type": "object",
        "properties": {
            "primary_metric": {
                "anyOf": [
                    {"$ref": "#/$defs/PrimaryMetric"},
                    {"items": {"$ref": "#/$defs/PrimaryMetric"}, "type": "array"},
                    {"type": "null"},
                ],
                "description": "Metric or list of metrics.",
            },
            "steps": {"type": "integer"},
        },
        "$defs": {"PrimaryMetric": values},
    }


def test_share_enums_shares_between_the_schema_and_its_definitions():
    """
    Test that a list of values used by the schema and by one of its `$defs`
    is written once, next to the definitions the schema already had.
    """
    values = {"enum": ["a", "b"], "type": "string"}
    schema = {
        "properties": {
            "metric": dict(values),
            "candidates": {"$ref": "#/$defs/Candidate"},
        },
        "$defs": {
            "Candidate": {
                "type": "object",
                "properties": {"metric": {"anyOf": [dict(values), {"type": "null"}]}},
            }
        },
    }

    result = _share_enums(schema)

    assert result == {
        "properties": {
            "metric": {"$ref": "#/$defs/Metric"},
            "candidates": {"$ref": "#/$defs/Candidate"},
        },
        "$defs": {
            "Candidate": {
                "type": "object",
                "properties": {
                    "metric": {
                        "anyOf": [{"$ref": "#/$defs/Metric"}, {"type": "null"}]
                    }
                },
            },
            "Metric": values,
        },
    }


def test_share_enums_does_not_reuse_the_name_of_a_definition():
    """
    Test that the shared list of values takes another name when a definition
    of the schema already has the name of its property.
    """
    values = {"enum": ["a", "b"], "type": "string"}
    schema = {
        "properties": {
            "metric": {"anyOf": [dict(values), {"items": dict(values)}]},
            "other": {"$ref": "#/$defs/Metric"},
        },
        "$defs": {"Metric": {"type": "object"}},
    }

    result = _share_enums(schema)

    assert result["$defs"] == {"Metric": {"type": "object"}, "MetricValue": values}
    assert result["properties"]["metric"] == {
        "anyOf": [
            {"$ref": "#/$defs/MetricValue"},
            {"items": {"$ref": "#/$defs/MetricValue"}},
        ]
    }


def test_share_enums_keeps_a_schema_without_repeated_values():
    """
    Test that a list of values used once, or one that carries its own
    description, stays where it is and no `$defs` is added.
    """
    schema = {
        "properties": {
            "forecaster": {"enum": ["a", "b"], "type": "string"},
            "estimator": {
                "description": "Estimator.",
                "enum": ["c", "d"],
                "type": "string",
            },
            "fallback": {
                "description": "Fallback estimator.",
                "enum": ["c", "d"],
                "type": "string",
            },
        }
    }

    result = _share_enums(schema)

    assert result == schema
    assert "$defs" not in result
