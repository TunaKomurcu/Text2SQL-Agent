"""
Error Analyzer - SQL error analysis and suggestions
"""

import re
from typing import Dict, List


class SQLErrorAnalyzer:
    """SQL error analysis helper - ENHANCED VERSION"""
    
    def analyze_error(self, error_message: str, sql_query: str, schema_pool: Dict) -> Dict:
        """
        Analyze SQL errors, including timestamp issues.
        
        Args:
            error_message: Error message from database
            sql_query: SQL query that caused the error
            schema_pool: Schema pool dictionary
            
        Returns:
            dict: Error analysis with type, message, suggestions
        """
        error_lower = error_message.lower()
        
        # Timestamp format error
        if "invalid input syntax for type timestamp" in error_lower:
            return {
                "error_type": "timestamp_format_error",
                "message": "Invalid date/time format",
                "problematic_parts": self._extract_timestamp_value(error_message),
                "suggestions": self._suggest_timestamp_fixes(error_message, sql_query),
                "needs_clarification": True
            }
        # Missing table error
        elif "table" in error_lower and "does not exist" in error_lower:
            return {
                "error_type": "missing_table",
                "message": error_message,
                "problematic_parts": self._extract_table_name(error_message),
                "suggestions": self._suggest_tables(schema_pool, error_message),
                "needs_clarification": True
            }
        # Missing column error
        elif "column" in error_lower and "does not exist" in error_lower:
            return {
                "error_type": "missing_column", 
                "message": error_message,
                "problematic_parts": self._extract_column_name(error_message),
                "suggestions": self._suggest_columns(schema_pool, error_message),
                "needs_clarification": True
            }
        # Syntax error
        else:
            return {
                "error_type": "syntax_error",
                "message": error_message,
                "problematic_parts": [],
                "suggestions": self._suggest_syntax_fixes(error_message),
                "needs_clarification": False  # Suggest automatic fixes
            }
    
    def _extract_timestamp_value(self, error_message: str) -> List[str]:
        """Extract values from a timestamp error message."""
        # Find invalid values like "asdaba"
        matches = re.findall(r"\"([^\"]+)\"", error_message)
        return matches if matches else []
    
    def _suggest_timestamp_fixes(self, error_message: str, sql_query: str) -> List[Dict]:
        """Suggestions for timestamp formatting fixes."""
        suggestions = []
        
        # Suggest valid timestamp formats
        timestamp_formats = [
            "YYYY-MM-DD",
            "YYYY-MM-DD HH:MI:SS", 
            "DD.MM.YYYY",
            "DD/MM/YYYY"
        ]
        
        for fmt in timestamp_formats:
            suggestions.append({
                "suggested": fmt,
                "type": "timestamp_format",
                "description": f"Accepted date format: {fmt}",
                "confidence": 80
            })
        
        # Suggest removing the condition
        suggestions.append({
            "suggested": "REMOVE_CONDITION",
            "type": "remove_condition", 
            "description": "Remove this condition and return all rows",
            "confidence": 60
        })
        
        return suggestions
    
    def _suggest_syntax_fixes(self, error_message: str) -> List[Dict]:
        """Suggestions for syntax errors."""
        return [
            {
                "suggested": "simplify_query",
                "type": "simplify",
                "description": "Simplify the query",
                "confidence": 70
            },
            {
                "suggested": "retry_generation", 
                "type": "retry",
                "description": "Regenerate the SQL",
                "confidence": 80
            }
        ]
    
    def _extract_table_name(self, error_message: str) -> List[str]:
        """Extract table name from an error message."""
        matches = re.findall(r"table \"([^\"]+)\"", error_message, re.IGNORECASE)
        return matches if matches else []
    
    def _extract_column_name(self, error_message: str) -> List[str]:
        """Extract column name from an error message."""
        matches = re.findall(r"column \"([^\"]+)\"", error_message, re.IGNORECASE)
        return matches if matches else []
    
    def _suggest_tables(self, schema_pool: Dict, error_message: str) -> List[Dict]:
        """Create table suggestions based on schema pool."""
        problematic_tables = self._extract_table_name(error_message)
        suggestions = []
        
        for table in problematic_tables:
            for existing_table in schema_pool.keys():
                # Simple similarity check
                if table.lower() in existing_table.lower() or existing_table.lower() in table.lower():
                    suggestions.append({
                        "suggested": existing_table,
                        "confidence": 80,
                        "reason": "Similar table name"
                    })
        
        return suggestions[:5]
    
    def _suggest_columns(self, schema_pool: Dict, error_message: str) -> List[Dict]:
        """Create column suggestions based on schema pool."""
        problematic_columns = self._extract_column_name(error_message)
        suggestions = []
        
        for column in problematic_columns:
            for table, table_data in schema_pool.items():
                # Handle both dict and list formats
                columns = []
                if isinstance(table_data, dict):
                    columns = table_data.get('columns', [])
                elif isinstance(table_data, list):
                    columns = table_data
                    
                for existing_column in columns:
                    # Simple similarity check
                    if column.lower() in existing_column.lower() or existing_column.lower() in column.lower():
                        suggestions.append({
                            "suggested": existing_column,
                            "table": table,
                            "confidence": 80,
                            "reason": "Similar column name"
                        })
        
        return suggestions[:5]
