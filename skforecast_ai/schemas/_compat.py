################################################################################
#                          Schema compatibility                                #
#                                                                              #
# Loading objects pickled by an earlier version of the package                 #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Any
from pydantic_core import PydanticUndefined


class PickleDefaultsMixin:
    """
    Give an object unpickled from an earlier version the fields that version
    did not have.

    pickle restores the attributes an object had when it was saved, without
    running the validation that fills in the defaults: a profile, a plan or
    a result saved before a field was added came back without it, and the
    first method that read the field raised `AttributeError` (after running
    the backtest, in the case of `backtest()`). Each missing field gets its
    default; a field without one is left missing, as before.

    It must come before `BaseModel` in the bases of a model.
    """

    def __setstate__(self, state: dict[Any, Any]) -> None:
        super().__setstate__(state)
        for name, field in type(self).model_fields.items():
            if name in self.__dict__:
                continue
            default = field.get_default(call_default_factory=True)
            if default is not PydanticUndefined:
                self.__dict__[name] = default
