from __future__ import annotations

import ast
from collections import deque
from functools import cache, singledispatch
from typing import Any, Dict, Iterator, List, Optional, Tuple, Type, cast


def negate(node: ast.expr) -> ast.UnaryOp:
    """Negate the given `node`."""
    return ast.UnaryOp(op=ast.Not(), operand=node)


def apply_condition(condition: bool, node: ast.expr) -> ast.expr:
    """Negate the node if `condition` is a falsy value."""
    if condition:
        return node
    else:
        return negate(node)


_OPERATOR_MAP = {
    ast.Eq: True,
    ast.In: True,
    ast.Is: True,
    ast.NotEq: False,
    ast.NotIn: False,
    ast.IsNot: False,
}


def is_truthy(op: ast.cmpop) -> Optional[bool]:
    """Return `True` for truth-based comparison
    operators (e.g `==`, `is`, `in`), `False` for
    falsity-based operators (e.g `!=`, `is not`, `not in`)
    and `None` for others."""
    return _OPERATOR_MAP.get(type(op))


@cache
def _is_comprehension(node_type: Type[ast.AST]) -> bool:
    return issubclass(
        node_type, (ast.SetComp, ast.ListComp, ast.DictComp, ast.GeneratorExp)
    )


def is_comprehension(node: ast.AST) -> bool:
    """Check if the node is a comprehension"""
    return _is_comprehension(type(node))  # type: ignore


@cache
def _is_contextful(node_type: Type[ast.AST]) -> bool:
    return issubclass(
        node_type,
        (
            ast.Module,
            ast.ClassDef,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.Lambda,
        ),
    ) or _is_comprehension(
        node_type  # type: ignore
    )


def is_contextful(node: ast.AST) -> bool:
    """Check if the node is a context starter (e.g
    a function definition)."""
    return _is_contextful(type(node))  # type: ignore


def pascal_to_snake(name: str) -> str:
    """Convert a name written in pascal case notation to
    snake case."""

    new_string = str()
    for is_tail, part in enumerate(name):
        if is_tail and part.isupper():
            new_string += "_"
        new_string += part

    return new_string.lower()


def find_closest(node: ast.AST, *targets: ast.AST) -> ast.AST:
    """Find the closest node against given sequence
    of targets (absolute distance from starting points)."""
    assert len(targets) >= 0

    def closest(target):
        return (
            abs(target.lineno - node.lineno),
            abs(target.col_offset - node.col_offset),
        )

    sorted_targets = sorted(targets, key=closest)
    return sorted_targets[0]


_POSITIONAL_ATTRIBUTES = (
    "lineno",
    "col_offset",
    "end_lineno",
    "end_col_offset",
)
_POSITIONAL_ATTRIBUTES_SET = frozenset(_POSITIONAL_ATTRIBUTES)


@cache  # type: ignore
def has_positions(node_type: Type[ast.AST]) -> bool:
    """Return `True` if the given `node_type` tracks
    source positions."""
    return _POSITIONAL_ATTRIBUTES_SET.issubset(node_type._attributes)


def position_for(node: ast.AST) -> Tuple[int, int, int, int]:
    """Return a 4-item tuple of positions for the given node."""
    positions = tuple(
        getattr(node, attribute) for attribute in _POSITIONAL_ATTRIBUTES
    )
    return cast(Tuple[int, int, int, int], positions)


def unpack_lhs(node: ast.AST) -> Iterator[str]:
    """Unpack assignment targets to individual identifiers"""
    if isinstance(node, (ast.List, ast.Tuple)):
        for element in node.elts:
            yield from unpack_lhs(element)
    else:
        yield ast.unparse(node)


def walk_scope(node: ast.AST) -> Iterator[ast.AST]:
    """Like regular ast.walk() but only walks within the
    current scope."""
    assert hasattr(node, "body")

    todo = deque(_walker(node))
    while todo:
        node = todo.popleft()
        todo.extend(_walker(node, top_level=True))
        yield node


@singledispatch
def _walker(node: ast.AST, top_level: bool = False) -> Iterator[ast.AST]:
    yield from ast.iter_child_nodes(node)


@_walker.register(ast.Lambda)
@_walker.register(ast.FunctionDef)
@_walker.register(ast.AsyncFunctionDef)
def _walk_func(node: ast.AST, top_level: bool = False) -> Iterator[ast.AST]:
    if top_level:
        yield from node.decorator_list
        yield from node.args.defaults
        yield from node.args.kw_defaults
        yield from _walk_optional(node.returns)
    else:
        yield from _walk_args(node.args)
        yield from node.body


@_walker.register(ast.ClassDef)
def _walk_class(node: ast.AST, top_level: bool = False) -> Iterator[ast.AST]:
    if top_level:
        yield from node.decorator_list
        yield from node.bases
        yield from node.keywords
    else:
        yield from node.body


def _walk_args(node: ast.arguments) -> List[ast.arg]:
    args = node.posonlyargs + node.args + node.kwonlyargs
    if node.vararg:
        args.append(node.vararg)
    if node.kwarg:
        args.append(node.kwarg)
    return args


def _walk_optional(node: Optional[ast.AST]) -> Iterator[ast.AST]:
    if node:
        yield node


class Singleton:
    def __init_subclass__(cls) -> None:
        cls._instances: Dict[Tuple[Any, ...], Singleton] = {}  # type: ignore

    def __new__(cls, *args: Any) -> Singleton:
        if not cls._instances.get(args):
            cls._instances[args] = super().__new__(cls)
        return cls._instances[args]
