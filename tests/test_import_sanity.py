import os
import pytest
import importlib
import sys

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

def get_python_modules(root_path):
    modules = []
    for root, dirs, files in os.walk(root_path):
        # Skip hidden directories, venv, and __pycache__
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'venv' and d != '__pycache__']
        
        for file in files:
            if file.endswith('.py') and file != '__init__.py':
                # Convert path to module dotted path
                rel_path = os.path.relpath(os.path.join(root, file), root_path)
                module_name = rel_path.replace(os.path.sep, '.')[:-3]
                
                # Skip tests themselves to avoid recursion issues or test discovery issues
                if module_name.startswith('tests.'):
                    continue
                    
                modules.append(module_name)
    return modules

@pytest.mark.parametrize("module_name", get_python_modules(PROJECT_ROOT))
def test_import_sanity(module_name):
    """
    Tries to import every python module to catch NameError, ImportError, SyntaxError at module level.
    """
    try:
        importlib.import_module(module_name)
    except (NameError, ImportError, AttributeError, SyntaxError) as e:
        pytest.fail(f"Failed to import {module_name}: {e}")
    except Exception as e:
        # Other runtime errors during import (e.g. database connection init at top level) 
        # might be ignored or handled, but ideally top level code shouldn't do side effects.
        # For now, we fail on them too to encourage clean modules.
        pytest.fail(f"Runtime error during import of {module_name}: {e}")
