# Independent Genesis subsystem recording

One source tree contains reusable tools plus Cryo, Microwave, Magnet and ssRF
recorders. Every subsystem runs in its own process with independent PVs, save
interval, history controls, lock, server port and output directory. The source
folder may be renamed or moved: imports are relative and the launcher resolves
its own location. It does not import the existing Genesis `archive` package.

## Install and run

Use a Python environment with the dependencies from `requirements.txt` installed.
From this directory (any name):

```sh
python -m pip install -r requirements.txt
python run.py cryo list
python run.py cryo run
```

`run` records in the foreground; Ctrl+C stops cleanly. Managed recording:

```sh
python run.py cryo start
python run.py cryo status
python run.py cryo stop
python run.py all start
python run.py all status
python run.py all stop
```

All commands also work by absolute path, from any working directory:

```sh
python /path/to/recording/run.py microwave start
```

Use `--settings /path/to/settings.yaml` for a single subsystem's custom profile.
`--data-root /path/to/shared-data` overrides the settings path; the
`GENESIS_DATA_ROOT` environment variable can also override it. For a local test:

```sh
python run.py cryo run --data-root /tmp/genesis-data
```

The default shared WSL directory is `/home/shared/cooldown_data`. Give recorder
accounts write access to that directory; directories/files inherit the shared
root's group/default ACL permissions. The recorder does not change permissions.
Its processes only monitor instrument PVs; they never send hardware commands.
No instrument IOC is started by this launcher.

## Files and rates

Each subsystem contains `settings.yaml`, `pvs.yaml` and `recorder.py`. Settings
have explicit startup defaults (initially one second for each), the CA input
addresses and a unique control server port. Change `save_interval_s` independently
for each subsystem, or write its `SaveInterval` PV at runtime. Units are seconds
between saves: 5 means save every five seconds. Values must be finite and positive.
Live changes are not persisted to settings and reset on restart.

| Subsystem | Control PV prefix | CA server port | Output subdirectory |
|---|---|---|---|
| Cryo | UNH:GEN:CRYO:ARCH | 5140 | cryo/ |
| Microwave | UNH:GEN:MW:ARCH | 5141 | microwave/ |
| Magnet | UNH:GEN:MAG:ARCH | 5142 | magnet/ |
| ssRF | UNH:GEN:SSRF:ARCH | 5143 | ssrf/ |

Under each prefix: `SaveInterval` (writable normal interval, seconds) and
`EffectiveInterval` (read-only actual scheduled interval). A faster save rate
does not increase the sensor/IOC update rate. All timestamps are UTC. One CSV
per process run uses `<subsystem>_<UTC timestamp>_<pid>_<unique suffix>.csv`.
Each row contains timestamp_utc and the selected PV values, with no quality
columns. Unavailable and nonfinite readings become empty cells. Unchanged
connected readings repeat the last value. PV lists are loaded only at startup;
restart after editing them. A lock prevents two recorders using the same output.
Independent output roots can still create deliberate duplicate recordings.

The Cryo/Microwave/Magnet selections follow the requested reduced PV lists.
Planned Cryo T2/T4/T5 thermometer pairs are commented until their IOCs exist.
ssRF's initial periodic list is a small editable set of source/recipe state
readbacks; its burn parameter PV map is separate from that snapshot list.

## ssRF burn log and embedded waveforms

ssRF has BOTH periodic CSV snapshots and an independently triggered JSONL burn
stream under `ssrf/burns/`, labeled `ssrf_burns_<UTC timestamp>_...jsonl`.
The save-interval PV changes periodic snapshots only, never burn triggering.
Each accepted RUNNING transition captures the latest available burn parameters
and recipe session ID and generates a unique burn ID. Parameters are copied and
retained even if PVs subsequently change. Repeated RUNNING updates do not start
another burn. COMPLETE, FAILED, CLEANUP_FAILED and ABORTED finish it. Connection
loss or recorder shutdown produces an interrupted outcome, never success.

For durability, an append-only `burn_started` record contains parameters and the
full waveform, followed by a `burn_finished` record containing the same burn ID,
parameters and full waveform plus end time/outcome. These are two events for one
burn, not two burns. The GUI groups them by burn ID and uses the latest event.
There are no separate waveform files. No placeholder-identification fields are
saved. Missing parameters appear as null. A reconstruction error is saved as
`waveform_error` with waveform=null so the burn attempt is not silently lost.
The log is flushed and synced at each burn boundary.

