"""Policy wrapper that repairs a gpt-oss/Groq tool-calling quirk.

gpt-oss sometimes leaks the closing brace of the tool call's JSON into the
`code` argument of `submit`, so the submitted program ends in a stray `}` line
and fails with a SyntaxError. This wrapper strips that line before the monitor
and scorer see the submission.
"""

from inspect_ai.agent import Agent, AgentState
from inspect_ai.model import ChatMessageAssistant
from inspect_ai.tool import Tool

from control_arena._control_agent import ControlAgent, control_agent


def strip_stray_brace(code: str) -> str | None:
    """Return code without a leaked trailing `}` line, or None if there isn't one.

    Only strips when braces are unbalanced, so a dict literal legitimately
    closed on the last line is left alone.
    """
    lines = code.rstrip().splitlines()
    if lines and lines[-1].strip() == "}" and code.count("}") > code.count("{"):
        return "\n".join(lines[:-1]) + "\n"
    return None


@control_agent
def clean_submit_policy_builder(policy: ControlAgent) -> Agent:
    """Wrap `policy`, removing a leaked trailing `}` from submitted code."""

    async def impl(state: AgentState, tools: list[Tool]) -> AgentState:
        state = await policy(state, tools)
        message = state.output.message if state.output else None
        if not isinstance(message, ChatMessageAssistant):
            return state
        for tool_call in message.tool_calls or []:
            code = tool_call.arguments.get("code")
            if tool_call.function != "submit" or not isinstance(code, str):
                continue
            fixed = strip_stray_brace(code)
            if fixed is not None:
                # Mutating in place updates both state.output and the message
                # history, which hold the same message object.
                tool_call.arguments["code"] = fixed
                message.metadata = {**(message.metadata or {}), "stripped_stray_brace": True}
        return state

    return impl
