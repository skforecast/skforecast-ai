# Unit test _drop_titles

from skforecast_ai.mcp.server import _drop_titles


def test_drop_titles_removes_generated_titles_at_every_level():
    """
    Test that the `title` texts are removed from the schema, its properties,
    the items of its lists and its `$defs`, and nothing else changes.
    """
    schema = {
        "title": "Arguments",
        "type": "object",
        "properties": {
            "metric": {
                "title": "Metric",
                "anyOf": [
                    {"title": "One", "type": "string"},
                    {"type": "null"},
                ],
                "description": "Metric of the plan.",
            },
            "overrides": {"$ref": "#/$defs/Overrides"},
        },
        "$defs": {
            "Overrides": {
                "title": "Overrides",
                "type": "object",
                "properties": {"steps": {"title": "Steps", "type": "integer"}},
            }
        },
        "required": ["metric"],
    }

    result = _drop_titles(schema)

    assert result == {
        "type": "object",
        "properties": {
            "metric": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "description": "Metric of the plan.",
            },
            "overrides": {"$ref": "#/$defs/Overrides"},
        },
        "$defs": {
            "Overrides": {
                "type": "object",
                "properties": {"steps": {"type": "integer"}},
            }
        },
        "required": ["metric"],
    }


def test_drop_titles_keeps_a_property_named_title():
    """
    Test that a property named `title` is kept with its schema, and that an
    allowed value or a required name equal to `title` is kept too.
    """
    schema = {
        "title": "Arguments",
        "properties": {
            "title": {"title": "Title", "type": "string", "enum": ["title"]}
        },
        "required": ["title"],
    }

    result = _drop_titles(schema)

    assert result == {
        "properties": {"title": {"type": "string", "enum": ["title"]}},
        "required": ["title"],
    }


def test_drop_titles_does_not_change_its_input():
    """
    Test that the schema given is not modified.
    """
    schema = {"title": "Arguments", "properties": {"a": {"title": "A"}}}

    _drop_titles(schema)

    assert schema == {"title": "Arguments", "properties": {"a": {"title": "A"}}}
