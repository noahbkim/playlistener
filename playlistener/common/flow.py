from django.http.request import HttpRequest
from django.utils.safestring import mark_safe
from django.urls import reverse
from django import template

from typing import Any, Callable, Optional
from dataclasses import dataclass, field


register = template.Library()


@dataclass
class Next:
    """Next step reference data."""

    title: str
    description: str
    url: str


@dataclass
class Step:
    """Represents a task for a user that can be queued."""

    name: str
    title: str
    description: str
    view: str
    theme: str

    done: Callable[[HttpRequest], bool]
    next: Optional["Step"] = field(default=False, repr=False)


class Flow:
    """A series of steps required to complete a task."""

    name: str
    steps: dict[str, Step]

    _instances: dict[str, "Flow"] = {}

    def __init__(self, name: str, steps: tuple[Step, ...]):
        """Initialize a new goal."""

        if name in Flow._instances:
            raise ValueError(f"goal with name {name} already exists")

        self.name = name
        self.steps = {}

        last = None
        for step in steps:
            if step.name in self.steps:
                raise ValueError("goal may not have steps with duplicate names")
            self.steps[step.name] = step
            if last is not None:
                last.next = step
            last = step

        Flow._instances[self.name] = self

    @staticmethod
    def get(name: str) -> Optional["Flow"]:
        """Get a goal from instances."""

        return Flow._instances.get(name)


class FlowViewMixin:
    """Provides step progress in context data."""

    step: str

    def get_context_data(self, **kwargs):
        """Inject step."""

        context_data = super().get_context_data(**kwargs)
        flow = Flow.get(self.request.GET.get("flow"))
        if flow is not None:
            step = flow.steps[self.step]
            context_data.update(flow=flow, step=step)

        return context_data


@register.simple_tag(takes_context=True, name="flow")
def _flow(context: dict[str, Any]) -> str:
    """Generate a step list with colors."""

    flow: Flow = context.get("flow")
    if flow is None:
        return ""

    current_step: Step = context.get("step")

    elements: list[str] = []
    last_step: Optional[Step] = None
    for i, (name, step) in enumerate(flow.steps.items()):
        done = step.done is None or step.done(context["request"])
        is_current = name == current_step.name

        if i > 0:
            theme = f"{last_step.theme}-{step.theme}" if done or is_current else "disabled"
            elements.append(f"""<div class="link {theme}"></div>""")

        text = "&#10003;" if done else context.get("step_state", "") if is_current else ""
        theme = step.theme if done or is_current else "disabled"
        elements.append(
            f"""<div class="step {theme}">"""
            f"""{text}"""
            f"""</div>""")
        last_step = step

    return mark_safe(f"""<div class="steps">{"".join(elements)}</div>""")


def copy_query(request: HttpRequest, *keys: str, prefix: str = "?") -> str:
    """Copy a set of keys from a query."""

    get = request.GET.copy()
    for key in request.GET.keys():
        if key not in keys:
            get.pop(key)
    return prefix + get.urlencode()


@register.simple_tag(takes_context=True, name="query")
def _query(context: dict[str, Any], *keys: str, prefix: str = "?") -> str:
    """Copy variables from the current query string."""

    return copy_query(context["request"], *keys, prefix=prefix)
