import numpy as np

from app.modules.matching.matcher import Matcher, MatcherConfig, points_near_matches


def test_finds_reference_pose(reference, make_scene):
    scene, _, centre = make_scene()
    matches = Matcher(reference, MatcherConfig(voxel_size=0.08)).find(scene)

    assert len(matches) == 1
    m = matches[0]
    assert m.fitness > 0.9
    assert np.linalg.norm(m.pose[:3, 3] - centre) < 0.05
    assert m.stage == "global+icp"


def test_recovers_rotation(reference, make_scene):
    scene, T, _ = make_scene(yaw_deg=70.0)
    matcher = Matcher(reference, MatcherConfig(voxel_size=0.08))
    m = matcher.find(scene)[0]
    # Compare the rotation relative to the ground truth: should be ~identity.
    delta = m.pose[:3, :3] @ T[:3, :3].T
    angle = np.degrees(np.arccos(np.clip((np.trace(delta) - 1) / 2, -1, 1)))
    assert angle < 3.0


def test_no_match_in_empty_scene(reference):
    rng = np.random.default_rng(3)
    floor = np.c_[rng.uniform(-10, 10, (20000, 2)), rng.normal(0, 0.005, 20000)]
    assert Matcher(reference, MatcherConfig(voxel_size=0.08, min_fitness=0.9)).find(floor) == []


def test_tracking_uses_icp_only(reference, make_scene):
    scene, _, centre = make_scene()
    matcher = Matcher(reference, MatcherConfig(voxel_size=0.08))
    first = matcher.find(scene)[0]
    tracked = matcher.find(scene, prev_pose=first.pose, prev_fitness=first.fitness)
    assert tracked[0].stage == "tracking"
    assert np.linalg.norm(tracked[0].pose[:3, 3] - centre) < 0.05


def test_tracking_falls_back_to_global_when_lost(reference, make_scene):
    scene, _, centre = make_scene()
    matcher = Matcher(reference, MatcherConfig(voxel_size=0.08))
    far = np.eye(4)
    far[:3, 3] = [-8.0, -8.0, 0.0]  # nowhere near the object
    result = matcher.find(scene, prev_pose=far, prev_fitness=1.0)
    assert result and result[0].stage == "global+icp"
    assert np.linalg.norm(result[0].pose[:3, 3] - centre) < 0.05


def test_reference_scale(reference, make_scene):
    scene, _, centre = make_scene()
    mm_reference = reference * 1000.0
    matcher = Matcher(mm_reference, MatcherConfig(voxel_size=0.08, reference_scale=0.001))
    assert np.linalg.norm(matcher.find(scene)[0].pose[:3, 3] - centre) < 0.05


def test_finds_two_instances(reference, make_scene):
    scene_a, _, centre_a = make_scene(translation=(4.0, -2.0, 0.5))
    scene_b, _, centre_b = make_scene(yaw_deg=-30, translation=(-5.0, -4.0, 0.5), seed=2)
    # keep both objects, one floor: take object points of B (first 12000) + all of A
    scene = np.vstack([scene_a, scene_b[:12000]])
    matches = Matcher(reference, MatcherConfig(voxel_size=0.08, max_instances=2, min_fitness=0.85)).find(scene)
    found = sorted(tuple(np.round(m.pose[:3, 3], 0)) for m in matches)
    assert len(matches) == 2
    for c in (centre_a, centre_b):
        assert min(np.linalg.norm(m.pose[:3, 3] - c) for m in matches) < 0.1
    assert found[0] != found[1]


def test_points_near_matches_isolates_object(reference, make_scene):
    scene, _, _ = make_scene()
    matches = Matcher(reference, MatcherConfig(voxel_size=0.08)).find(scene)
    out = points_near_matches(scene, matches, 0.16)
    assert 10000 < len(out) < 14000  # the 12k object points (+ a few floor points)
    assert len(points_near_matches(scene, [], 0.1)) == 0


def test_match_to_dict_is_json_serialisable(reference, make_scene):
    import json
    scene, _, _ = make_scene()
    m = Matcher(reference, MatcherConfig(voxel_size=0.08)).find(scene)[0]
    d = m.to_dict()
    json.dumps(d)
    assert set(d["rotation_deg"]) == {"roll", "pitch", "yaw"}
    assert abs(d["rotation_deg"]["yaw"] - 70) < 3
    assert abs(d["rotation_deg"]["roll"]) < 3 and abs(d["rotation_deg"]["pitch"]) < 3
