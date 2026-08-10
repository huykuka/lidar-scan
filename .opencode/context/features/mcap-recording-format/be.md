# BE Feature Context: mcap-recording-format
_Updated: 2026-08-10_

## Goal
Migrate persisted recording format ZIP-of-PCD → MCAP (foxglove.PointCloud protobuf).
Live WS LIDR wire protocol byte-identical. Startup migration ZIP→MCAP.

## Key files to create/modify
- NEW: `app/services/shared/mcap_recording.py` — McapRecordingWriter, McapRecordingReader, _ZipReader shim
- MODIFY: `app/services/shared/recording.py` — extract SICK_SCAN_SCHEMA, PIPELINE_SCHEMA as consts (already there)
- MODIFY: `app/services/shared/recorder.py` — line 99: recording_{id}.zip→.mcap; line 113: RecordingWriter→McapRecordingWriter; final_name .zip→.mcap
- MODIFY: `app/api/v1/recordings/service.py` — stream_recording:94, get_recording_frame_as_pcd:622, trim_recording:899, _perform_trim_copy:859/861/863, upload_recording:660-790, download_recording:545
- MODIFY: `app/services/shared/thumbnail.py` — line 168: RecordingReader → McapRecordingReader (import)
- MODIFY: `app/modules/playback/node.py` — multiple RecordingReader usages + zipf.close() calls
- MODIFY: `app/db/migrate.py` — add migrate_zip_recordings_to_mcap()
- MODIFY: `app/core/lifespan.py` — wire migration between ensure_schema(:28) and get_recorder(:30)
- NEW: `tests/services/test_mcap_recording.py` — AC1-AC11

## Findings
- RecordingModel.file_path stores full abs path incl .zip — reuse column, NO schema change
- LIDR _encode_stream_frame uses `<4sIIIdI` + xyz only (f32) — NOT touched
- recorder.py line 99: `filename = f"recording_{recording_id}.zip"` → change to .mcap
- recorder.py line 206: `final_name = f"{safe_node_id}_{ts_ms}.zip"` → change to .mcap
- service.py trim line 928: `dest = recordings_dir / f"{new_id}.zip"` → .mcap
- playback/node.py line 164/203: `.with_suffix(".zip")` guard + `reader.zipf.close()` → needs update
- thumbnail.py imports RecordingReader from recording.py → change to McapRecordingReader
- download_recording line 545: `.lidr` → `.mcap`
- upload_recording entirely ZIP-based → rewrite for MCAP (accept .mcap primary, .zip convert)

## Deps to add
- mcap>=1.2,<2
- mcap-protobuf-support>=0.5,<1  
- foxglove-schemas-protobuf>=0.3,<1
- Pillow (already used in thumbnail.py via PIL)

## Status
- [x] B1 deps installed: mcap==1.4.0, mcap-protobuf-support==0.5.4, foxglove-schemas-protobuf==0.4.0
- [x] B2 mcap_recording.py written
- [x] B3 schema consts verified (SICK_SCAN_SCHEMA 16, PIPELINE_SCHEMA 14 in recording.py + copied to mcap_recording.py)
- [x] B4 recorder.py rewired (.zip→.mcap, RecordingWriter→McapRecordingWriter)
- [x] B5 service.py readers rewired + thumbnail.py + playback/node.py (zipf.close→close)
- [x] B6 upload rewrite: .mcap primary + .zip convert, path-traversal guard
- [x] B7 download .mcap filename
- [x] B8 migration + lifespan (between ensure_schema and get_recorder)
- [x] B9 tests: 38 passed (AC1-AC9+validation)
- [x] pytest green (pre-existing test_get_recorder_creates_default_dir failure NOT caused by us - confirmed by git stash test)
- [x] detect_changes: MEDIUM risk, all expected symbols, 3 lifespan-adjacent processes
