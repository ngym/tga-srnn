import random
import numpy as np
import copy

def gram_drop_random(seed, gram, percent):
    """Drop elements randomly from Gram matrix.

    :param seed: Random seed for reproducibility
    :param gram: Gram matrix to be dropped
    :param percent: Percent of matrix elements to drop
    :type seed: int
    :type gram: list of lists
    :type percent: int
    :returns: Dropped version of Gram matrix, dropped indices
    :rtype: list of lists, list of tuples
    """
    
    random.seed(seed)

    half_indices = [(i, j) for i in range(len(gram))
                   for j in range(i + 1, len(gram[0]))]
    permutated_half_indices = np.random.permutation(half_indices)
    num_to_drop = int(len(permutated_half_indices) * percent / 100)
    indices_drop = permutated_half_indices[:num_to_drop]

    gram_drop = copy.deepcopy(gram)
    for i, j in indices_drop:
        gram_drop[i][j] = np.nan
        gram_drop[j][i] = np.nan
        
    return gram_drop, indices_drop

def gram_drop_one_sample(gram, index):
    """Drop ith row and ith column from Gram matrix.

    :param gram: Gram matrix to be dropped
    :param index: Row and column to be dropped
    :type gram: list of lists
    :type index: int
    :returns: Dropped version of Gram matrix, dropped indices
    :rtype: list of lists, list of tuples
    """

    gram_drop = copy.deepcopy(gram)
    indices_drop = []
    for i in range(len(gram)):
        if not np.isnan(gram_drop[i][index]):
            gram_drop[i][index] = np.nan
            indices_drop.append((i, index))
        if not np.isnan(gram_drop[index][i]):
            gram_drop[index][i] = np.nan
            indices_drop.append((index, i))

    return gram_drop, indices_drop

def gram_drop_samples(gram, indices):
    """Drop multiple rows and columns from Gram matrix.

    :param gram: Gram matrix to be dropped
    :param indices: Rows and columns to be dropped
    :type gram: list of lists
    :type indices: list of ints
    :returns: Dropped version of Gram matrix, dropped indices
    :rtype: list of lists, list of tuples
    """

    gram_drop = copy.deepcopy(gram)
    indices_drop = []
    for index in indices:
        gram_drop, indices_drop_i = gram_drop_one_sample(gram_drop, index)
        indices_drop += indices_drop_i
    return gram_drop, indices_drop


def gram_drop_in_sample_random(gram, index, percent):
    """Drop random part of ith row and ith column from Gram matrix.

    :param gram: Gram matrix to be dropped
    :param index: Row and column to be dropped
    :param percent: Percent of row and column to be dropped
    :type gram: list of lists
    :type index: list of ints
    :type percent: int
    :returns: Dropped version of Gram matrix, dropped indices
    :rtype: list of lists, list of tuples
    """
    
    length = len(gram)

    permutated_indices = np.random.permutation(length)
    num_to_drop = int(length * percent * 0.01)
    subindices_drop = permutated_indices[:num_to_drop]

    gram_drop = copy.deepcopy(gram)
    indices_drop = []
    for i in subindices_drop:
        gram_drop[i][index] = np.nan
        indices_drop.append((i, index))
        gram_drop[index][i] = np.nan
        indices_drop.append((index, i))

    return gram_drop, indices_drop

def gram_drop_in_samples_random(gram, indices, percent):
    """Drop random parts of multiple rows and columns from Gram matrix.

    :param gram: Gram matrix to be dropped
    :param indices: Rows and columns to be dropped
    :type gram: list of lists
    :type indices: list of ints
    :returns: Dropped version of Gram matrix, dropped indices
    :rtype: list of lists, list of tuples
    """
    
    gram_drop = copy.deepcopy(gram)
    indices_drop = []
    for index in indices:
        gram_drop, indices_drop_i = gram_drop_in_sample_random(gram_drop, index, percent)
        indices_drop += indices_drop_i
    return gram_drop, indices_drop

from collections import OrderedDict

def trim_nan(gram_drop, seqs):
    seqs = np.array(seqs)
    to_remove = [i for i in range(len(gram_drop))
                 if np.isnan(gram_drop[i][0])]
    gram_drop = np.delete(gram_drop, to_remove, axis=0)
    gram_drop = np.delete(gram_drop, to_remove, axis=1)
    seqs = np.delete(seqs, to_remove, axis=0)
    return gram_drop, seqs





