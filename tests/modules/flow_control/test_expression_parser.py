"""
Unit tests for the IF node expression parser.

Tests the AST-based expression evaluator for security, correctness, and edge cases.
"""
import pytest
from app.modules.flow_control.if_condition.expression_parser import ExpressionParser


class TestExpressionParserBasics:
    """Test basic comparison operations."""
    
    def test_simple_greater_than_true(self):
        parser = ExpressionParser()
        context = {"point_count": 1500}
        result = parser.evaluate("point_count > 1000", context)
        assert result is True
    
    def test_simple_greater_than_false(self):
        parser = ExpressionParser()
        context = {"point_count": 500}
        result = parser.evaluate("point_count > 1000", context)
        assert result is False
    
    def test_less_than(self):
        parser = ExpressionParser()
        context = {"intensity_avg": 50}
        result = parser.evaluate("intensity_avg < 100", context)
        assert result is True
    
    def test_equals(self):
        parser = ExpressionParser()
        context = {"external_state": True}
        result = parser.evaluate("external_state == True", context)
        assert result is True
    
    def test_not_equals(self):
        parser = ExpressionParser()
        context = {"sensor_name": "lidar_2"}
        result = parser.evaluate('sensor_name != "lidar_1"', context)
        assert result is True
    
    def test_greater_than_or_equal(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        result = parser.evaluate("point_count >= 1000", context)
        assert result is True
    
    def test_less_than_or_equal(self):
        parser = ExpressionParser()
        context = {"variance": 0.01}
        result = parser.evaluate("variance <= 0.01", context)
        assert result is True


class TestBooleanOperators:
    """Test AND, OR, NOT operations."""
    
    def test_and_both_true(self):
        parser = ExpressionParser()
        context = {"point_count": 1500, "intensity_avg": 75}
        result = parser.evaluate("point_count > 1000 AND intensity_avg > 50", context)
        assert result is True
    
    def test_and_first_false(self):
        parser = ExpressionParser()
        context = {"point_count": 500, "intensity_avg": 75}
        result = parser.evaluate("point_count > 1000 AND intensity_avg > 50", context)
        assert result is False
    
    def test_or_both_false(self):
        parser = ExpressionParser()
        context = {"point_count": 500, "intensity_avg": 30}
        result = parser.evaluate("point_count > 1000 OR intensity_avg > 50", context)
        assert result is False
    
    def test_or_one_true(self):
        parser = ExpressionParser()
        context = {"point_count": 1500, "intensity_avg": 30}
        result = parser.evaluate("point_count > 1000 OR intensity_avg > 50", context)
        assert result is True
    
    def test_not_operator(self):
        parser = ExpressionParser()
        context = {"timestamp": 12345678}
        result = parser.evaluate("NOT (timestamp < 10000000)", context)
        assert result is True


class TestCaseInsensitivity:
    """Test that operators are case-insensitive."""
    
    def test_lowercase_and(self):
        parser = ExpressionParser()
        context = {"a": 10, "b": 20}
        result = parser.evaluate("a > 5 and b > 15", context)
        assert result is True
    
    def test_mixed_case_or(self):
        parser = ExpressionParser()
        context = {"a": 10, "b": 5}
        result = parser.evaluate("a > 15 Or b > 3", context)
        assert result is True
    
    def test_uppercase_not(self):
        parser = ExpressionParser()
        context = {"value": 10}
        result = parser.evaluate("NOT value < 5", context)
        assert result is True


class TestParentheses:
    """Test grouped conditions with parentheses."""
    
    def test_simple_grouping(self):
        parser = ExpressionParser()
        context = {"a": 10, "b": 20, "c": 30}
        result = parser.evaluate("(a > 5 OR b < 15) AND c > 25", context)
        assert result is True
    
    def test_nested_grouping(self):
        parser = ExpressionParser()
        context = {"a": 10, "b": 20, "c": 30, "d": 40}
        result = parser.evaluate("((a > 5 OR b < 15) AND c > 25) OR d < 35", context)
        assert result is True
    
    def test_precedence_without_parentheses(self):
        """AND has higher precedence than OR."""
        parser = ExpressionParser()
        context = {"a": 10, "b": 5, "c": 30}
        # Should be: False OR (False AND True) = False OR False = False
        result = parser.evaluate("a > 15 OR b < 3 AND c > 20", context)
        assert result is False


class TestMissingFields:
    """Test behavior when context variables are missing."""
    
    def test_missing_field_comparison(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        # missing_field is None, None > 100 should be False
        result = parser.evaluate("missing_field > 100", context)
        assert result is False
    
    def test_missing_field_in_and(self):
        parser = ExpressionParser()
        context = {"point_count": 1500}
        result = parser.evaluate("point_count > 1000 AND missing_field > 100", context)
        assert result is False


class TestTypeMismatches:
    """Test type error handling."""
    
    def test_string_number_comparison(self):
        parser = ExpressionParser()
        context = {"string_field": "hello"}
        with pytest.raises(Exception):  # Should raise TypeError
            parser.evaluate("string_field > 100", context)
    
    def test_none_comparison(self):
        parser = ExpressionParser()
        context = {"value": None}
        # None < 100 should be False (handled gracefully)
        result = parser.evaluate("value < 100", context)
        assert result is False


class TestSyntaxErrors:
    """Test invalid expression syntax."""
    
    def test_missing_operand(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        with pytest.raises(SyntaxError):
            parser.evaluate("point_count >", context)
    
    def test_invalid_operator(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        with pytest.raises(Exception):  # SyntaxError or similar
            parser.evaluate("point_count >< 1000", context)
    
    def test_unbalanced_parentheses(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        with pytest.raises(SyntaxError):
            parser.evaluate("(point_count > 1000 AND intensity_avg > 50", context)


class TestDisallowedOperations:
    """Test that unsafe operations are rejected."""
    
    def test_arithmetic_addition(self):
        parser = ExpressionParser()
        context = {"point_count": 1000}
        with pytest.raises(ValueError):
            parser.evaluate("point_count + 500 > 1000", context)
    
    def test_function_call(self):
        parser = ExpressionParser()
        context = {}
        with pytest.raises(ValueError):
            parser.evaluate("len([1, 2, 3]) > 2", context)
    
    def test_lambda_expression(self):
        parser = ExpressionParser()
        context = {}
        with pytest.raises(ValueError):
            parser.evaluate("(lambda x: x > 5)(10)", context)
    
    def test_import_statement(self):
        parser = ExpressionParser()
        context = {}
        with pytest.raises(Exception):
            parser.evaluate("__import__('os').system('echo test')", context)


class TestComplexExpressions:
    """Test real-world complex expressions."""
    
    def test_quality_gate_expression(self):
        parser = ExpressionParser()
        context = {
            "point_count": 5500,
            "intensity_avg": 75,
            "variance": 0.02,
            "external_state": True
        }
        result = parser.evaluate(
            "point_count > 1000 AND intensity_avg >= 50 AND variance > 0.01 AND external_state == True",
            context
        )
        assert result is True
    
    def test_complex_with_grouping(self):
        parser = ExpressionParser()
        context = {
            "point_count": 5500,
            "variance": 0.005,
            "external_state": True
        }
        result = parser.evaluate(
            "(variance > 0.01 OR point_count > 5000) AND external_state == True",
            context
        )
        assert result is True


class TestExpressionCaching:
    """Test that expressions can be parsed once and evaluated multiple times."""
    
    def test_parse_once_evaluate_many(self):
        parser = ExpressionParser()
        expr = "point_count > 1000 AND intensity_avg > 50"
        
        # First evaluation
        context1 = {"point_count": 1500, "intensity_avg": 75}
        result1 = parser.evaluate(expr, context1)
        assert result1 is True
        
        # Second evaluation with different context
        context2 = {"point_count": 500, "intensity_avg": 75}
        result2 = parser.evaluate(expr, context2)
        assert result2 is False
