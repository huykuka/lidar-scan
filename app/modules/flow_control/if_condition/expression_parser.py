"""
Secure AST-based expression parser for conditional evaluation.

This module provides a sandboxed expression evaluator that only allows:
- Comparison operators: >, <, ==, !=, >=, <=
- Boolean operators: AND, OR, NOT (case-insensitive)
- Parentheses for grouping
- Variable access (from context dictionary)

NO eval() is used. All operations are validated through AST whitelist.
"""
import ast
from typing import Any, Dict


class ExpressionParser:
    """
    Safe expression evaluator using AST parsing with operation whitelist.
    
    Examples:
        >>> parser = ExpressionParser()
        >>> parser.evaluate("point_count > 1000", {"point_count": 1500})
        True
        >>> parser.evaluate("a > 5 AND b < 10", {"a": 10, "b": 8})
        True
    """
    
    def evaluate(self, expression: str, context: Dict[str, Any]) -> bool:
        """
        Evaluate a boolean expression with the given context.
        
        Args:
            expression: Boolean expression string
            context: Dictionary of variable values
            
        Returns:
            Boolean result of the expression
            
        Raises:
            SyntaxError: Invalid expression syntax
            ValueError: Disallowed operation (arithmetic, function calls, etc.)
            TypeError: Type mismatch in comparison
        """
        try:
            # Normalize boolean operators to lowercase (Python AST requirement)
            normalized = self._normalize_operators(expression)
            
            # Parse the expression into an AST
            tree = ast.parse(normalized, mode='eval')
            
            # Create evaluator with context
            evaluator = SafeExpressionEvaluator(context)
            
            # Evaluate the AST
            result = evaluator.visit(tree.body)
            
            # Ensure result is boolean
            return bool(result)
            
        except SyntaxError as e:
            raise SyntaxError(f"Expression syntax error: {e}")
        except Exception as e:
            # Re-raise with context
            raise
    
    def _normalize_operators(self, expression: str) -> str:
        """
        Normalize boolean operators to lowercase for Python AST parsing.
        
        Replaces case-insensitive AND/OR/NOT with lowercase and/or/not.
        Uses word boundaries to avoid replacing substrings within variable names.
        
        Args:
            expression: Original expression string
            
        Returns:
            Normalized expression with lowercase operators
        """
        import re
        
        # Replace case-insensitive operators with lowercase versions
        # Use word boundaries \b to match whole words only
        normalized = expression
        normalized = re.sub(r'\bAND\b', 'and', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bOR\b', 'or', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\bNOT\b', 'not', normalized, flags=re.IGNORECASE)
        
        return normalized


class SafeExpressionEvaluator(ast.NodeVisitor):
    """
    AST visitor that only allows safe comparison and boolean operations.
    
    Whitelisted node types:
    - Compare: >, <, ==, !=, >=, <=
    - BoolOp: AND, OR
    - UnaryOp: NOT
    - Name: variable access
    - Constant: literal values (numbers, strings, booleans)
    """
    
    # Allowed comparison operators
    ALLOWED_COMPARE_OPS = {
        ast.Gt: lambda a, b: a > b,
        ast.Lt: lambda a, b: a < b,
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.GtE: lambda a, b: a >= b,
        ast.LtE: lambda a, b: a <= b,
    }
    
    # Allowed boolean operators
    ALLOWED_BOOL_OPS = {
        ast.And: lambda values: all(values),
        ast.Or: lambda values: any(values),
    }
    
    def __init__(self, context: Dict[str, Any]):
        """
        Initialize evaluator with variable context.
        
        Args:
            context: Dictionary of variable names to values
        """
        self.context = context
    
    def visit_Compare(self, node: ast.Compare) -> bool:
        """
        Evaluate comparison operations (>, <, ==, etc.).
        
        Args:
            node: AST Compare node
            
        Returns:
            Boolean result of comparison
            
        Raises:
            ValueError: If comparison operator is not allowed
            TypeError: If operands cannot be compared
        """
        # Get left operand value
        left = self.visit(node.left)
        
        # Handle None values gracefully
        if left is None:
            return False
        
        # Evaluate all comparisons (can be chained: a < b < c)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            
            # Handle None values
            if right is None:
                return False
            
            # Check if operator is allowed
            if type(op) not in self.ALLOWED_COMPARE_OPS:
                raise ValueError(f"Comparison operator {type(op).__name__} not allowed")
            
            # Perform comparison
            try:
                compare_func = self.ALLOWED_COMPARE_OPS[type(op)]
                if not compare_func(left, right):
                    return False
            except TypeError as e:
                raise TypeError(f"Cannot compare {type(left).__name__} and {type(right).__name__}: {e}")
            
            # For chained comparisons, update left for next iteration
            left = right
        
        return True
    
    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        """
        Evaluate boolean operations (AND, OR).
        
        Args:
            node: AST BoolOp node
            
        Returns:
            Boolean result of operation
            
        Raises:
            ValueError: If boolean operator is not allowed
        """
        if type(node.op) not in self.ALLOWED_BOOL_OPS:
            raise ValueError(f"Boolean operator {type(node.op).__name__} not allowed")
        
        # Evaluate all operands
        values = [self.visit(value) for value in node.values]
        
        # Apply boolean operation
        bool_func = self.ALLOWED_BOOL_OPS[type(node.op)]
        return bool_func(values)
    
    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        """
        Evaluate unary operations (NOT).
        
        Args:
            node: AST UnaryOp node
            
        Returns:
            Result of unary operation
            
        Raises:
            ValueError: If unary operator is not allowed (only NOT is allowed)
        """
        if not isinstance(node.op, ast.Not):
            raise ValueError(f"Unary operator {type(node.op).__name__} not allowed")
        
        operand = self.visit(node.operand)
        return not operand
    
    def visit_Name(self, node: ast.Name) -> Any:
        """
        Resolve variable name from context.
        
        Args:
            node: AST Name node
            
        Returns:
            Value of the variable from context, or None if not found
        """
        return self.context.get(node.id)
    
    def visit_Constant(self, node: ast.Constant) -> Any:
        """
        Return constant literal value.
        
        Args:
            node: AST Constant node (numbers, strings, True/False, None)
            
        Returns:
            The constant value
        """
        return node.value
    
    def visit_Expr(self, node: ast.Expr) -> Any:
        """Visit expression wrapper node."""
        return self.visit(node.value)
    
    def generic_visit(self, node: ast.AST) -> Any:
        """
        Reject any AST node type not explicitly whitelisted.
        
        Args:
            node: AST node
            
        Raises:
            ValueError: Operation not allowed
        """
        raise ValueError(f"Operation {type(node).__name__} not allowed in expression")
