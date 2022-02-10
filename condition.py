from collections import deque
from threading import (
    get_ident,
    Lock,
)


def _pop_dict(dct):
    result = next(iter(dct))
    return result, dct.pop(result)


class FairConditionRLock:
    def __init__(self):
        self.meta_lock = Lock()
        self.owner = 0
        self.lock_count = 0
        self.lockers = {}
        self.waiters = {}

    def acquire(self, blocking=True, timeout=-1, count=1):
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

            waiter = Lock()
            waiter.acquire()
            self.lockers[waiter] = (ident, count)

        if waiter.acquire(timeout=timeout):
            assert self.owner == ident and self.lock_count == count
            return True

        with self.meta_lock:
            if not self.lockers.pop(waiter, None):
                # If someone removed us from lockers then we were actually signalled
                # just happened to time out at the sameish time.
                assert self.owner == ident and self.lock_count == count
                return True

        assert self.owner != ident
        return False

    def release(self, count=1):
        if count < 1:
            raise ValueError("unlock count must be a positive integer")
        if self.owner != get_ident():
            raise RuntimeError("cannot release un-acquired lock")
        if count > self.lock_count:
            raise RuntimeError("cannot release lock at higher count than currently acquired")

        self.lock_count -= count
        if self.lock_count == 0:
            with self.meta_lock:
                if self.lockers:
                    waiter, (self.owner, self.lock_count) = _pop_dict(self.lockers)
                    waiter.release()
                else:
                    self.owner = 0

    def yield_lock(self) -> bool:
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

    def wait(self, timeout=-1):
        ident = get_ident()
        if self.owner != ident:
            raise RuntimeError("cannot wait on un-acquired lock")
        waiter = Lock()
        waiter.acquire()
        count = self.lock_count
        with self.meta_lock:
            self.waiters[waiter] = (ident, count)
        self.release(count=self.lock_count)

        if waiter.acquire(timeout=timeout):
            assert self.owner == ident and self.lock_count == count
            return True

        result = False
        with self.meta_lock:
            if self.waiters.pop(waiter):
                # No one notified us and we timed out. Promote ourselves to
                # waiting for the lock so we can exit in failure.
                self.lockers[waiter] = (ident, count)
            elif waiter in self.lockers:
                # We were notified but haven't received the lock yet, keep waiting.
                result = True
            else:
                # Someone just gave us the lock
                assert self.owner == ident and self.lock_count == count
                return True

        waiter.acquire()
        assert self.owner == ident and self.lock_count == count
        return result

    def wait_for(self, predicate, timeout=-1):
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
        if self.owner != get_ident():
            raise RuntimeError("cannot notify on un-acquired lock")
        with self.meta_lock:
            for _ in range(min(n, len(self.waiters))):
                waiter, (ident, count) = _pop_dict(self.waiters)
                self.lockers[waiter] = (ident, count)

    def notify_all(self):
        if self.owner != get_ident():
            raise RuntimeError("cannot notify on un-acquired lock")
        with self.meta_lock:
            self.lockers.update(self.waiters)
            self.waiters.clear()


def test():
    from threading import Thread
    import time

    lck = FairConditionRLock()
    # lck = Lock()

    counter = 2

    def work(tid):
        nonlocal counter
        for i in range(1000):
            with lck:
                lck.wait_for(lambda: counter > 0)
                counter -= 1

            print("got object", tid)
            time.sleep(0.25)

            with lck:
                counter += 1
                lck.notify()

    threads = [Thread(target=work, args=(tid,)) for tid in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    test()
