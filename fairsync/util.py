from queue import Queue

from .condition import Condition
from .lock import RLock


def make_fair(que: Queue) -> None:
    """
    Convert a queue.Queue object into a fair queue.

    Under the hood this just replaces its locks/condition variables with
    fair replacements to yield a fair queue.
    """
    lck = RLock()
    que.mutex = lck
    que.not_empty = Condition(lck)
    que.not_full = Condition(lck)
    que.all_tasks_done = Condition(lck)
