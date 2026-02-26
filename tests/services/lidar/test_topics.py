"""
Unit tests for topics module - topic prefix generation and management.
"""
import pytest

from app.services.shared.topics import (
    slugify_topic_prefix,
    generate_unique_topic_prefix,
    TopicRegistry
)


class TestSlugifyTopicPrefix:
    """Tests for slugify_topic_prefix function"""
    
    def test_basic_alphanumeric(self):
        """Test with basic alphanumeric string"""
        result = slugify_topic_prefix("front_lidar")
        assert result == "front_lidar"
    
    def test_spaces_to_underscores(self):
        """Test that spaces are converted to underscores"""
        result = slugify_topic_prefix("Front Lidar #1")
        assert result == "Front_Lidar_1"
    
    def test_special_characters_removed(self):
        """Test that special characters are replaced with underscores"""
        result = slugify_topic_prefix("sensor@#$%name")
        assert result == "sensor_name"
    
    def test_multiple_underscores_collapsed(self):
        """Test that multiple underscores are collapsed to one"""
        result = slugify_topic_prefix("test___sensor___name")
        assert result == "test_sensor_name"
    
    def test_leading_trailing_stripped(self):
        """Test that leading/trailing underscores and hyphens are stripped"""
        result = slugify_topic_prefix("__sensor_name__")
        assert result == "sensor_name"
        
        result = slugify_topic_prefix("--sensor-name--")
        assert result == "sensor-name"
    
    def test_hyphens_preserved(self):
        """Test that hyphens are preserved"""
        result = slugify_topic_prefix("front-lidar-sensor")
        assert result == "front-lidar-sensor"
    
    def test_empty_string_returns_default(self):
        """Test that empty string returns 'sensor'"""
        assert slugify_topic_prefix("") == "sensor"
        assert slugify_topic_prefix("   ") == "sensor"
    
    def test_only_special_chars_returns_default(self):
        """Test that string with only special characters returns 'sensor'"""
        result = slugify_topic_prefix("@#$%^&*()")
        assert result == "sensor"
    
    def test_numbers_preserved(self):
        """Test that numbers are preserved"""
        result = slugify_topic_prefix("lidar123")
        assert result == "lidar123"
        
        result = slugify_topic_prefix("sensor_01_rear")
        assert result == "sensor_01_rear"
    
    def test_mixed_case_preserved(self):
        """Test that case is preserved"""
        result = slugify_topic_prefix("FrontLidar")
        assert result == "FrontLidar"
    
    def test_unicode_replaced(self):
        """Test that unicode characters are replaced"""
        result = slugify_topic_prefix("sensor™_lidar™")
        assert "sensor" in result
        assert "lidar" in result
    
    def test_whitespace_variants(self):
        """Test various whitespace characters"""
        result = slugify_topic_prefix("front\tlidar\nrear")
        assert result == "front_lidar_rear"


class TestGenerateUniqueTopicPrefix:
    """Tests for generate_unique_topic_prefix function"""
    
    def test_unique_prefix_returned_as_is(self):
        """Test that unique prefix is returned without modification"""
        existing = {"rear", "left"}
        result = generate_unique_topic_prefix("front", "abc123", existing)
        assert result == "front"
    
    def test_collision_adds_sensor_id_suffix(self):
        """Test that collision adds sensor_id suffix"""
        existing = {"front"}
        result = generate_unique_topic_prefix("front", "abc123", existing)
        assert result == "front_abc123"
    
    def test_double_collision_adds_number(self):
        """Test that double collision adds incrementing number"""
        existing = {"front", "front_abc123"}
        result = generate_unique_topic_prefix("front", "abc123", existing)
        assert result == "front_abc123_2"
    
    def test_multiple_collisions(self):
        """Test multiple collisions increment correctly"""
        existing = {"front", "front_abc123", "front_abc123_2", "front_abc123_3"}
        result = generate_unique_topic_prefix("front", "abc123", existing)
        assert result == "front_abc123_4"
    
    def test_sensor_id_truncated_to_8_chars(self):
        """Test that sensor_id suffix is truncated to 8 characters"""
        existing = {"sensor"}
        result = generate_unique_topic_prefix("sensor", "verylongsensorid12345", existing)
        # Should use first 8 chars after slugifying
        assert result == "sensor_verylong"
    
    def test_slugification_applied(self):
        """Test that slugification is applied to input"""
        existing = set()
        result = generate_unique_topic_prefix("Front Lidar #1", "abc", existing)
        assert result == "Front_Lidar_1"
    
    def test_empty_sensor_id_uses_sensor_default(self):
        """Test that empty sensor_id slugifies to 'sensor' (the default)"""
        existing = {"sensor"}
        result = generate_unique_topic_prefix("sensor", "", existing)
        # Empty string slugifies to "sensor", so we get "sensor_sensor"
        assert result == "sensor_sensor"
    
    def test_special_chars_in_sensor_id_slugified(self):
        """Test that special characters in sensor_id are slugified"""
        existing = {"front"}
        result = generate_unique_topic_prefix("front", "abc@#$123", existing)
        assert result == "front_abc_123"
    
    def test_existing_set_not_modified(self):
        """Test that existing prefixes set is not modified"""
        existing = {"rear"}
        original_set = existing.copy()
        generate_unique_topic_prefix("front", "abc", existing)
        assert existing == original_set
    
    def test_empty_existing_set(self):
        """Test with empty existing set"""
        result = generate_unique_topic_prefix("front", "abc", set())
        assert result == "front"


