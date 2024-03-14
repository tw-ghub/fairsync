from threading import (
    get_ident,
    Lock as BaseLock,
)


def _pop_dict(dct):
    result = next(iter(dct))
    return result, dct.pop(result)


class RLock:
    def __init__(self):
        self.meta_lock = BaseLock()
        self.owner = 0
        self.lock_count = 0
        self.lockers = {}

    def acquire(self, blocking: bool = True, timeout: float = -1, *, count: int = 1):
        """
        Acquire the lock. Returns True if the lock was acquired or False if the acquire
        timed out or was not available immediately if blocking=False.

        Arguments:
            blocking: If True this method will wait for the lock to become available.
                      Otherwise, it will return False immediately if the lock is
                      not immediately available.
            timeout: A positive number of seconds to wait for the lock. If negative
                     this is interpreted as an indefinite wait. This argument
                     is ignored if blocking is False.
            count: The number of times to acquire the re-entrant lock. This is
                   equivalent to calling acquire() `count` times.
        """
        if count < 1:
            raise ValueError("lock count must be a positive integer")

        ident = get_ident()
        with self.meta_lock:
            if self.owner == 0:
                self.owner = ident
                self.lock_count = count
                return True
            if self.owner == ident:
                self.lock_count += count
                return True
            if not blocking:
                return False

            waiter = BaseLock()
            waiter.acquire()
            self.lockers[waiter] = (ident, count)

        if waiter.acquire(timeout=timeout):
            assert self.owner == ident and self.lock_count == count
            return True

        with self.meta_lock:
            if not self.lockers.pop(waiter, None):
                # If someone removed us from lockers then we were actually signalled
                # just happened to time out at the same time.
                assert self.owner == ident and self.lock_count == count
                return True

        assert self.owner != ident
        return False

    def release(self, *, count: int = 1) -> bool:
        """
        Releases the lock. Returns True if the current thread no longer controls
        the lock.

        Arguments:
            count: The number of times to release the re-entrant lock. This is
                   equivalent to calling release() `count` times.
        """
        if count < 1:
            raise ValueError("unlock count must be a positive integer")
        if self.owner != get_ident():
            raise RuntimeError("cannot release un-acquired lock")
        if count > self.lock_count:
            raise RuntimeError("cannot release lock at higher count than currently acquired")

        self.lock_count -= count
        if self.lock_count > 0:
            return False

        with self.meta_lock:
            if self.lockers:
                waiter, (self.owner, self.lock_count) = _pop_dict(self.lockers)
                waiter.release()
            else:
                self.owner = 0

        return True

    def yield_lock(self) -> bool:
        """
        Gives the lock to the next waiting thread and inserts itself at the
        end of the wait list. If there are no waiters this will not actually
        release the lock.
        """
        if self.owner != get_ident():
            raise RuntimeError("cannot yield un-acquired lock")
        if not self.lockers:
            return False
        lock_count = self.lock_count
        self.release(count=lock_count)
        self.acquire(count=lock_count)

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
