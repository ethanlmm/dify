from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Union

from typing_extensions import deprecated

from core.app.segments import Variable, factory
from core.file.file_obj import FileVar
from core.workflow.entities.node_entities import SystemVariable
import json
VariableValue = Union[str, int, float, dict, list, FileVar]


SYSTEM_VARIABLE_NODE_ID = 'sys'
ENVIRONMENT_VARIABLE_NODE_ID = 'env'


class VariablePool:
    def __init__(
        self,
        system_variables: Mapping[SystemVariable, Any],
        user_inputs: Mapping[str, Any],
        environment_variables: Sequence[Variable],
    ) -> None:
        # system variables
        # for example:
        # {
        #     'query': 'abc',
        #     'files': []
        # }

        # Varaible dictionary is a dictionary for looking up variables by their selector.
        # The first element of the selector is the node id, it's the first-level key in the dictionary.
        # Other elements of the selector are the keys in the second-level dictionary. To get the key, we hash the
        # elements of the selector except the first one.
        self._variable_dictionary: dict[str, dict[int, Variable]] = defaultdict(dict)

        # TODO: This user inputs is not used for pool.
        self.user_inputs = user_inputs

        # Add system variables to the variable pool
        self.system_variables = system_variables
        for key, value in system_variables.items():
            self.add((SYSTEM_VARIABLE_NODE_ID, key.value), value)

        # Add environment variables to the variable pool
        for var in environment_variables or []:
            self.add((ENVIRONMENT_VARIABLE_NODE_ID, var.name), var)

    def add(self, selector: Sequence[str], value: Any, /) -> None:
        """
        Adds a variable to the variable pool.

        Args:
            selector (Sequence[str]): The selector for the variable.
            value (VariableValue): The value of the variable.

        Raises:
            ValueError: If the selector is invalid.

        Returns:
            None
        """
        if len(selector) < 2:
            raise ValueError('Invalid selector')

        if value is None:
            return

        if not isinstance(value, Variable):
            v = factory.build_anonymous_variable(value)
        else:
            v = value

        hash_key = hash(tuple(selector[1:]))
        if hash_key==hash(tuple(['files'])):
            self.add((SYSTEM_VARIABLE_NODE_ID,'files_str'),json.dumps([v.to_dict()for v in value]))
        if hash_key==hash(tuple(['files_extend'])):
            hash_key=hash(tuple(['files']))
            self._variable_dictionary[selector[0]][hash_key].extend(value)
            self.add((SYSTEM_VARIABLE_NODE_ID, 'files_str'),json.dumps([v.to_dict() for v in self._variable_dictionary[SYSTEM_VARIABLE_NODE_ID][hash_key]]))
            return
        self._variable_dictionary[selector[0]][hash_key] = v

    def get(self, selector: Sequence[str], /) -> Variable | None:
        """
        Retrieves the value from the variable pool based on the given selector.

        Args:
            selector (Sequence[str]): The selector used to identify the variable.

        Returns:
            Any: The value associated with the given selector.

        Raises:
            ValueError: If the selector is invalid.
        """
        if len(selector) < 2:
            raise ValueError('Invalid selector')
        hash_key = hash(tuple(selector[1:]))
        value = self._variable_dictionary[selector[0]].get(hash_key)

        return value

    @deprecated('This method is deprecated, use `get` instead.')
    def get_any(self, selector: Sequence[str], /) -> Any | None:
        """
        Retrieves the value from the variable pool based on the given selector.

        Args:
            selector (Sequence[str]): The selector used to identify the variable.

        Returns:
            Any: The value associated with the given selector.

        Raises:
            ValueError: If the selector is invalid.
        """
        if len(selector) < 2:
            raise ValueError('Invalid selector')
        hash_key = hash(tuple(selector[1:]))
        value = self._variable_dictionary[selector[0]].get(hash_key)
        return value.to_object() if value else None

    def remove(self, selector: Sequence[str], /):
        """
        Remove variables from the variable pool based on the given selector.

        Args:
            selector (Sequence[str]): A sequence of strings representing the selector.

        Returns:
            None
        """
        if not selector:
            return
        if len(selector) == 1:
            self._variable_dictionary[selector[0]] = {}
            return
        hash_key = hash(tuple(selector[1:]))
        self._variable_dictionary[selector[0]].pop(hash_key, None)
