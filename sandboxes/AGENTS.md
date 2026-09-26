# Sandboxes

This package runs inside one Modal sandbox per task. Its Python import package
remains `gg.server`. It owns the agent server, local conversation state,
workspace operations, Pi process, and task execution. It depends on `gg.sdk`
for shared HTTP contracts and never imports `gg.runtime`. Keep local execution
and persistence out of the SDK.
