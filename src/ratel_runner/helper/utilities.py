from typing import Callable, Optional, Any
import typer


def run_once(func: Callable) -> Callable:
    """Decorator to ensure a function is called exactly one time"""
    def wrapper(*args, **kwargs):
        if not hasattr(wrapper, '__called'):
            setattr(wrapper, '__result', func(*args, **kwargs))
            setattr(wrapper, '__called', True)
        return getattr(wrapper, '__result')
    return wrapper


def callback_is_set(value):
    if value is None:
        raise typer.BadParameter("Required CLI option")
    return value


class LazyImporter:
    """Lazy import manager for CLI applications

    From yazyzw.com/optimizing-python-cli-apps-for-speed-my-top-techn/
    """

    def __init__(self, module_name: str, package: Optional[str] = None):
        self.module_name = module_name
        self.package = package
        self._module = None

    def __getattr__(self, name: str) -> Any:
        if self._module is None:
            self._module = __import__(self.module_name, fromlist=[''], level=0)
        return getattr(self._module, name)