`ssrf/waveform_reconstruction.py:reconstruct(parameters, sample_count)` is the
replacement point for the real algorithm. It currently generates a sine using
FM_PERIOD_S, FM_REPEATS and voltage bounds. The array includes sample spacing and
units. This is a development reconstruction, not a measured RF waveform, and is
never loaded onto hardware by this software. Replace it before scientific use.

### What was learned from the existing ssRF event code

The existing recipe IOC creates its session during preparation, before execution,
and periodically samples EXECUTION_STATE. This implementation observes that PV
with a CA subscription, logging executions rather than preparations. Continuous
burn cycles are handled by repeated RUNNING/terminal transitions.

CA monitoring is an observation adapter, not an authoritative execution journal:
it can miss events while disconnected, and its parameter monitors are not an
atomic snapshot of the sequencer. If started mid-burn, it captures only the
observed portion; timestamps are logger receipt times rather than physical RF
edges. It does not infer unobserved burns or claim measured RF delivery.
A logger restart cannot reliably identify a continuation without a sequencer
burn ID. Do not run two burn observers for the same execution stream.

For stronger guarantees, connect sequencer execution boundaries directly to
`BurnLogger.start(parameters, session_id)` and `finish(outcome, reason)` with the
captured execution parameters. That direct interface is provided; existing
sequencer code is not modified by this new folder. Short manual RF operations
outside sequenced burns are not automatically classified as burns.

The original semantic event logger API is preserved inside `ssrf/recipe_events.py`
and re-exported from `ssrf/event_logger.py` for later recipe/fitter integration.
It has package-relative path helpers and scientific scalar handling. Existing
recipe/fitter imports have not been redirected; optional semantic events are
not automatically duplicated by the standalone recorder.

## Future Cryo magnet-fill sampling

`cryo/settings.yaml` includes an OFF-by-default magnet_fill block. Later, supply
the real active_pv and set enabled:true. active_value defaults to 1. interval_s
sets the faster interval; settling_time_s keeps it fast briefly after filling
ends to prevent switching rapidly. The entire Cryo row is saved more often.
`EffectiveInterval` reports the scheduled interval while `SaveInterval` remains
the operator's normal interval. The faster of normal/fill intervals is used.

Unknown/disconnected fill status follows unavailable_policy (`fast` by default,
`normal` optionally). When disabled, no fill-status PV is subscribed. An enabled
configuration without an active_pv is rejected. Fill status has no influence on
hardware; it changes file sampling only.

## Phoebus history GUI

Open `gui/overview.bob` in Phoebus Display Runtime. Merge `gui/phoebus.properties`
into client preferences (use the recorder host instead of localhost remotely).
Each subsystem has a screen for interval controls, channel selection and history.
Enter Window (hours), End: hours ago (0=now), then Load / Refresh. History reads
that subsystem's CSVs, not another archiver or the old master schema. Numeric
plots show at most the latest 10,000 rows in the requested window. UTC endpoints
appear above the plot; x is hours relative to the endpoint. Blank readings create
gaps. History loads in a worker thread and refreshes only on request.

The ssRF Burn waveforms screen loads the embedded waveform: index 0 is the most
recent burn, index 1 the previous, etc. It shows burn ID, timestamp, outcome and
the saved waveform against time in seconds. A recorder must be running to serve
its historical data PVs. GUI clients share selection controls. `P` is the control
prefix macro; all open-display paths are relative. After changing PV lists or
prefixes, run `python gui/build_displays.py` to regenerate the screens.
Large burn windows are read on demand; the initial implementation scans the
burn log files and is intended for modest volumes, without an indexing service.

## Deployment boundaries

This folder is additive. Existing launchers, current master/per-PV recorders and
existing ssRF recipe imports are untouched. Starting these recorders does not
stop existing writers. Switch launchers deliberately when deploying; do not run
both generations if duplicate recordings are unwanted. Before replacing the
existing `archive` directory, migrate its remaining external imports/data-path
helpers too; renaming this source folder alone does not update other applications.

Tests live under `tests/`: `python -m pytest tests`. The end-to-end test launches
four independent recorders and one fake instrument IOC on private loopback ports,
with temporary output paths. It never uses lab addresses. No live hardware or
visual Phoebus acceptance is implied by those tests.
