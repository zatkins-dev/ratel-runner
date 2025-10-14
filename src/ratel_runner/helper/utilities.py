from typing import Callable
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
