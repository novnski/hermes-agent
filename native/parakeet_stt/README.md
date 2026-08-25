# Hermes Parakeet STT

This macOS helper exposes FluidAudio's Parakeet TDT 0.6B v3 Core ML model as
a file-to-text command for Hermes' existing `stt.providers.<name>` interface.
It is deliberately separate from Multiplexer and does not modify or communicate
with the running Multiplexer app.

Build, install the helper, and provision an independent model copy under the
active Hermes home:

```bash
./scripts/install_parakeet_stt.sh [source-model-directory]
```

The default source is Multiplexer's existing Parakeet v3 model directory. On
APFS the installer first attempts a copy-on-write clone; it falls back to a
normal copy. The source directory is only read. The installed model is
validated with FluidAudio before it is activated.

Configure Hermes with:

```yaml
stt:
  provider: parakeet
  providers:
    parakeet:
      type: command
      command: >-
        /path/to/hermes/bin/hermes-parakeet-stt
        --input {input_path}
        --output {output_path}
        --model-dir /path/to/hermes/models/parakeet-tdt-0.6b-v3
        --language {language}
      format: txt
      language: en
      timeout: 120
```

Verification:

```bash
swift test --package-path native/parakeet_stt
~/.hermes/bin/hermes-parakeet-stt \
  --check-model \
  --model-dir ~/.hermes/models/parakeet-tdt-0.6b-v3
```
