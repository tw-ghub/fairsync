import time
from threading import Condition, Thread
from fairsync.condition import Condition as FsCondition

# This is a sample implementation of something like an object pool. It uses
# a condition variable to ensure that at most `counter` threads are allowed
# to execute at a time.
THREAD_COUNT = 10
counter = 1


class TestCondition:
    cnd = None

    def _work(self, tid):
        global counter
        for i in range(10):
            # Wait for counter to be positive, so we are allowed to run.
            with self.cnd:
                self.cnd.wait_for(lambda: counter > 0)
                counter -= 1

            print("thread", tid, "running")
            # Sample logic to run in the critical section.
            time.sleep(0.05)

            # Give up counter. Ideally this would allow someone else to run. In practice
            # however we will immediately loop and run again before anyone else gets
            # the chance.
            with self.cnd:
                counter += 1
                self.cnd.notify_all()

    def test_std_condition(self):
        TestCondition.cnd = Condition()
        # With standard condition it can be observed that the Thread which owned the condition with immediately re-acquire it
        # after doing notify_all and releasing the condition. Other threads waiting on the condition might starve.

        threads = [Thread(target=self._work, args=(tid,)) for tid in range(THREAD_COUNT)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def test_fairsync_condition(self):
        TestCondition.cnd = FsCondition()
        # The fairsync condition implementation serves waiting threads in a fair manner and prevents starvation.

        threads = [Thread(target=self._work, args=(tid,)) for tid in range(THREAD_COUNT)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
