# Validation

The new package's 11 tests passed in a temporary Python environment on macOS.

The local-only end-to-end test copied the package to a folder named `archive`
and ran all four recorders from that location, alongside a fake input IOC. It
verified separate output folders, CSV values, independent save intervals,
fill-dependent rate switching and return to normal, a start/complete ssRF burn
with captured parameters and an embedded waveform, numeric history loading,
burn waveform history, and managed clean stop for all four processes.

Other tests cover immutable burn parameters, repeated-state deduplication,
multiple burns in one session, abort/interruption behavior, reconstruction
failure, the retained recipe event API, unavailable/nonfinite CSV readings,
history empty windows, exclusive output locks, relative GUI links and moving
the package to another directory name. Python syntax and all generated Phoebus
XML were parsed successfully. No tests contact lab addresses or write to the
shared live data path. Existing repository files are not changed by this build.

Live WSL/hardware acceptance and visual testing in Phoebus remain outstanding.
The sine reconstruction is a development implementation to replace with the
real algorithm. The event observer has the limitations documented in README:
CA observations are not an authoritative physical RF pulse journal. Direct
sequencer hooks are provided but not integrated into existing execution code.
