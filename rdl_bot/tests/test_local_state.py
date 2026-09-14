import unittest

from local_state import UnresolvedInputQueue
from h_state import unresolved_input_pressure


class UnresolvedInputQueueTests(unittest.TestCase):
    def test_queue_is_list_compatible_for_legacy_runtime(self):
        queue = UnresolvedInputQueue(["a"])
        queue.append("b")
        self.assertEqual(queue, ["a", "b"])
        self.assertEqual(len(queue), 2)

    def test_named_operations_preserve_deferred_input_role(self):
        queue = UnresolvedInputQueue()
        queue.hold("unknown one")
        queue.hold("unknown two")
        self.assertEqual(queue.pending(), ("unknown one", "unknown two"))

        queue.replace_pending(["unknown two"])
        self.assertEqual(queue.pending(), ("unknown two",))

    def test_legacy_pressure_accepts_queue_without_making_it_core_xi(self):
        queue = UnresolvedInputQueue(["a", "b"])
        self.assertAlmostEqual(unresolved_input_pressure(queue, saturation=4), 0.5)
        self.assertFalse(hasattr(queue, "xi"))
        self.assertFalse(hasattr(queue, "theta"))


if __name__ == "__main__":
    unittest.main()
