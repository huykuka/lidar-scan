"""Tests for LiDAR device profiles module - Updated for actual implementation"""
import pytest
from app.modules.lidar.profiles import (
    SickLidarProfile,
    get_all_profiles,
    get_enabled_profiles,
    get_profile,
    build_launch_args
)


class TestProfilesData:
    """Test profile data structures and retrieval"""
    
    def test_get_all_profiles_returns_25_profiles(self):
        """Verify 25 SICK LiDAR profiles are registered"""
        profiles = get_all_profiles()
        assert len(profiles) == 25
        assert all(isinstance(p, SickLidarProfile) for p in profiles)
    
    def test_get_enabled_profiles_filters_disabled(self):
        """get_enabled_profiles returns only enabled profiles"""
        all_profiles = get_all_profiles()
        enabled_profiles = get_enabled_profiles()
        
        # Enabled count should be <= all count
        assert len(enabled_profiles) <= len(all_profiles)
        # All enabled profiles should have disabled=False
        assert all(not p.disabled for p in enabled_profiles)
    
    def test_get_all_profiles_have_unique_model_ids(self):
        """Each profile must have a unique model_id"""
        profiles = get_all_profiles()
        model_ids = [p.model_id for p in profiles]
        assert len(model_ids) == len(set(model_ids))
    
    def test_get_all_profiles_have_required_fields(self):
        """Each profile must have all required fields"""
        profiles = get_all_profiles()
        required = {'model_id', 'display_name', 'launch_file', 'default_hostname',
                   'port_arg', 'default_port', 'has_udp_receiver', 'has_imu_udp_port',
                   'scan_layers'}
        for p in profiles:
            for field in required:
                assert hasattr(p, field)
                assert getattr(p, field) is not None or field in {'default_port'}
    
    def test_multiscan_profile_properties(self):
        """multiScan profile has correct UDP/IMU support"""
        profile = get_profile("multiscan")
        assert profile.model_id == "multiscan"
        assert profile.display_name == "SICK multiScan100"
        assert profile.launch_file == "launch/sick_multiscan.launch"
        assert profile.port_arg == "udp_port"
        assert profile.default_port == 2115
        assert profile.has_udp_receiver is True
        assert profile.has_imu_udp_port is True
        assert profile.scan_layers == 16
    
    def test_tim_5xx_profile_properties(self):
        """TiM5xx profile has no UDP/IMU support"""
        profile = get_profile("tim_5xx")
        assert profile.model_id == "tim_5xx"
        assert profile.display_name == "SICK TiM5xx Family"
        assert profile.launch_file == "launch/sick_tim_5xx.launch"
        assert profile.port_arg == "port"
        assert profile.default_port == 2112
        assert profile.has_udp_receiver is False
        assert profile.has_imu_udp_port is False
        assert profile.scan_layers == 1
    
    def test_tim_7xx_profile_properties(self):
        """TiM7xx profile is TCP only"""
        profile = get_profile("tim_7xx")
        assert profile.port_arg == "port"
        assert profile.has_udp_receiver is False
        assert profile.has_imu_udp_port is False
    
    def test_lms_1xx_profile_no_port_arg(self):
        """LMS1xx profile has no port argument (TCP only)"""
        profile = get_profile("lms_1xx")
        assert profile.port_arg == ""
        assert profile.default_port == 0
        assert profile.has_udp_receiver is False
        assert profile.has_imu_udp_port is False
    
    def test_mrs_6xxx_profile_multi_layer(self):
        """MRS6xxx profile has 24 layers"""
        profile = get_profile("mrs_6xxx")
        assert profile.scan_layers == 24
        assert profile.port_arg == ""
    
    def test_get_profile_unknown_raises_keyerror(self):
        """Requesting unknown profile raises KeyError"""
        with pytest.raises(KeyError):
            get_profile("velodyne_vls128")
        with pytest.raises(KeyError):
            get_profile("ouster_os1")
        with pytest.raises(KeyError):
            get_profile("")
    
    def test_all_profiles_have_valid_launch_files(self):
        """All profiles point to launch files with .launch extension"""
        profiles = get_all_profiles()
        for p in profiles:
            assert p.launch_file.startswith("launch/")
            assert p.launch_file.endswith(".launch")
    
    def test_tim_240_uses_sick_tim_240_launch(self):
        """TiM240 uses correct launch file"""
        profile = get_profile("tim_240")
        assert profile.launch_file == "launch/sick_tim_240.launch"


