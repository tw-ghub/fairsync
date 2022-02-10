from queue import Queue
from typing import TypeVar

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


def test():
    import threading
    import time
    from queue import Queue

    QUEUE_SIZE = 100
    WAIT_TIMEOUT = 1000.0
    THREAD_COUNT = 100
    OPS_PER_THREAD = 1000

    q = Queue()
    #make_fair(q)
    for i in range(QUEUE_SIZE):
        q.put(i)


    def work():
        for _ in range(OPS_PER_THREAD):
            # Uncomment this to alleviate the issue, allowing other threads to access queue elements
            # time.sleep(1e-9)
            val = q.get(timeout=WAIT_TIMEOUT)
            #time.sleep(0.001)
            q.put(val)


    threads = [threading.Thread(target=work) for _ in range(THREAD_COUNT)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    test()
