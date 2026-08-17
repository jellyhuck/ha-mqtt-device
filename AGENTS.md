# AGENTS.md

Guidance for AI agents (and humans) working on this repository.

## Project context

`ha-mqtt-device` is a thin Python library for creating and maintaining Home Assistant devices that are discoverable via MQTT device discovery. It also lets you add and maintain the individual entities (sensors, switches, etc.) associated with a device.

The library currently has no third-party runtime dependencies and targets Python 3.14+.

## Development workflow

The project is managed with [uv](https://docs.astral.sh/uv/). Always use `uv`-prefixed commands rather than invoking `pip`, `pytest`, or formatters directly.

| Task          | Command                |
| ------------- | ---------------------- |
| Sync deps     | `uv sync`              |
| Run tests     | `uv run pytest`        |
| Format code   | `uv format`            |
| Lint          | `uv run ruff check`    |
| Type checking | `uv run mypy .`        |
| Build         | `uv build`             |

## Best practices

- **Run the full test suite** (`uv run pytest`) before considering a change complete.
- **Format after editing**: `uv format` keeps style consistent. Run it on any touched files.
- **Keep the library thin**: avoid adding heavy dependencies or framework-like abstractions. Prefer small, focused public APIs that model a device and its entities.
- **Tests belong in `tests/`**: add or update tests alongside any behavior change. Use pytest-style tests.
- Entity topics use the canonical `~/<unique_id>/state[/<suffix>]` and
  `~/<unique_id>/command[/<suffix>]` schemas. Use `Entity.state_topic_for()` and
  `Entity.command_topic_for()` for topic construction; an empty or `None`
  suffix produces the base state or command topic. Tests and examples should
  follow this schema when asserting or documenting topics.
- **Type hints**: annotate public functions and methods. The project targets Python 3.14+, so modern typing features are available.
- **Follow the existing package layout**: source lives under `src/ha_mqtt_device/`; keep it organized by device/entity concerns.

## Conventions

- Public API is exposed through `src/ha_mqtt_device/__init__.py`.
- Keep changes minimal and scoped. Prefer additive changes over refactors unless the refactor is part of the task.
- When adding entities, consider the corresponding Home Assistant MQTT discovery schema (device class, unit of measurement, state/command topics, etc.).
- `EXAMPLES.md` documents one section per entity (and device discovery and the MQTT provider). When adding an entity, add a runnable example there and a script under `examples/`; entities that are not yet supported stay listed in `EXAMPLES.md` with a TODO note.

## Dev guides

- If you add a new command or tool to the workflow, document it in both `README.md` and this file.
- Update `EXAMPLES.md` when the public API changes: keep the entity examples in sync, and mark newly supported entities no longer TODO. The `README.md` just points users at `EXAMPLES.md`, so keep that link and the linked file consistent.
- Verify the project metadata in `pyproject.toml` (name, version, entry points) stays in sync with the README.
