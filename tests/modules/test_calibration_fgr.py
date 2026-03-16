"""
Unit tests for Phase 4 — Fast Global Registration (FGR) support.

Tests that GlobalRegistration supports FGR as an alternative to RANSAC,
and that ICPEngine correctly passes through the FGR configuration flag.
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock


class TestGlobalRegistrationFGR:
    """Test FGR branch in GlobalRegistration"""

    def _make_point_cloud(self, n: int = 200) -> np.ndarray:
        """Create a random point cloud for testing."""
        return np.random.rand(n, 3).astype(np.float32)

    def test_ransac_mode_by_default(self):
        """use_fast_global_registration defaults to False → uses RANSAC"""
        from app.modules.calibration.registration.global_registration import GlobalRegistration

        gr = GlobalRegistration({})
        assert gr.use_fgr is False

    def test_fgr_mode_enabled_via_config(self):
        """use_fast_global_registration=True → FGR mode enabled"""
        from app.modules.calibration.registration.global_registration import GlobalRegistration

        gr = GlobalRegistration({"use_fast_global_registration": True})
        assert gr.use_fgr is True

    def test_global_result_has_method_field(self):
        """GlobalResult dataclass includes method field"""
        from app.modules.calibration.registration.global_registration import GlobalResult

        result = GlobalResult(
            transformation=np.eye(4),
            fitness=0.9,
            num_correspondences=50,
            converged=True,
            method="ransac"
        )
        assert result.method == "ransac"

    def test_global_result_method_fgr(self):
        """GlobalResult method field can be 'fgr'"""
        from app.modules.calibration.registration.global_registration import GlobalResult

        result = GlobalResult(
            transformation=np.eye(4),
            fitness=0.85,
            num_correspondences=40,
            converged=True,
            method="fgr"
        )
        assert result.method == "fgr"

    def test_ransac_calls_ransac_function(self):
        """When use_fgr=False, register() calls RANSAC matching function"""
        from app.modules.calibration.registration.global_registration import GlobalRegistration

        gr = GlobalRegistration({"use_fast_global_registration": False})
        source = self._make_point_cloud()
        target = self._make_point_cloud()

        ransac_mock = Mock(return_value=Mock(
            transformation=np.eye(4),
            fitness=0.85,
            correspondence_set=list(range(30))
        ))

        with patch(
            "open3d.pipelines.registration.registration_ransac_based_on_feature_matching",
            ransac_mock
        ), patch(
            "open3d.pipelines.registration.registration_fgr_based_on_feature_matching",
        ) as fgr_mock:
            result = gr.register(source, target)

        ransac_mock.assert_called_once()
        fgr_mock.assert_not_called()
        assert result.method == "ransac"

    def test_fgr_calls_fgr_function(self):
        """When use_fgr=True, register() calls FGR matching function"""
        from app.modules.calibration.registration.global_registration import GlobalRegistration

        gr = GlobalRegistration({"use_fast_global_registration": True})
        source = self._make_point_cloud()
        target = self._make_point_cloud()

        fgr_mock = Mock(return_value=Mock(
            transformation=np.eye(4),
            fitness=0.90,
            correspondence_set=list(range(35))
        ))

        with patch(
            "open3d.pipelines.registration.registration_fgr_based_on_feature_matching",
            fgr_mock
        ), patch(
            "open3d.pipelines.registration.registration_ransac_based_on_feature_matching",
        ) as ransac_mock:
            result = gr.register(source, target)

        fgr_mock.assert_called_once()
        ransac_mock.assert_not_called()
        assert result.method == "fgr"


class TestICPEngineFGRPassthrough:
    """Test that ICPEngine passes use_fast_global_registration flag to GlobalRegistration"""

    def test_icp_engine_fgr_flag_default_false(self):
        """ICPEngine default: use_fast_global_registration=False"""
        from app.modules.calibration.registration.icp_engine import ICPEngine

        engine = ICPEngine({})
        # When global registration is enabled, it should default to RANSAC
        if engine.global_reg is not None:
            assert engine.global_reg.use_fgr is False

    def test_icp_engine_passes_fgr_flag_to_global_reg(self):
        """ICPEngine passes use_fast_global_registration=True to GlobalRegistration"""
        from app.modules.calibration.registration.icp_engine import ICPEngine

        config = {
            "enable_global_registration": True,
            "use_fast_global_registration": True
        }
        engine = ICPEngine(config)
        assert engine.global_reg is not None
        assert engine.global_reg.use_fgr is True

    def test_icp_engine_no_global_reg_fgr_flag_irrelevant(self):
        """When global registration disabled, FGR flag has no effect"""
        from app.modules.calibration.registration.icp_engine import ICPEngine

        config = {
            "enable_global_registration": False,
            "use_fast_global_registration": True
        }
        engine = ICPEngine(config)
        assert engine.global_reg is None

    def test_icp_engine_fgr_false_passes_to_global_reg(self):
        """ICPEngine explicit use_fast_global_registration=False → RANSAC mode"""
        from app.modules.calibration.registration.icp_engine import ICPEngine

        config = {
            "enable_global_registration": True,
            "use_fast_global_registration": False
        }
        engine = ICPEngine(config)
        assert engine.global_reg is not None
        assert engine.global_reg.use_fgr is False