class TestTopicRegistry:
    """Tests for TopicRegistry class"""
    
    def test_register_unique_prefix(self):
        """Test registering a unique prefix"""
        registry = TopicRegistry()
        result = registry.register("front", "sensor1")
        assert result == "front"
        assert "front" in registry.get_all()
    
    def test_register_duplicate_adds_suffix(self):
        """Test that registering duplicate adds suffix"""
        registry = TopicRegistry()
        first = registry.register("front", "sensor1")
        second = registry.register("front", "sensor2")
        
        assert first == "front"
        assert second == "front_sensor2"
        assert len(registry.get_all()) == 2
    
    def test_register_multiple_sensors(self):
        """Test registering multiple sensors"""
        registry = TopicRegistry()
        
        prefixes = [
            registry.register("front", "s1"),
            registry.register("rear", "s2"),
            registry.register("left", "s3"),
            registry.register("right", "s4")
        ]
        
        assert prefixes == ["front", "rear", "left", "right"]
        assert len(registry.get_all()) == 4
    
    def test_register_with_collisions(self):
        """Test collision handling in registry"""
        registry = TopicRegistry()
        
        p1 = registry.register("sensor", "id1")
        p2 = registry.register("sensor", "id2")
        p3 = registry.register("sensor", "id3")
        
        assert p1 == "sensor"
        assert p2 == "sensor_id2"
        assert p3 == "sensor_id3"
    
    def test_unregister(self):
        """Test unregistering a prefix"""
        registry = TopicRegistry()
        registry.register("front", "s1")
        
        registry.unregister("front")
        assert "front" not in registry.get_all()
    
    def test_unregister_allows_reuse(self):
        """Test that unregistering allows prefix reuse"""
        registry = TopicRegistry()
        
        registry.register("front", "s1")
        registry.unregister("front")
        result = registry.register("front", "s2")
        
        assert result == "front"  # Should be able to reuse
    
    def test_unregister_nonexistent(self):
        """Test unregistering non-existent prefix (should not error)"""
        registry = TopicRegistry()
        registry.unregister("nonexistent")  # Should not raise
        assert "nonexistent" not in registry.get_all()
    
    def test_clear(self):
        """Test clearing all prefixes"""
        registry = TopicRegistry()
        
        registry.register("front", "s1")
        registry.register("rear", "s2")
        registry.register("left", "s3")
        
        registry.clear()
        assert len(registry.get_all()) == 0
    
    def test_clear_allows_fresh_start(self):
        """Test that clear allows fresh registration"""
        registry = TopicRegistry()
        
        registry.register("front", "s1")
        registry.clear()
        result = registry.register("front", "s2")
        
        assert result == "front"
    
    def test_get_all_returns_copy(self):
        """Test that get_all returns a copy, not reference"""
        registry = TopicRegistry()
        registry.register("front", "s1")
        
        all_prefixes = registry.get_all()
        all_prefixes.add("hacked")
        
        # Original registry should not be affected
        assert "hacked" not in registry.get_all()
    
    def test_register_with_desired_prefix_requiring_slugification(self):
        """Test registration with prefix needing slugification"""
        registry = TopicRegistry()
        result = registry.register("Front Lidar #1", "s1")
        assert result == "Front_Lidar_1"
    
    def test_sequential_collisions(self):
        """Test sequential collision handling"""
        registry = TopicRegistry()
        
        # Register same desired prefix multiple times
        results = [registry.register("test", f"id{i}") for i in range(5)]
        
        assert results[0] == "test"
        assert results[1] == "test_id1"
        assert results[2] == "test_id2"
        assert results[3] == "test_id3"
        assert results[4] == "test_id4"
    
    def test_empty_initialization(self):
        """Test that registry starts empty"""
        registry = TopicRegistry()
        assert len(registry.get_all()) == 0