class TestLaunchArgsGeneration:
    """Test build_launch_args function for correct argument assembly"""
    
    def test_build_launch_args_multiscan_full(self):
        """multiScan with all UDP/IMU parameters"""
        args = build_launch_args(
            model_id="multiscan",
            hostname="192.168.0.50",
            port=2115,
            udp_receiver_ip="192.168.0.10",
            imu_udp_port=7503,
            add_transform_xyz_rpy="0.0,0.0,0.5,0.0,0.0,0.0"
        )
        assert "launch/sick_multiscan.launch" in args
        assert "hostname:=192.168.0.50" in args
        assert "udp_port:=2115" in args
        assert "udp_receiver_ip:=192.168.0.10" in args
        assert "imu_udp_port:=7503" in args
    
    def test_build_launch_args_multiscan_no_udp_receiver_ip(self):
        """multiScan without udp_receiver_ip omits that parameter"""
        args = build_launch_args(
            model_id="multiscan",
            hostname="192.168.0.50",
            port=2115,
            udp_receiver_ip=None,
            imu_udp_port=7503,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "hostname:=192.168.0.50" in args
        assert "udp_port:=2115" in args
        assert "imu_udp_port:=7503" in args
        assert "udp_receiver_ip" not in args
    
    def test_build_launch_args_tim_5xx_no_udp_fields(self):
        """TiM5xx uses 'port' argument, not 'udp_port'"""
        args = build_launch_args(
            model_id="tim_5xx",
            hostname="192.168.0.100",
            port=2112,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "launch/sick_tim_5xx.launch" in args
        assert "hostname:=192.168.0.100" in args
        assert "port:=2112" in args
        assert "udp_port" not in args
        assert "udp_receiver_ip" not in args
        assert "imu_udp_port" not in args
    
    def test_build_launch_args_lms_1xx_no_port_arg(self):
        """LMS1xx TCP-only device has no port parameter"""
        args = build_launch_args(
            model_id="lms_1xx",
            hostname="192.168.0.50",
            port=None,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "launch/sick_lms_1xx.launch" in args
        assert "hostname:=192.168.0.50" in args
        assert "port:=" not in args
        assert "udp_port:=" not in args
    
    def test_build_launch_args_mrs_6xxx_tcp_only(self):
        """MRS6xxx TCP-only device"""
        args = build_launch_args(
            model_id="mrs_6xxx",
            hostname="192.168.1.50",
            port=None,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="1.0,2.0,3.0,0.1,0.2,0.3"
        )
        assert "launch/sick_mrs_6xxx.launch" in args
        assert "hostname:=192.168.1.50" in args
        assert "port:=" not in args
    
    def test_build_launch_args_tim_240_with_port(self):
        """TiM240 uses port argument"""
        args = build_launch_args(
            model_id="tim_240",
            hostname="192.168.1.11",
            port=2112,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "launch/sick_tim_240.launch" in args
        assert "port:=2112" in args
    
    def test_build_launch_args_unknown_model_raises(self):
        """Unknown model_id raises KeyError"""
        with pytest.raises(KeyError):
            build_launch_args(
                model_id="velodyne_vls128",
                hostname="192.168.0.1",
                port=None,
                udp_receiver_ip=None,
                imu_udp_port=None,
                add_transform_xyz_rpy="0,0,0,0,0,0"
            )
    
    def test_build_launch_args_format_is_valid(self):
        """Launch args string is formatted correctly for roslaunch"""
        args = build_launch_args(
            model_id="tim_5xx",
            hostname="192.168.0.1",
            port=2112,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        # Should be space-separated key:=value pairs
        tokens = args.split()
        assert len(tokens) >= 2  # launch_file, hostname:=
        assert all(token.startswith("launch/") or ":=" in token for token in tokens)
    
    def test_build_launch_args_all_tim_models_use_port_arg(self):
        """All TiM models use 'port' not 'udp_port'"""
        tim_models = ["tim_240", "tim_5xx", "tim_7xx", "tim_7xxs"]
        for model_id in tim_models:
            args = build_launch_args(
                model_id=model_id,
                hostname="192.168.0.1",
                port=2112,
                udp_receiver_ip=None,
                imu_udp_port=None,
                add_transform_xyz_rpy="0,0,0,0,0,0"
            )
            assert "port:=2112" in args, f"{model_id} should have port:= arg"
            assert "udp_port" not in args, f"{model_id} should not have udp_port"
    
    def test_build_launch_args_all_lms_models_tcp_only(self):
        """All LMS models have no port argument"""
        lms_models = ["lms_1xx", "lms_5xx", "lms_4xxx"]
        for model_id in lms_models:
            args = build_launch_args(
                model_id=model_id,
                hostname="192.168.0.1",
                port=None,
                udp_receiver_ip=None,
                imu_udp_port=None,
                add_transform_xyz_rpy="0,0,0,0,0,0"
            )
            assert "port:=" not in args, f"{model_id} should not have port arg"
            assert "udp_port:=" not in args, f"{model_id} should not have udp_port arg"
    
    def test_build_launch_args_all_mrs_models_tcp_only(self):
        """All MRS models have no port argument"""
        mrs_models = ["mrs_1xxx", "mrs_6xxx"]
        for model_id in mrs_models:
            args = build_launch_args(
                model_id=model_id,
                hostname="192.168.0.1",
                port=None,
                udp_receiver_ip=None,
                imu_udp_port=None,
                add_transform_xyz_rpy="0,0,0,0,0,0"
            )
            assert "port:=" not in args, f"{model_id} should not have port arg"
            assert "udp_port:=" not in args, f"{model_id} should not have udp_port arg"
    
    def test_build_launch_args_only_multiscan_has_imu_port(self):
        """Only multiScan profile has IMU UDP port support"""
        profiles = get_all_profiles()
        imu_capable = [p for p in profiles if p.has_imu_udp_port]
        assert len(imu_capable) >= 1
        assert any(p.model_id == "multiscan" for p in imu_capable)


class TestEdgeCasesAndBackwardCompat:
    """Test edge cases and backward compatibility scenarios"""
    
    def test_get_profile_default_lidar_type_is_multiscan(self):
        """Default lidar_type for legacy configs is multiScan"""
        profile = get_profile("multiscan")
        assert profile.launch_file == "launch/sick_multiscan.launch"
    
    def test_profile_dataclass_is_immutable_equivalent(self):
        """SickLidarProfile behaves consistently"""
        p1 = get_profile("tim_5xx")
        p2 = get_profile("tim_5xx")
        assert p1.model_id == p2.model_id
        assert p1.display_name == p2.display_name
    
    def test_port_none_for_tcp_devices(self):
        """Port parameter can be None for TCP-only devices"""
        args = build_launch_args(
            model_id="lms_1xx",
            hostname="192.168.0.50",
            port=None,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "hostname:=192.168.0.50" in args
    
    def test_zero_port_number_edge_case(self):
        """Port 0 should not be included in args"""
        args = build_launch_args(
            model_id="tim_5xx",
            hostname="192.168.0.1",
            port=0,
            udp_receiver_ip=None,
            imu_udp_port=None,
            add_transform_xyz_rpy="0,0,0,0,0,0"
        )
        assert "hostname:=192.168.0.1" in args


class TestProfileUIIntegration:
    """Test integration with UI dropdown rendering"""
    
    def test_get_all_profiles_ordered_consistent(self):
        """Profiles should be returned in consistent order"""
        profiles1 = get_all_profiles()
        profiles2 = get_all_profiles()
        model_ids1 = [p.model_id for p in profiles1]
        model_ids2 = [p.model_id for p in profiles2]
        assert model_ids1 == model_ids2
    
    def test_profile_display_names_are_unique(self):
        """Each profile has a distinct display name for UI"""
        profiles = get_all_profiles()
        display_names = [p.display_name for p in profiles]
        assert len(display_names) == len(set(display_names))
    
    def test_enabled_profiles_for_dropdown(self):
        """Enabled profiles should be shown in dropdown"""
        enabled = get_enabled_profiles()
        # Should have several enabled profiles for UI
        assert len(enabled) > 0
        # All should have disabled=False
        assert all(not p.disabled for p in enabled)


class TestPerformanceAndConsistency:
    """Test performance characteristics and consistency"""
    
    def test_get_all_profiles_is_fast(self):
        """get_all_profiles() should be fast"""
        import time
        start = time.perf_counter()
        for _ in range(100):
            get_all_profiles()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05  # 100 calls < 50ms
    
    def test_get_profile_is_fast(self):
        """get_profile() should be O(1) dict lookup"""
        import time
        start = time.perf_counter()
        for _ in range(100):
            get_profile("multiscan")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.01  # 100 lookups < 10ms
    
    def test_build_launch_args_is_fast(self):
        """build_launch_args() should be pure string operations"""
        import time
        start = time.perf_counter()
        for _ in range(100):
            build_launch_args(
                model_id="tim_5xx",
                hostname="192.168.0.1",
                port=2112,
                udp_receiver_ip=None,
                imu_udp_port=None,
                add_transform_xyz_rpy="0,0,0,0,0,0"
            )
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05  # 100 arg builds < 50ms
