#!/usr/bin/env python3
"""Check the repository-local Claude/Codex entry points without external tools."""
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    adapter = root / "CLAUDE.md"
    assert "@AGENTS.md" in adapter.read_text().splitlines(), "Claude must import AGENTS.md"
    assert (root / "AGENTS.md").is_file(), "Missing common instructions"
    skills = root / ".agents/skills"
    entries = list(skills.glob("*/SKILL.md"))
    assert entries, "No project skills found"
    for entry in entries:
        alias = root / ".claude/skills" / entry.parent.name
        assert alias.is_symlink(), f"Expected shared skill link: {alias.name}"
        assert alias.resolve() == entry.parent.resolve(), f"Skill drift: {alias.name}"
        assert entry.resolve().is_relative_to(root), "Skills must stay inside the repository"
        lines = entry.read_text().splitlines()
        assert lines[0] == "---" and "---" in lines[1:], "Missing skill frontmatter"
        metadata = lines[1:lines[1:].index("---") + 1]
        assert f"name: {entry.parent.name}" in metadata, "Skill name differs from directory"
        assert any(line.startswith("description: ") for line in metadata), "Missing skill description"
    print(f"Agent harness: OK ({len(entries)} shared skill)")


if __name__ == "__main__":
    main()
