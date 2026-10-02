# Unit test Store

import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._store import Entry, Store
from skforecast_ai.mcp.models import ToolResult

from .fixtures_mcp import ID_PATTERN


def _entry(store, kind="profile", nbytes=10):
    """
    Register an entry of `kind` and return its id.
    """
    object_id = store.new_id(kind)
    store.add(
        Entry(
            id       = object_id,
            kind     = kind,
            obj      = None,
            envelope = ToolResult(id=object_id, kind=kind, summary=""),
            nbytes   = nbytes,
        )
    )

    return object_id


def test_Store_new_id_output_kind_sequence_and_token():
    """
    Test that ids are '<kind>-<sequence>-<token>', with a sequence shared by
    every kind and a token of the store.
    """
    store = Store(max_objects=10, max_bytes=1000)

    ids = [store.new_id("profile"), store.new_id("plan"), store.new_id("cv")]

    assert ids == [
        f"profile-1-{store.token}", f"plan-2-{store.token}", f"cv-3-{store.token}"
    ]
    assert all(ID_PATTERN.fullmatch(object_id) for object_id in ids)
    assert Store(max_objects=10, max_bytes=1000).token != store.token


def test_Store_add_removes_least_recently_used_beyond_max_objects():
    """
    Test that the least recently used entry is removed beyond `max_objects`,
    that reading an entry makes it recent, and that a removed id raises
    `unknown_id` saying it was removed.
    """
    store = Store(max_objects=2, max_bytes=1000)
    first = _entry(store)
    second = _entry(store)
    store.get(first, "profile_id")
    third = _entry(store)

    assert [entry.id for entry in store.entries()] == [third, first]
    assert store.removed == 1
    with pytest.raises(ServerError) as excinfo:
        store.get(second, "profile_id")
    assert excinfo.value.code == "unknown_id"
    assert excinfo.value.field == "profile_id"
    assert excinfo.value.details == {"id": second, "removed": True}
    assert str(excinfo.value) == (
        f"{second!r} was removed to keep the server within its limits "
        f"(2 objects, 0 MB): create it again."
    )


def test_Store_add_removes_entries_beyond_max_bytes_and_keeps_the_newest():
    """
    Test that entries are removed while the memory is over `max_bytes`, and
    that the newest entry is kept even when it is over the limit alone.
    """
    store = Store(max_objects=10, max_bytes=100)
    _entry(store, nbytes=60)
    second = _entry(store, nbytes=30)
    third = _entry(store, nbytes=50)

    assert [entry.id for entry in store.entries()] == [third, second]

    big = _entry(store, nbytes=500)

    assert [entry.id for entry in store.entries()] == [big]
    assert store.removed == 3


@pytest.mark.parametrize(
    "object_id, message",
    [
        ("profile-1-abcdef", "'profile-1-abcdef' comes from another run of the server: ids do not survive a restart. Create the object again."),
        ("not an id", "No object has the id 'not an id'."),
    ],
    ids=lambda dt: f"{dt}"
)
def test_Store_get_ServerError_when_id_unknown(object_id, message):
    """
    Test that an id of another server process and an id that never existed
    raise `unknown_id` with their message.
    """
    store = Store(max_objects=10, max_bytes=1000)
    _entry(store)

    with pytest.raises(ServerError) as excinfo:
        store.get(object_id, "plan_id")

    assert excinfo.value.code == "unknown_id"
    assert str(excinfo.value) == message
    assert excinfo.value.hint == "Call `list_objects` to see the ids registered now."


def test_Store_get_ServerError_when_kind_does_not_match():
    """
    Test that an id of another kind raises `invalid_argument` naming the
    kind it is and the tools that return the expected kind.
    """
    store = Store(max_objects=10, max_bytes=1000)
    cv_id = _entry(store, kind="cv")

    with pytest.raises(ServerError) as excinfo:
        store.get(cv_id, "plan_id", ("plan",))

    assert excinfo.value.code == "invalid_argument"
    assert str(excinfo.value) == (
        f"{cv_id!r} is the id of a cv, and `plan_id` takes the id of a plan "
        f"(returned by plan or refine_plan)."
    )
