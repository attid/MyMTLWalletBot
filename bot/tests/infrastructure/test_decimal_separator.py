"""
Tests for decimal separator support (comma and dot).

These tests verify that the bot correctly parses amounts with both:
- Dot as decimal separator (0.5)
- Comma as decimal separator (0,5)
"""

from infrastructure.utils.stellar_utils import my_float


class TestMyFloat:
    """Tests for my_float function."""
    
    def test_dot_decimal_separator(self):
        """Test that dot works as decimal separator."""
        assert my_float("0.5") == 0.5
        assert my_float("10.25") == 10.25
        assert my_float("1000.123") == 1000.123
    
    def test_comma_decimal_separator(self):
        """Test that comma works as decimal separator."""
        assert my_float("0,5") == 0.5
        assert my_float("10,25") == 10.25
        assert my_float("1000,123") == 1000.123
    
    def test_integer_values(self):
        """Test integer values work correctly."""
        assert my_float("100") == 100.0
        assert my_float("0") == 0.0
        assert my_float("999999") == 999999.0
    
    def test_none_value(self):
        """Test that None returns 0.0."""
        assert my_float(None) == 0.0
    
    def test_unlimited_value(self):
        """Test that 'unlimited' returns infinity."""
        assert my_float("unlimited") == float('inf')
    
    def test_numeric_input(self):
        """Test that numeric input works (int, float)."""
        assert my_float(0.5) == 0.5
        assert my_float(100) == 100.0
    
    def test_edge_cases(self):
        """Test edge cases with small and large numbers."""
        assert my_float("0,001") == 0.001
        assert my_float("0.001") == 0.001
        assert my_float("999999,99") == 999999.99
        assert my_float("999999.99") == 999999.99
