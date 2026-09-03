from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_pins_pi_runtime_and_disables_install_scripts() -> None:
    assert "FROM node:22.23.1-bookworm-slim AS pi-runtime" in DOCKERFILE
    assert "npm install --global --ignore-scripts" in DOCKERFILE
    assert "@earendil-works/pi-coding-agent@0.83.0" in DOCKERFILE


def test_dockerfile_copies_and_verifies_pi_runtime_in_final_image() -> None:
    assert (
        "COPY --from=pi-runtime /usr/local/bin/node /usr/local/bin/node"
        in DOCKERFILE
    )
    assert (
        "COPY --from=pi-runtime /usr/local/lib/node_modules "
        "/usr/local/lib/node_modules"
    ) in DOCKERFILE
    assert "../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm" in DOCKERFILE
    assert "../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx" in DOCKERFILE
    assert (
        "../lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
        in DOCKERFILE
    )
    assert 'test "$(node --version)" = "v22.23.1"' in DOCKERFILE
    assert 'test "$(pi --version)" = "0.83.0"' in DOCKERFILE


def test_dockerfile_preserves_non_root_server_contract() -> None:
    assert "USER ${USERNAME}" in DOCKERFILE
    assert "WORKDIR /workspace/project" in DOCKERFILE
    assert (
        'CMD ["python", "-m", "gg.server", "--host", "0.0.0.0", '
        '"--port", "8000"]'
    ) in DOCKERFILE
    assert ".pi" not in DOCKERFILE
