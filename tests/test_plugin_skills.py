from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_portable_skill_metadata_contains_only_flat_strings():
    """Hermes' portable Agent Plugin loader rejects nested metadata values."""
    for skill_file in sorted((ROOT / "skills").glob("*/SKILL.md")):
        lines = skill_file.read_text(encoding="utf-8").splitlines()
        metadata_index = lines.index("metadata:")
        metadata_lines: list[str] = []
        for line in lines[metadata_index + 1 :]:
            if line and not line.startswith("  "):
                break
            if line.strip():
                metadata_lines.append(line)

        assert metadata_lines, f"{skill_file}: metadata must not be empty"
        for line in metadata_lines:
            assert not line.startswith("    "), f"{skill_file}: metadata must be flat"
            key, separator, value = line.strip().partition(":")
            assert key and separator and value.strip(), (
                f"{skill_file}: metadata keys and values must be non-empty strings"
            )
            assert value.strip()[0] not in "[{", (
                f"{skill_file}: metadata values must be strings, not collections"
            )
