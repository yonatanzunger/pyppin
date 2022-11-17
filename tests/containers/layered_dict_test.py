import unittest
from typing import Dict

from pyppin.containers.layered_dict import LayeredDict


class LayeredDictTest(unittest.TestCase):
    def test_simple_layers(self) -> None:
        d1: Dict[str, int] = {'foo': 1, 'bar': 2}
        layered = LayeredDict[str, int](d1)

        self.assertEqual(2, len(layered))
        self.assertEqual(1, layered.depth)
        self.assertEqual(1, layered['foo'])
        self.assertEqual(2, layered['bar'])
        with self.assertRaises(KeyError):
            layered['quux']
        with self.assertRaises(NotImplementedError):
            layered['quux'] = 5
        self.assertEqual(d1, layered.flatten())

        # Now we add a second layer.
        d2: Dict[str, int] = {'bar': 5, 'quux': 100}
        layered.push_layer(d2)
        self.assertEqual(3, len(layered))
        self.assertEqual(2, layered.depth)
        self.assertEqual(1, layered['foo'])
        self.assertEqual(5, layered['bar'])
        self.assertEqual(100, layered['quux'])
        with self.assertRaises(KeyError):
            layered['frobnitz']
        self.assertEqual({'foo': 1, 'bar': 5, 'quux': 100}, layered.flatten())

        # Modify the second layer directly.
        d2['frobnitz'] = 30
        del d2['bar']
        self.assertEqual(4, len(layered))
        self.assertEqual({'foo': 1, 'bar': 2, 'quux': 100, 'frobnitz': 30}, layered.flatten())

        # Now pop_layer off the second layer and see that it's back where it should have been
        self.assertEqual(d2, layered.pop_layer())
        self.assertEqual(1, layered.depth)
        self.assertEqual(2, len(layered))
        self.assertEqual(1, layered['foo'])
        self.assertEqual(2, layered['bar'])
        with self.assertRaises(KeyError):
            layered['quux']
        with self.assertRaises(NotImplementedError):
            layered['quux'] = 5
        self.assertEqual(d1, layered.flatten())

        # Now pop_layer off the first one, too.
        self.assertEqual(d1, layered.pop_layer())
        self.assertEqual(0, layered.depth)
        self.assertEqual(0, len(layered))
        self.assertEqual({}, layered.flatten())

        # And validate that an extra pop_layer doesn't crash.
        self.assertIsNone(layered.pop_layer())
