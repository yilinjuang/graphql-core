from __future__ import annotations

from asyncio import sleep
from typing import Any, AsyncGenerator, NamedTuple

import pytest
from graphql.error import GraphQLError
from graphql.execution import (
    ExecutionContext,
    ExecutionResult,
    ExperimentalIncrementalExecutionResults,
    IncrementalDeferResult,
    InitialIncrementalExecutionResult,
    SubsequentIncrementalExecutionResult,
    execute,
    experimental_execute_incrementally,
)
from graphql.execution.execute import DeferredFragmentRecord
from graphql.language import DocumentNode, parse
from graphql.pyutils import Path, is_awaitable
from graphql.type import (
    GraphQLField,
    GraphQLID,
    GraphQLList,
    GraphQLNonNull,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
)

friend_type = GraphQLObjectType(
    "Friend",
    {
        "id": GraphQLField(GraphQLID),
        "name": GraphQLField(GraphQLString),
        "nonNullName": GraphQLField(GraphQLNonNull(GraphQLString)),
    },
)

hero_type = GraphQLObjectType(
    "Hero",
    {
        "id": GraphQLField(GraphQLID),
        "name": GraphQLField(GraphQLString),
        "nonNullName": GraphQLField(GraphQLNonNull(GraphQLString)),
        "friends": GraphQLField(GraphQLList(friend_type)),
    },
)

query = GraphQLObjectType("Query", {"hero": GraphQLField(hero_type)})

schema = GraphQLSchema(query)


class Friend(NamedTuple):
    id: int
    name: str


friends = [Friend(2, "Han"), Friend(3, "Leia"), Friend(4, "C-3PO")]

hero = {"id": 1, "name": "Luke", "friends": friends}


class Resolvers:
    """Various resolver functions for testing."""

    @staticmethod
    def null(_info) -> None:
        """A resolver returning a null value synchronously."""
        return

    @staticmethod
    async def null_async(_info) -> None:
        """A resolver returning a null value asynchronously."""
        return

    @staticmethod
    async def slow(_info) -> str:
        """Simulate a slow async resolver returning a value."""
        await sleep(0)
        return "slow"

    @staticmethod
    def bad(_info) -> str:
        """Simulate a bad resolver raising an error."""
        raise RuntimeError("bad")

    @staticmethod
    async def friends(_info) -> AsyncGenerator[Friend, None]:
        """A slow async generator yielding the first friend."""
        await sleep(0)
        yield friends[0]


async def complete(document: DocumentNode, root_value: Any = None) -> Any:
    result = experimental_execute_incrementally(
        schema, document, root_value or {"hero": hero}
    )
    if is_awaitable(result):
        result = await result

    if isinstance(result, ExperimentalIncrementalExecutionResults):
        results: list[Any] = [result.initial_result.formatted]
        async for patch in result.subsequent_results:
            results.append(patch.formatted)
        return results

    assert isinstance(result, ExecutionResult)
    return result.formatted


def modified_args(args: dict[str, Any], **modifications: Any) -> dict[str, Any]:
    return {**args, **modifications}


