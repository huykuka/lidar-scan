from app.api.v1.recordings.handler import router


def test_stream_route_registered():
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/recordings/{recording_id}/stream" in paths
