from __future__ import annotations

import collections
import inspect
from typing import Any, Iterator

from twisted.python.modules import PythonAttribute, PythonModule, getModule

from automat import MethodicalMachine

from ._typified import TypifiedMachine


def isOriginalLocation(attr: PythonAttribute | PythonModule) -> bool:
    """
    Attempt to discover if this appearance of a PythonAttribute
    representing a class refers to the module where that class was
    defined.
    """
    sourceModule = inspect.getmodule(attr.load())
    if sourceModule is None:
        return False

    currentModule = attr
    while not isinstance(currentModule, PythonModule):
        currentModule = currentModule.onObject

    return currentModule.name == sourceModule.__name__


def findMachinesViaWrapper(
    within: PythonModule | PythonAttribute,
) -> Iterator[tuple[str, MethodicalMachine | TypifiedMachine]]:
    """
    Recursively yield L{MethodicalMachine}s and their FQPNs within a
    L{PythonModule} or a L{twisted.python.modules.PythonAttribute}
    wrapper object.

    Note that L{PythonModule}s may refer to packages, as well.

    The discovery heuristic considers L{MethodicalMachine} instances
    that are module-level attributes or class-level attributes
    accessible from module scope.  Machines inside nested classes will
    be discovered, but those returned from functions or methods will not be.

    @type within: L{PythonModule} or L{twisted.python.modules.PythonAttribute}
    @param within: Where to start the search.

    @return: a generator which yields FQPN, L{MethodicalMachine} pairs.
    """
    queue = collections.deque([within])
    visited: set[
        PythonModule | PythonAttribute | MethodicalMachine | TypifiedMachine | type[Any]
    ] = set()

    while queue:
        attr = queue.pop()
        value = attr.load()
        print("inspecting", value)

        if (
            isinstance(value, MethodicalMachine) or isinstance(value, TypifiedMachine)
        ) and value not in visited:
            visited.add(value)
            yield attr.name, value
        elif (
            inspect.isclass(value) and isOriginalLocation(attr) and value not in visited
        ):
            visited.add(value)
            queue.extendleft(attr.iterAttributes())
        elif isinstance(attr, PythonModule) and value not in visited:
            visited.add(value)
            queue.extendleft(attr.iterAttributes())
            queue.extendleft(attr.iterModules())


class InvalidFQPN(Exception):
    """
    The given FQPN was not a dot-separated list of Python objects.
    """


class NoModule(InvalidFQPN):
    """
    A prefix of the FQPN was not an importable module or package.
    """


class NoObject(InvalidFQPN):
    """
    A suffix of the FQPN was not an accessible object
    """


def wrapFQPN(fqpn: str) -> PythonModule | PythonAttribute:
    """
    Given an FQPN, retrieve the object via the global Python module
    namespace and wrap it with a L{PythonModule} or a
    L{twisted.python.modules.PythonAttribute}.
    """
    # largely cribbed from t.p.reflect.namedAny

    if not fqpn:
        raise InvalidFQPN("FQPN was empty")

    components = collections.deque(fqpn.split("."))

    if "" in components:
        raise InvalidFQPN(
            "name must be a string giving a '.'-separated list of Python "
            "identifiers, not %r" % (fqpn,)
        )

    component = components.popleft()
    try:
        module = getModule(component)
    except KeyError:
        raise NoModule(component)

    # find the bottom-most module
    while components:
        component = components.popleft()
        try:
            module = module[component]
        except KeyError:
            components.appendleft(component)
            break
        else:
            module.load()
    else:
        return module

    # find the bottom-most attribute
    attribute = module
    for component in components:
        try:
            attribute = next(
                child
                for child in attribute.iterAttributes()
                if child.name.rsplit(".", 1)[-1] == component
            )
        except StopIteration:
            raise NoObject("{}.{}".format(attribute.name, component))

    return attribute


def findMachines(
    fqpn: str,
) -> Iterator[tuple[str, MethodicalMachine | TypifiedMachine]]:
    """
    Recursively yield L{MethodicalMachine}s and their FQPNs in and
    under the a Python object specified by an FQPN.

    The discovery heuristic considers L{MethodicalMachine} instances
    that are module-level attributes or class-level attributes
    accessible from module scope.  Machines inside nested classes will
    be discovered, but those returned from functions or methods will not be.

    @type within: an FQPN
    @param within: Where to start the search.

    @return: a generator which yields FQPN, L{MethodicalMachine} pairs.
    """
    return findMachinesViaWrapper(wrapFQPN(fqpn))
