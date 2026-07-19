from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True, slots=True)
class ActionContext:
    type: str
    value: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Action:
    id: str
    label: str
    group: str = "General"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ActionGroup:
    id: str
    label: str
    actions: tuple[Action, ...]


class ActionProvider(Protocol):
    def actions_for(self, context: ActionContext) -> list[Action]:
        ...


class ActionDispatcher(QObject):
    action_requested = Signal(object, object)

    def dispatch(self, context: ActionContext, action: Action) -> None:
        self.action_requested.emit(context, action)


class ActionRegistry:
    def __init__(self, providers: Iterable[ActionProvider] | None = None) -> None:
        self._providers: list[ActionProvider] = list(providers or [])

    def register(self, provider: ActionProvider) -> None:
        self._providers.append(provider)

    def actions_for(self, context: ActionContext) -> list[Action]:
        actions: list[Action] = []
        for provider in self._providers:
            actions.extend(provider.actions_for(context))
        return actions

    def groups_for(self, context: ActionContext) -> list[ActionGroup]:
        grouped: dict[str, list[Action]] = {}
        for action in self.actions_for(context):
            grouped.setdefault(action.group, []).append(action)
        return [
            ActionGroup(id=self._group_id(label), label=label, actions=tuple(actions))
            for label, actions in grouped.items()
            if actions
        ]

    @staticmethod
    def _group_id(label: str) -> str:
        return label.lower().replace(" ", "-")


class IPActionProvider:
    def actions_for(self, context: ActionContext) -> list[Action]:
        if context.type != "ip":
            return []
        return [
            Action("ip.ssh", "SSH", "Connect"),
            Action("ip.telnet", "Telnet", "Connect"),
            Action("ip.ping", "Ping", "Diagnostics"),
            Action("ip.traceroute", "Traceroute", "Diagnostics"),
            Action("ip.copy", "Copy", "Clipboard"),
        ]


class URLActionProvider:
    def actions_for(self, context: ActionContext) -> list[Action]:
        if context.type != "url":
            return []
        return [
            Action("url.open", "Open Browser", "Open"),
            Action("url.copy", "Copy", "Clipboard"),
        ]


class EmailActionProvider:
    def actions_for(self, context: ActionContext) -> list[Action]:
        if context.type != "email":
            return []
        return [
            Action("email.mail", "Mail", "Open"),
            Action("email.copy", "Copy", "Clipboard"),
        ]


class InterfaceActionProvider:
    def actions_for(self, context: ActionContext) -> list[Action]:
        if context.type != "interface":
            return []
        return [
            Action("interface.inspect", "Inspect", "Network"),
            Action("interface.copy", "Copy", "Clipboard"),
        ]


class SelectionActionProvider:
    def actions_for(self, context: ActionContext) -> list[Action]:
        if context.type != "selection":
            return []
        return [
            Action("selection.copy", "Copy", "Clipboard"),
            Action("selection.copy_one_line", "Copy as One Line", "Clipboard"),
            Action("selection.save_to_file", "Save To File", "Export"),
        ]


def default_action_registry() -> ActionRegistry:
    return ActionRegistry(
        [
            IPActionProvider(),
            URLActionProvider(),
            EmailActionProvider(),
            InterfaceActionProvider(),
            SelectionActionProvider(),
        ]
    )
