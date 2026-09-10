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


def test_dockerfile_pins_git_and_github_cli() -> None:
    assert "git=1:2.39.5-0+deb12u3" in DOCKERFILE
    assert "cli/cli/releases/download/v2.100.0/" in DOCKERFILE
    assert "gh_2.100.0_linux_${TARGETARCH}.tar.gz" in DOCKERFILE
    assert "sha256sum -c" in DOCKERFILE
    assert "apt-get install git" not in DOCKERFILE
    assert "apt-get install -y gh" not in DOCKERFILE


def test_dockerfile_verifies_git_and_gh_versions_in_final_image() -> None:
    git_install = DOCKERFILE.index("git=1:2.39.5-0+deb12u3")
    user_switch = DOCKERFILE.index("USER ${USERNAME}")
    assert git_install < user_switch
    assert DOCKERFILE.index("/usr/local/bin/gh") < user_switch
    assert 'test "$(git --version)" = "git version 2.39.5"' in DOCKERFILE
    assert "gh --version" in DOCKERFILE
    assert "gh version 2.100.0" in DOCKERFILE


def test_dockerfile_preserves_non_root_server_contract() -> None:
    assert "USER ${USERNAME}" in DOCKERFILE
    assert "WORKDIR /workspace/project" in DOCKERFILE
    assert (
        'CMD ["python", "-m", "gg.server", "--host", "0.0.0.0", '
        '"--port", "8000"]'
    ) in DOCKERFILE
    assert ".pi" not in DOCKERFILE
    assert "GH_TOKEN" not in DOCKERFILE
    assert "GITHUB_TOKEN" not in DOCKERFILE
    assert ".gitconfig" not in DOCKERFILE
    assert ".ssh" not in DOCKERFILE
    assert "gh auth" not in DOCKERFILE
    assert "credential.helper" not in DOCKERFILE
