# Adapt ICP registration steps in calibration backend to match Open3D tutorial - Requirements

## Feature Overview

Align the backend calibration workflow with the Open3D global-registration tutorial so that calibration follows a documented, stage-based pipeline instead of behaving like a black-box ICP trigger. Based on current documented calibration artifacts, the existing flow already matches the tutorial at a high level in that it supports a calibration trigger, returns per-sensor registration quality metrics (`fitness`, `rmse`, `quality`), and requires explicit operator approval before results are accepted. However, the documented flow diverges from the tutorial because preprocessing stages are not exposed, a global-registration fallback stage is not documented, the fine-registration method and parameters are not documented, and the API does not currently report stage-by-stage execution details or the basis for the produced transform.

This feature must introduce a clearly defined backend calibration sequence with Open3D-aligned terminology and ordering: validation of externally preprocessed source and target clouds, optional or automatic global registration initialization using FPFH features with RANSAC when no reliable initial transform exists, fine ICP refinement using a declared estimation mode, and structured result reporting for operator review and approval. The backend must preserve the current approval model and existing calibration lifecycle endpoints while extending them so users can understand what was run, which upstream preprocessing chain produced the calibration inputs, whether fallback was invoked, and why a calibration result should be accepted or rejected.

The feature must also define the user journey across backend and API/UI touchpoints. The operator triggers calibration from the existing calibration action in the UI or the `POST /api/v1/calibration/{node_id}/trigger` endpoint. The backend executes the staged registration flow and returns visible feedback for each major stage, including whether preprocessing completed, whether global registration fallback was used, which ICP mode was applied, final transform quality metrics, and whether results are pending approval. The operator then reviews the result summary and explicitly accepts or rejects it through the existing accept or reject actions. History, statistics, and rollback views must continue to work and must reflect the new Open3D-aligned metadata for traceability.

## User Stories

- As an operator, I want calibration to follow a predictable Open3D-style pipeline so that registration results are easier to trust, compare, and troubleshoot.
- As an operator, I want calibration to consume point clouds preprocessed by upstream DAG nodes using documented downsampling, normal estimation, and feature preparation steps so that I can fully control the preprocessing chain before registration.
- As an operator, I want the system to use FPFH plus RANSAC as a required fallback when there is no reliable initial transform so that calibration can still start from poor initial alignment.
- As an operator, I want the system to tell me whether it used direct ICP only or global registration plus ICP refinement so that I understand how the final transform was obtained.
- As an operator, I want core calibration tunables exposed through the API and surfaced in the UI so that I can adjust voxel size, frame sampling, correspondence thresholds, ICP mode, and iteration limits without changing backend code.
- As an operator, I want fine registration to declare whether point-to-point or point-to-plane ICP was used so that the refinement method matches the data and is auditable.
- As an operator, I want calibration responses to include stage-level status, key metrics, and final approval state so that I can decide whether to accept or reject the result.
- As an operator, I want calibration results to remain pending until I explicitly approve them so that no new transform is applied silently.
- As an administrator, I want the API contract and terminology to match Open3D concepts so that documentation, support, and future development use consistent language.
- As a reviewer or support engineer, I want calibration history and rollback records to preserve the registration method and key parameters used so that past calibration decisions can be understood later.

## Acceptance Criteria

