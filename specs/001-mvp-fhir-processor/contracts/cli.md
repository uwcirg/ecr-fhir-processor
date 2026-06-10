# Contract: CLI & Configuration

The processor is a single-entry CLI: `process.py`. This contract defines its invocation
surface and the config schema it consumes. (Stable interface for users and CI.)

## Invocation

```text
python3 process.py [--config PATH] [--input-dir PATH] [--measure NAME]
                   [--output-dir PATH] [--no-output-mirror] [--dry-run]
                   [--log-dir PATH] [--verbose]
```

| Flag | Default | Meaning |
|------|---------|---------|
| `--config` | `config.json` | Path to the run config (template: `config.example.json`). |
| `--input-dir` | `config.paths.input_dir` (`input`) | Root of the input tree to process. |
| `--measure` | all | Restrict to one measure folder (`poor-diabetic-control`, `controllable-bp`, `depression-screening`). |
| `--output-dir` | `config.paths.output_dir` (`output`) | Where the submitted-JSON mirror is written. |
| `--no-output-mirror` | off | Skip writing the local output mirror. |
| `--dry-run` | off | Discover, classify, stamp, and transform, but do **not** submit. Prints the RunSummary. Used by CI/validator gate. |
| `--log-dir` | `config.paths.log_dir` (`log`) | Audit-log directory. |
| `--verbose` | off | Console DEBUG verbosity (file log is always detailed). |

## Behavior contract

- **Config validation (FR-010)**: On startup, require non-empty `server.base_url`,
  `server.token_endpoint`, `server.client_id`, `server.client_secret`. If any is missing,
  empty, or still equal to its `YOUR_*` placeholder → exit non-zero with a message naming
  the field. (`--dry-run` does not require server credentials.)
- **Discovery**: Recursively find `*.json` under the input root, grouped by
  `{measure}/{population}/{scenario}/`. Empty input → exit `0`, "nothing processed".
- **Per-file outcome** is logged and aggregated into the RunSummary.
- **Exit code (FR-014)**: `0` iff `failed == 0`; non-zero otherwise.
- **Logging (FR-013)**: console + `log/ecr-fhir-processor_{YYYY-MM-DDtHHMMSS}.log`.

## Config schema (`config.json`)

See [research.md D7](../research.md) for the reconciled `config.example.json`. Required
vs. optional:

| Key | Required | Notes |
|-----|----------|-------|
| `software.name` | yes | Provenance identity code. |
| `software.identifier_system` / `identifier_value` | yes | Stable system identifier. |
| `server.base_url` | yes (unless `--dry-run`) | FHIR R4 base. |
| `server.token_endpoint` | yes (unless `--dry-run`) | OAuth2 token URL. |
| `server.client_id` / `client_secret` | yes (unless `--dry-run`) | OAuth2 client-credentials. **Secret — never committed.** |
| `ig_versions{}` | recommended | IG → version for the validator gate (Principle II). |
| `paths{input_dir,output_dir,log_dir}` | optional | Default `input`/`output`/`log`. |

> `software.version` is **not** a config field — it is derived from git at runtime (D5,
> FR-006).
