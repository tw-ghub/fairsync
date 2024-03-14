import time
from threading import (
    get_ident,
    Lock as BaseLock,
)
from typing import Callable, Optional

from .lock import RLock


def _pop_dict(dct):
    result = next(iter(dct))
    return result, dct.pop(result)


class Condition:
    """
    Fair condition variable implementation. If passing a lock to the constructor
    it is expected to be a fairsync.lock.RLock instance.
    """
    def __init__(self, lock: Optional[RLock] = None):
        if lock is not None:
            if not isinstance(lock, RLock):
                raise ValueError("Can only accept fairsync.lock.RLock lock")
        self.lock = lock or RLock()
        self.waiters = {}

    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()

    def wait(self, timeout: float = -1) -> bool:
        """
        Wait for the condition variable to be signalled. Returns True if the
        condition was signalled or False if the wait timeout expired.

        Arguments:
            timeout: If a positive number this will be interpreted as
                     a timeout in seconds. Negative numbers will be interpreted
                     as an indefinite wait.
        """
        ident = get_ident()
        if self.lock.owner != ident:
            raise RuntimeError("cannot wait on un-acquired lock")
        waiter = BaseLock()
        waiter.acquire()
        count = self.lock.lock_count
        with self.lock.meta_lock:
            self.waiters[waiter] = (ident, count)
        self.lock.release(count=self.lock.lock_count)

        if waiter.acquire(timeout=timeout):
            assert self.lock.owner == ident and self.lock.lock_count == count
            return True

        result = False
        with self.lock.meta_lock:
            if self.waiters.pop(waiter):
                # No one notified us and we timed out. Promote ourselves to
                # waiting for the lock so we can exit in failure.
                self.lock.lockers[waiter] = (ident, count)
            elif waiter in self.lock.lockers:
                # We were notified but haven't received the lock yet, keep waiting.
                result = True
            else:
                # Someone just gave us the lock
                assert self.lock.owner == ident and self.lock.lock_count == count
                return True

        waiter.acquire()
        assert self.lock.owner == ident and self.lock.lock_count == count
        return result

    def wait_for(self, predicate: Callable[[], bool], timeout=-1) -> bool:
        """
        Waits for the callable predicate to evaluate to True, calling wait()
        inbetween evaluations. Returns True if the predicate returned True
        or False if the wait timeout expired.
        """
        start_time = None
        result = predicate()
        while not result:
            wait_time = -1
            if timeout > 0:
                if start_time is None:
                    start_time = time.monotonic()
                    wait_time = timeout
                else:
                    wait_time = time.monotonic() - start_time
                    if wait_time <= 0:
                        break

            self.wait(timeout=wait_time)
            result = predicate()

        return result

    def notify(self, n=1):
        """
        Notify `n` threads to wake up.
        """
        if self.lock.owner != get_ident():
            raise RuntimeError("cannot notify on un-acquired lock")
        with self.lock.meta_lock:
            for _ in range(min(n, len(self.waiters))):
                waiter, (ident, count) = _pop_dict(self.waiters)
                self.lock.lockers[waiter] = (ident, count)

    def notify_all(self):
        """
        Notify all threads to wake up.
        """
        if self.lock.owner != get_ident():
            raise RuntimeError("cannot notify on un-acquired lock")
        with self.lock.meta_lock:
            self.lock.lockers.update(self.waiters)
            self.waiters.clear()
