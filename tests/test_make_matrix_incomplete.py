import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import unittest
from utils.make_matrix_incomplete import gram_drop_random, gram_drop_one_sample, gram_drop_samples
import numpy as np


class Test_make_matrix_incomplete(unittest.TestCase):
    """Unit tests for dropping Gram matrix elements
    """

    def setUp(self):
        length = 10
        self.sim = [[(i, j) for i in range(length)] for j in range(length)]
        for i in self.sim:
            print(i)

    def test_gram_drop_random(self):
        in_sim, dropped_elements = gram_drop_random(1, self.sim, 10)
        for i in in_sim:
            print(i)
        def comp(a, b):
            if isinstance(a, tuple) and isinstance(b, tuple):
                return a == b[::-1]
            elif np.isnan(a) and np.isnan(b):
                return True
            assert False
        self.assertTrue(all([comp(z[0], z[1]) for z
                             in zip(np.array(in_sim).flatten(),
                                    np.array(in_sim).T.flatten())]))

    def test_gram_drop_one_sample(self):
        length = 10
        for drop in range(length):
            print("drop:%d" % drop)
            sim = [[(i, j) for i in range(length)] for j in range(length)]
            sim, _ = gram_drop_one_sample(self.sim, drop)
            for i in sim:
                print(i)
            sim_ = [[e for e in s if isinstance(e, tuple)] for s in sim
                    if [e for e in s if isinstance(e, tuple)] != []]
            sim_ = np.array(sim_).flatten()
            sim_ = [drop != s for s in sim_]
            self.assertTrue(all(sim_))

    def test_gram_drop_samples(self):
        length = 10
        indices = [(i, j) for i in range(length) for j in range(length)]
        for drop_i, drop_j in indices:
            print("drop_i:%d, drop_j:%d" % (drop_i, drop_j))
            sim = [[(i, j) for i in range(length)] for j in range(length)]
            sim, _ = gram_drop_samples(self.sim, [drop_i, drop_j])
            for i in sim:
                print(i)
            sim_ = [[e for e in s if isinstance(e, tuple)] for s in sim
                    if [e for e in s if isinstance(e, tuple)] != []]
            sim_ = np.array(sim_).flatten()
            sim_ = [drop_i != s and drop_j != s for s in sim_]
            self.assertTrue(all(sim_))

    def tearDown(self):
        pass

if __name__ == '__main__':
    unittest.main()