def describe_execute_defer_directive():
    def can_format_and_print_incremental_defer_result():
        result = IncrementalDeferResult()
        assert result.formatted == {"data": None}
        assert str(result) == "IncrementalDeferResult(data=None, errors=None)"

        result = IncrementalDeferResult(
            data={"hello": "world"},
            errors=[GraphQLError("msg")],
            path=["foo", 1],
            label="bar",
            extensions={"baz": 2},
        )
        assert result.formatted == {
            "data": {"hello": "world"},
            "errors": [{"message": "msg"}],
            "extensions": {"baz": 2},
            "label": "bar",
            "path": ["foo", 1],
        }
        assert (
            str(result) == "IncrementalDeferResult(data={'hello': 'world'},"
            " errors=[GraphQLError('msg')], path=['foo', 1], label='bar',"
            " extensions={'baz': 2})"
        )

    # noinspection PyTypeChecker
    def can_compare_incremental_defer_result():
        args: dict[str, Any] = {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "path": ["foo", 1],
            "label": "bar",
            "extensions": {"baz": 2},
        }
        result = IncrementalDeferResult(**args)
        assert result == IncrementalDeferResult(**args)
        assert result != IncrementalDeferResult(
            **modified_args(args, data={"hello": "foo"})
        )
        assert result != IncrementalDeferResult(**modified_args(args, errors=[]))
        assert result != IncrementalDeferResult(**modified_args(args, path=["foo", 2]))
        assert result != IncrementalDeferResult(**modified_args(args, label="baz"))
        assert result != IncrementalDeferResult(
            **modified_args(args, extensions={"baz": 1})
        )
        assert result == tuple(args.values())
        assert result == tuple(args.values())[:4]
        assert result == tuple(args.values())[:3]
        assert result == tuple(args.values())[:2]
        assert result != tuple(args.values())[:1]
        assert result != ({"hello": "world"}, [])
        assert result == args
        assert result == dict(list(args.items())[:2])
        assert result == dict(list(args.items())[:3])
        assert result != dict(list(args.items())[:2] + [("path", ["foo", 2])])
        assert result != {**args, "label": "baz"}

    def can_format_and_print_initial_incremental_execution_result():
        result = InitialIncrementalExecutionResult()
        assert result.formatted == {"data": None, "hasNext": False}
        assert (
            str(result) == "InitialIncrementalExecutionResult(data=None, errors=None)"
        )

        result = InitialIncrementalExecutionResult(has_next=True)
        assert result.formatted == {"data": None, "hasNext": True}
        assert (
            str(result)
            == "InitialIncrementalExecutionResult(data=None, errors=None, has_next)"
        )

        incremental = [IncrementalDeferResult(label="foo")]
        result = InitialIncrementalExecutionResult(
            data={"hello": "world"},
            errors=[GraphQLError("msg")],
            incremental=incremental,
            has_next=True,
            extensions={"baz": 2},
        )
        assert result.formatted == {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "incremental": [{"data": None, "label": "foo"}],
            "hasNext": True,
            "extensions": {"baz": 2},
        }
        assert (
            str(result) == "InitialIncrementalExecutionResult("
            "data={'hello': 'world'}, errors=[GraphQLError('msg')], incremental[1],"
            " has_next, extensions={'baz': 2})"
        )

    def can_compare_initial_incremental_execution_result():
        incremental = [IncrementalDeferResult(label="foo")]
        args: dict[str, Any] = {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "incremental": incremental,
            "has_next": True,
            "extensions": {"baz": 2},
        }
        result = InitialIncrementalExecutionResult(**args)
        assert result == InitialIncrementalExecutionResult(**args)
        assert result != InitialIncrementalExecutionResult(
            **modified_args(args, data={"hello": "foo"})
        )
        assert result != InitialIncrementalExecutionResult(
            **modified_args(args, errors=[])
        )
        assert result != InitialIncrementalExecutionResult(
            **modified_args(args, incremental=[])
        )
        assert result != InitialIncrementalExecutionResult(
            **modified_args(args, has_next=False)
        )
        assert result != InitialIncrementalExecutionResult(
            **modified_args(args, extensions={"baz": 1})
        )
        assert result == tuple(args.values())
        assert result == tuple(args.values())[:4]
        assert result == tuple(args.values())[:3]
        assert result == tuple(args.values())[:2]
        assert result != tuple(args.values())[:1]
        assert result != ({"hello": "foo"}, [])

        assert result == {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "incremental": incremental,
            "hasNext": True,
            "extensions": {"baz": 2},
        }
        assert result == {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "incremental": incremental,
            "hasNext": True,
        }
        assert result != {
            "data": {"hello": "world"},
            "errors": [GraphQLError("msg")],
            "incremental": incremental,
            "hasNext": False,
            "extensions": {"baz": 2},
        }

    def can_format_and_print_subsequent_incremental_execution_result():
        result = SubsequentIncrementalExecutionResult()
        assert result.formatted == {"hasNext": False}
        assert str(result) == "SubsequentIncrementalExecutionResult()"

        result = SubsequentIncrementalExecutionResult(has_next=True)
        assert result.formatted == {"hasNext": True}
        assert str(result) == "SubsequentIncrementalExecutionResult(has_next)"

        incremental = [IncrementalDeferResult(label="foo")]
        result = SubsequentIncrementalExecutionResult(
            incremental=incremental,
            has_next=True,
            extensions={"baz": 2},
        )
        assert result.formatted == {
            "incremental": [{"data": None, "label": "foo"}],
            "hasNext": True,
            "extensions": {"baz": 2},
        }
        assert (
            str(result) == "SubsequentIncrementalExecutionResult(incremental[1],"
            " has_next, extensions={'baz': 2})"
        )

    def can_compare_subsequent_incremental_execution_result():
        incremental = [IncrementalDeferResult(label="foo")]
        args: dict[str, Any] = {
            "incremental": incremental,
            "has_next": True,
            "extensions": {"baz": 2},
        }
        result = SubsequentIncrementalExecutionResult(**args)
        assert result == SubsequentIncrementalExecutionResult(**args)
        assert result != SubsequentIncrementalExecutionResult(
            **modified_args(args, incremental=[])
        )
        assert result != SubsequentIncrementalExecutionResult(
            **modified_args(args, has_next=False)
        )
        assert result != SubsequentIncrementalExecutionResult(
            **modified_args(args, extensions={"baz": 1})
        )
        assert result == tuple(args.values())
        assert result == tuple(args.values())[:2]
        assert result != tuple(args.values())[:1]
        assert result != (incremental, False)
        assert result == {
            "incremental": incremental,
            "hasNext": True,
            "extensions": {"baz": 2},
        }
        assert result == {"incremental": incremental, "hasNext": True}
        assert result != {
            "incremental": incremental,
            "hasNext": False,
            "extensions": {"baz": 2},
        }

    def can_print_deferred_fragment_record():
        context = ExecutionContext.build(schema, parse("{ hero { id } }"))
        assert isinstance(context, ExecutionContext)
        record = DeferredFragmentRecord(None, None, None, context)
        assert str(record) == "DeferredFragmentRecord(path=[])"
        record = DeferredFragmentRecord(
            "foo", Path(None, "bar", "Bar"), record, context
        )
        assert (
            str(record) == "DeferredFragmentRecord("
            "path=['bar'], label='foo', parent_context)"
        )
        record.data = {"hello": "world"}
        assert (
            str(record) == "DeferredFragmentRecord("
            "path=['bar'], label='foo', parent_context, data)"
        )

    @pytest.mark.asyncio()
    async def can_defer_fragments_containing_scalar_types():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              name
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [{"data": {"name": "Luke"}, "path": ["hero"]}],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_disable_defer_using_if_argument():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer(if: false)
              }
            }
            fragment NameFragment on Hero {
              name
            }
            """
        )
        result = await complete(document)

        assert result == {
            "data": {
                "hero": {
                    "id": "1",
                    "name": "Luke",
                },
            },
        }

    @pytest.mark.asyncio()
    async def does_not_disable_defer_with_null_if_argument():
        document = parse(
            """
            query HeroNameQuery($shouldDefer: Boolean) {
              hero {
                id
                ...NameFragment @defer(if: $shouldDefer)
              }
            }
            fragment NameFragment on Hero {
              name
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [{"data": {"name": "Luke"}, "path": ["hero"]}],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def throws_an_error_for_defer_directive_with_non_string_label():
        document = parse(
            """
            query Deferred {
              ... @defer(label: 42) { hero { id } }
            }
            """
        )
        result = await complete(document)

        assert result == {
            "data": None,
            "errors": [
                {
                    "locations": [{"column": 33, "line": 3}],
                    "message": "Argument 'label' has invalid value 42.",
                }
            ],
        }

    @pytest.mark.asyncio()
    async def can_defer_fragments_on_the_top_level_query_field():
        document = parse(
            """
            query HeroNameQuery {
              ...QueryFragment @defer(label: "DeferQuery")
            }
            fragment QueryFragment on Query {
              hero {
                id
              }
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {}, "hasNext": True},
            {
                "incremental": [
                    {"data": {"hero": {"id": "1"}}, "path": [], "label": "DeferQuery"}
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_defer_fragments_with_errors_on_the_top_level_query_field():
        document = parse(
            """
            query HeroNameQuery {
              ...QueryFragment @defer(label: "DeferQuery")
            }
            fragment QueryFragment on Query {
              hero {
                name
              }
            }
            """
        )
        result = await complete(document, {"hero": {**hero, "name": Resolvers.bad}})

        assert result == [
            {"data": {}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"hero": {"name": None}},
                        "errors": [
                            {
                                "message": "bad",
                                "locations": [{"column": 17, "line": 7}],
                                "path": ["hero", "name"],
                            }
                        ],
                        "path": [],
                        "label": "DeferQuery",
                    }
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_defer_a_fragment_within_an_already_deferred_fragment():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                ...TopFragment @defer(label: "DeferTop")
              }
            }
            fragment TopFragment on Hero {
              id
              ...NestedFragment @defer(label: "DeferNested")
            }
            fragment NestedFragment on Hero {
              friends {
                name
              }
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {
                            "friends": [
                                {"name": "Han"},
                                {"name": "Leia"},
                                {"name": "C-3PO"},
                            ]
                        },
                        "path": ["hero"],
                        "label": "DeferNested",
                    },
                    {
                        "data": {"id": "1"},
                        "path": ["hero"],
                        "label": "DeferTop",
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_defer_a_fragment_that_is_also_not_deferred_with_deferred_first():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                ...TopFragment @defer(label: "DeferTop")
                ...TopFragment
              }
            }
            fragment TopFragment on Hero {
              name
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"name": "Luke"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": "Luke"},
                        "path": ["hero"],
                        "label": "DeferTop",
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_defer_a_fragment_that_is_also_not_deferred_with_non_deferred_first():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                ...TopFragment
                ...TopFragment @defer(label: "DeferTop")
              }
            }
            fragment TopFragment on Hero {
              name
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"name": "Luke"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": "Luke"},
                        "path": ["hero"],
                        "label": "DeferTop",
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def can_defer_an_inline_fragment():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ... on Hero @defer(label: "InlineDeferred") {
                  name
                }
              }
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": "Luke"},
                        "path": ["hero"],
                        "label": "InlineDeferred",
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def handles_errors_thrown_in_deferred_fragments():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              name
            }
            """
        )
        result = await complete(document, {"hero": {**hero, "name": Resolvers.bad}})

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": None},
                        "path": ["hero"],
                        "errors": [
                            {
                                "message": "bad",
                                "locations": [{"line": 9, "column": 15}],
                                "path": ["hero", "name"],
                            }
                        ],
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def handles_non_nullable_errors_thrown_in_deferred_fragments():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              nonNullName
            }
            """
        )
        result = await complete(
            document, {"hero": {**hero, "nonNullName": Resolvers.null}}
        )

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": None,
                        "path": ["hero"],
                        "errors": [
                            {
                                "message": "Cannot return null for non-nullable field"
                                " Hero.nonNullName.",
                                "locations": [{"line": 9, "column": 15}],
                                "path": ["hero", "nonNullName"],
                            }
                        ],
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def handles_non_nullable_errors_thrown_outside_deferred_fragments():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                nonNullName
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              id
            }
            """
        )
        result = await complete(
            document, {"hero": {**hero, "nonNullName": Resolvers.null}}
        )

        assert result == {
            "data": {"hero": None},
            "errors": [
                {
                    "message": "Cannot return null for non-nullable field"
                    " Hero.nonNullName.",
                    "locations": [{"line": 4, "column": 17}],
                    "path": ["hero", "nonNullName"],
                }
            ],
        }

    @pytest.mark.asyncio()
    async def handles_async_non_nullable_errors_thrown_in_deferred_fragments():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              nonNullName
            }
            """
        )
        result = await complete(
            document, {"hero": {**hero, "nonNullName": Resolvers.null_async}}
        )

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": None,
                        "path": ["hero"],
                        "errors": [
                            {
                                "message": "Cannot return null for non-nullable field"
                                " Hero.nonNullName.",
                                "locations": [{"line": 9, "column": 15}],
                                "path": ["hero", "nonNullName"],
                            }
                        ],
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def returns_payloads_in_correct_order():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              name
              friends {
                ...NestedFragment @defer
              }
            }
            fragment NestedFragment on Friend {
              name
            }
            """
        )
        result = await complete(document, {"hero": {**hero, "name": Resolvers.slow}})

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": "slow", "friends": [{}, {}, {}]},
                        "path": ["hero"],
                    }
                ],
                "hasNext": True,
            },
            {
                "incremental": [
                    {
                        "data": {"name": "Han"},
                        "path": ["hero", "friends", 0],
                    },
                    {
                        "data": {"name": "Leia"},
                        "path": ["hero", "friends", 1],
                    },
                    {
                        "data": {"name": "C-3PO"},
                        "path": ["hero", "friends", 2],
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def returns_payloads_from_synchronous_data_in_correct_order():
        document = parse(
            """
            query HeroNameQuery {
              hero {
                id
                ...NameFragment @defer
              }
            }
            fragment NameFragment on Hero {
              name
              friends {
                ...NestedFragment @defer
              }
            }
            fragment NestedFragment on Friend {
              name
            }
            """
        )
        result = await complete(document)

        assert result == [
            {"data": {"hero": {"id": "1"}}, "hasNext": True},
            {
                "incremental": [
                    {
                        "data": {"name": "Luke", "friends": [{}, {}, {}]},
                        "path": ["hero"],
                    },
                ],
                "hasNext": True,
            },
            {
                "incremental": [
                    {
                        "data": {"name": "Han"},
                        "path": ["hero", "friends", 0],
                    },
                    {
                        "data": {"name": "Leia"},
                        "path": ["hero", "friends", 1],
                    },
                    {
                        "data": {"name": "C-3PO"},
                        "path": ["hero", "friends", 2],
                    },
                ],
                "hasNext": False,
            },
        ]

    @pytest.mark.asyncio()
    async def filters_deferred_payloads_when_list_item_from_async_iterable_nulled():
        document = parse(
            """
            query {
              hero {
                friends {
                  nonNullName
                  ...NameFragment @defer
                }
              }
            }
            fragment NameFragment on Friend {
              name
            }
            """
        )

        result = await complete(
            document, {"hero": {**hero, "friends": Resolvers.friends}}
        )

        assert result == {
            "data": {"hero": {"friends": [None]}},
            "errors": [
                {
                    "message": "Cannot return null for non-nullable field"
                    " Friend.nonNullName.",
                    "locations": [{"line": 5, "column": 19}],
                    "path": ["hero", "friends", 0, "nonNullName"],
                }
            ],
        }

    @pytest.mark.asyncio()
    async def original_execute_function_throws_error_if_deferred_and_all_is_sync():
        document = parse(
            """
            query Deferred {
              ... @defer { hero { id } }
            }
            """
        )

        with pytest.raises(GraphQLError) as exc_info:
            await execute(schema, document, {})  # type: ignore

        assert str(exc_info.value) == (
            "Executing this GraphQL operation would unexpectedly produce"
            " multiple payloads (due to @defer or @stream directive)"
        )

    @pytest.mark.asyncio()
    async def original_execute_function_throws_error_if_deferred_and_not_all_is_sync():
        document = parse(
            """
            query Deferred {
              hero { name }
              ... @defer { hero { id } }
            }
            """
        )

        root_value = {"hero": {**hero, "name": Resolvers.slow}}
        with pytest.raises(GraphQLError) as exc_info:
            await execute(schema, document, root_value)  # type: ignore

        assert str(exc_info.value) == (
            "Executing this GraphQL operation would unexpectedly produce"
            " multiple payloads (due to @defer or @stream directive)"
        )
