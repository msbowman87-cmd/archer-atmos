# Continuous Atmos observation collection

The user authorized collection of all available 2016–2025 observations without stopping at window boundaries. Production/main remain outside scope.

The research collector runs successive provider windows inside each runner session. Each window preserves a verified research-data archive before source files can be pruned locally. A completion sidecar records the original source SHA256 and verified release/part SHA256. Missing raw files count as complete only when this verified archive reference exists. Present corrupted files are never accepted merely because an archive reference exists.

Audit results are cached per source file and audit version. Raw files present on the runner are still hash-checked. Archived files require both a verified archive reference and a matching versioned coverage cache; measurements are not repeatedly parsed. Detailed variable-period reports stream to CSV/JSONL instead of holding the growing audit in memory.

Archives contain newly collected original bytes plus checkpoint metadata, caches and references to earlier archives. Earlier source bytes remain in referenced research releases. Source measurements, flags and timestamps are not altered. Runner deletion occurs only after release upload-size verification and source-hash agreement. Temporary artifacts are reduced to the two newest checkpoints; original observations in research archives are not deleted.

Each runner attempts to queue a research-branch successor. Platform deadlines do not signal task completion. An enabled hourly supervisor independently checks for idle/stalled collection and resumes or repairs it. Dispatch results must be observed; main is never modified to work around GitHub requirements.

Provider limits, retries and source gaps remain explicit. Three consecutive windows with no completed files trigger provider-recovery supervision instead of a request storm. Exhausting the current catalog does not imply that missing periods exist or the 10,000-location target is met. The 3,191-location source-verification shortage remains open.

Validation executes in GitHub regression jobs because the local executor is unavailable in this session. No job, archive/pruning cycle, or successor acceptance may be reported successful before its actual results are observed.
