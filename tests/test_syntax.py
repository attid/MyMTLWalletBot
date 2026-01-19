import os
import ast
import pytest

def get_python_files(root_path):
    python_files = []
    for root, dirs, files in os.walk(root_path):
        # Skip hidden directories and virtual environments
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'venv']
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@pytest.mark.parametrize("file_path", get_python_files(PROJECT_ROOT))
def test_syntax(file_path):
    """
    Tries to compile every python file to catch SyntaxErrors and IndentationErrors.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    
    try:
        ast.parse(source, filename=file_path)
    except SyntaxError as e:
        pytest.fail(f"Syntax error in {file_path}: {e}")