- The feature defines a required calibration pipeline with the following ordered stages: input frame selection, preprocessing, global initialization decision, global registration fallback when needed, fine ICP refinement, result evaluation, and explicit approval or rejection.
- The preprocessing stage is a first-class documented part of calibration and reports the externally prepared inputs used for calibration, including, at minimum, whether upstream preprocessing provided downsampled clouds, normals where required by the chosen registration mode, and feature preparation for global registration.
- The calibration API and user-facing terminology explicitly use Open3D-aligned names such as voxel downsampling, normal estimation, FPFH features, RANSAC global registration, point-to-point ICP, point-to-plane ICP, fitness, and inlier RMSE.
- `POST /api/v1/calibration/{node_id}/trigger` remains the primary backend trigger for calibration and is extended to accept core tunables for the staged pipeline.
- The trigger request supports `sample_frames` plus core registration tunables covering, at minimum, global-registration enablement or auto mode, global-registration correspondence threshold, ICP mode, ICP correspondence threshold, and ICP iteration limit. Preprocessing tunables are configured on upstream DAG preprocessing nodes rather than on the calibration trigger.
- The system supports a documented default behavior for each core registration tunable so calibration can still run when the client does not supply advanced values, while preprocessing defaults remain the responsibility of the configured DAG preprocessing nodes.
- The backend determines whether a reliable initial transform is already available; when it is not, FPFH plus RANSAC global registration is required before fine ICP refinement.
- If a reliable initial transform is available, the system may skip global registration, but the response must explicitly state that global initialization was skipped and why.
- Global registration is performed on externally preprocessed or downsampled point clouds rather than the full-resolution clouds, consistent with the Open3D tutorial flow.
- Global registration uses FPFH-derived feature matching with RANSAC as the required baseline fallback path.
- The feature may later support fast global registration, but FPFH plus RANSAC is the minimum required global-registration baseline for this scope.
- Fine registration is always performed as an explicit ICP refinement stage after initialization unless the run fails before reaching ICP.
- The fine-registration stage must support at least point-to-point ICP and point-to-plane ICP as selectable modes.
- The response for each calibrated source sensor identifies which ICP mode was used and whether the result came from direct ICP or from global registration followed by ICP.
- Calibration results continue to include per-sensor quality metrics and must include, at minimum, final fitness, final inlier RMSE, produced transform, and pending approval state.
- The trigger response is extended to include stage-level reporting for each source sensor, including preprocessing status, whether upstream preprocessing provided normals, whether upstream preprocessing provided FPFH features, whether RANSAC was run, whether ICP was run, and the final stage reached.
- The trigger response includes operator-visible explanation fields for failure or degradation cases, such as insufficient data, preprocessing failure, feature computation failure, global registration failure, ICP non-convergence, or quality below acceptance guidance.
- The trigger response clearly distinguishes between pipeline failure, partial completion, and successful completion pending approval.
- Calibration may be connected downstream of one or more preprocessing/operation nodes and must not require a direct sensor-to-calibration edge as long as source sensor identity and preprocessing context are preserved in payload metadata.
- Calibration fails with a clear actionable error when required external preprocessing metadata or artifacts are missing for the chosen registration path.
- The current explicit approval workflow is preserved: calibration results are not applied permanently until the operator performs the existing accept action.
- `POST /api/v1/calibration/{node_id}/accept` continues to accept specific sensors or all pending sensors, and accepted records must preserve the pipeline method, stage summary, and core parameters used for that accepted calibration.
- `POST /api/v1/calibration/{node_id}/reject` continues to discard pending results, and the system must not apply rejected transforms.
- `GET /api/v1/calibration/history/{sensor_id}` is extended to show enough metadata to understand how a historical result was produced, including at minimum registration path used, ICP mode, and key tunables or preset values.
- `GET /api/v1/calibration/statistics/{sensor_id}` continues to expose aggregate quality information and may include counts by registration path or ICP mode if available, but must not regress existing statistics.
- `POST /api/v1/calibration/rollback/{sensor_id}` continues to restore previously accepted calibrations and must restore only accepted results, not rejected or merely pending runs.
- The UI user journey is documented as follows: the operator initiates calibration from the calibration control; the backend runs the staged pipeline; the UI shows in-progress stage feedback and final per-sensor results; the operator then accepts or rejects; historical and rollback views expose the resulting record.
- During a calibration run, the user can see whether the system is in preprocessing, global registration, ICP refinement, or result-review state.
- After a run completes, the user can see for each sensor the final quality metrics, the registration path used, whether fallback was invoked, and whether the result is pending approval, accepted, or rejected.
- If calibration cannot proceed because required preprocessing inputs are missing or insufficient, the user receives a clear actionable error instead of a generic calibration failure.
- If global registration fallback fails, the system reports that failure explicitly and does not mislabel the result as a successful ICP calibration.
- If ICP refinement fails or does not meet documented quality guidance, the response identifies the failure stage and keeps the result unapproved.
- The feature requirements explicitly close current documentation gaps by requiring preprocessing visibility, fallback visibility, parameter visibility, and stage-level reporting in the calibration API contract.
- Existing calibration lifecycle capabilities documented in current plans—trigger, accept, reject, history, statistics, and rollback—remain part of the supported user journey and are not removed by this feature.

## Out of Scope

- Replacing the existing calibration lifecycle with a completely new endpoint set.
- Automatic approval of calibration results by default.
- Frontend redesign beyond the minimum UI changes needed to surface stage progress, core tunables, and approval-ready results.
- Advanced expert exposure of every possible Open3D parameter beyond the agreed core tunables.
- Multiway registration, pose-graph optimization, SLAM, or non-rigid registration workflows.
- Requirement to support colored ICP, generalized ICP, or fast global registration in the first aligned version unless separately planned later.
- Calibration-code refactors unrelated to making the workflow match the Open3D tutorial stages and terminology.
- Silent fallback or hidden backend heuristics that are not reported back through the calibration result metadata.
