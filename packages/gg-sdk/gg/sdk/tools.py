from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gg.sdk.local_workspace import LocalWorkspace


class Observation(BaseModel):
    """Structured result after a tool runs; becomes an event payload in the loop."""

    model_config = ConfigDict(frozen=True)

    payload: dict[str, Any] = Field(default_factory=dict)


class Tool(Protocol):
    """Contract every tool implements: a stable name and a run method."""

    name: str

    # Execute with plain dict args and return a typed observation.
    def run(self, args: dict[str, Any], workspace: LocalWorkspace) -> Observation: ...


class ToolNotFoundError(Exception):
    """Registry could not find a tool with the requested name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown tool: {name}")


class WriteFileTool:
    """Writes path and content through LocalWorkspace.write_file."""

    name = "write_file"

    # Validate args, write bytes to disk, return what happened.
    def run(self, args: dict[str, Any], workspace: LocalWorkspace) -> Observation:
        try:
            path = args["path"]
            content = args["content"]
        except KeyError as exc:
            missing = exc.args[0]
            raise ValueError(f"write_file requires '{missing}' in args") from exc

        if not isinstance(path, str):
            raise TypeError("write_file args.path must be a str")
        if not isinstance(content, str):
            raise TypeError("write_file args.content must be a str")

        workspace.write_file(path, content)
        byte_count = len(content.encode())

        return Observation(
            payload={
                "path": path,
                "bytes_written": byte_count,
            }
        )


class ToolRegistry:
    """Maps tool names to implementations; unknown names fail here."""

    # Build the name → tool lookup table from the provided tools.
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    # Resolve the tool by name, then delegate to its run method.
    def run(
        self,
        name: str,
        args: dict[str, Any],
        workspace: LocalWorkspace,
    ) -> Observation:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(name)
        return tool.run(args, workspace)


# Convenience factory with the one tool we need for the dummy agent loop.
def default_tool_registry() -> ToolRegistry:
    return ToolRegistry([WriteFileTool()])
