"""Static checks on the Dockerfile and the Compose file.

They read the files as text, so they need no Docker and no extra parser.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DOCKERFILE = ROOT / "deploy" / "docker" / "Dockerfile"
COMPOSE = ROOT / "deploy" / "compose" / "compose.yaml"
DOCKERIGNORE = ROOT / ".dockerignore"
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_dockerfile_images_are_pinned_by_digest() -> None:
    refs = [
        line
        for line in _lines(DOCKERFILE)
        if line.startswith("FROM ") or "--from=ghcr.io" in line
    ]

    assert len(refs) >= 3
    for line in refs:
        assert DIGEST.search(line), line


def test_dockerfile_does_not_run_as_root() -> None:
    users = [ln for ln in _lines(DOCKERFILE) if ln.startswith("USER ")]

    assert users
    assert users[-1].split()[1] not in ("root", "0")


def test_dockerfile_does_not_copy_secrets_or_the_whole_context() -> None:
    copies = [ln for ln in _lines(DOCKERFILE) if ln.startswith("COPY ")]

    for line in copies:
        assert ".env" not in line
        assert line.split()[1:] != [".", "."]


def test_dockerignore_keeps_secrets_out_of_the_build_context() -> None:
    entries = {ln.strip() for ln in _lines(DOCKERIGNORE)}

    assert {".env", ".env.*", ".git", "tests", ".claude"} <= entries


def test_every_pulled_compose_image_is_pinned_by_digest() -> None:
    # rolda:dev is built from this repository, not pulled from a registry.
    images = [
        ln.strip()
        for ln in _lines(COMPOSE)
        if ln.strip().startswith("image:") and ln.strip() != "image: rolda:dev"
    ]

    assert images
    for line in images:
        assert DIGEST.search(line), line


def test_compose_publishes_ports_on_loopback_only() -> None:
    ports = [ln.strip() for ln in _lines(COMPOSE) if re.match(r'\s*- "\d', ln)]

    assert ports
    for line in ports:
        assert line.startswith('- "127.0.0.1:'), line


def test_compose_has_no_literal_secret_values() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    for name in ("PASSWORD", "TOKEN"):
        for match in re.finditer(rf"\w*{name}\w*:\s*(.+)", text):
            assert match.group(1).startswith("${"), match.group(0)


def test_app_services_use_the_app_profile_and_a_hardened_runtime() -> None:
    text = COMPOSE.read_text(encoding="utf-8")

    for service in ("migrate", "worker", "api"):
        block = text.split(f"\n  {service}:\n", 1)[1].split("\n\n", 1)[0]
        assert 'profiles: ["app"]' in block, service
        assert "read_only: true" in block, service
        assert "cap_drop: [ALL]" in block, service
        assert "no-new-privileges:true" in block, service
        assert "user:" not in block or "root" not in block, service


def test_the_api_token_comes_from_the_environment_and_is_optional() -> None:
    # Compose interpolates every service, even one in an inactive profile.
    # A required variable would break "docker compose up" without the app
    # profile. The API itself refuses to start without a token.
    text = COMPOSE.read_text(encoding="utf-8")

    assert "ROLDA_API_TOKEN: ${ROLDA_API_TOKEN:-}" in text
