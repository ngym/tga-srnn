import sys, os
import time
from collections import OrderedDict

from sacred import Experiment

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from algorithms import matrix_completion
from datasets.read_sequences import read_sequences
from datasets import k_fold_cross_validation
from utils import errors
from utils import file_utils
from utils import nearest_positive_semidefinite
from utils import make_matrix_incomplete

ex = Experiment('calculate_gram_matrix')


@ex.config
def cfg():
    output_dir = "results/"
    params = None
    fold_count = 5
    fold_to_drop = 1


@ex.named_config
def gak():
    algorithm = "gak"
    params = dict(sigma=20,
                  triangular=None)


@ex.named_config
def softimpute():
    algorithm = "softimpute"


@ex.capture
def check_algorithms(algorithm):
    assert algorithm in {"gak", "softimpute"}


@ex.capture
def check_fold(fold_count, fold_to_drop):
    assert 1 < fold_count and 0 < fold_to_drop <= fold_count


@ex.capture
def check_params(algorithm, params):
    if algorithm == "gak":
        if 'sigma' not in params:  # TODO else
            params['sigma'] = None
        if 'triangular' not in params:  # TODO else
            params['triangular'] = None


def calculate_errors(gram, gram_completed_npsd, dropped_elements):
    mse = errors.mean_squared_error(gram, gram_completed_npsd)
    msede = errors.mean_squared_error(gram,
                                      gram_completed_npsd,
                                      dropped_elements)

    mae = errors.mean_absolute_error(gram, gram_completed_npsd)
    maede = errors.mean_absolute_error(gram,
                                       gram_completed_npsd,
                                       dropped_elements)

    re = errors.relative_error(gram,
                               gram_completed_npsd)
    rede = errors.relative_error(gram,
                                 gram_completed_npsd,
                                 dropped_elements)

    return mse, msede, mae, maede, re, rede

@ex.automain
def run(seed, pickle_location, dataset_location, fold_count, fold_to_drop,
        algorithm, params, output_dir, output_filename_format):
    main_start = time.time()

    pkl = file_utils.load_pickle(pickle_location)

    dataset_type = pkl['dataset_type']
    sample_names = pkl['sample_names']
    gram_matrices = pkl['gram_matrices']
    if len(gram_matrices) == 1:
        gram = gram_matrices[0]['original']
    else:
        gram = gram_matrices[-1]['completed_npsd']

    check_fold(fold_count, fold_to_drop)
    folds = k_fold_cross_validation.get_kfolds(dataset_type, sample_names, fold_count)
    indices_to_drop = folds[fold_to_drop - 1]
    gram_drop, dropped_elements = make_matrix_incomplete.gram_drop_samples(gram, indices_to_drop)

    seqs = OrderedDict((k, v) for k, v in read_sequences(dataset_type, direc=dataset_location)[0].items()
                       if k.split('/')[-1] in sample_names)

    train_start = None
    train_end = None
    if algorithm == "gak":
        gram_completed, completion_start, completion_end \
            = matrix_completion.gak_matrix_completion(gram_drop, list(seqs.values()), indices_to_drop,
                                                      sigma=params['sigma'], triangular=params['triangular'])
        action = "GAK sigma: " + str(params['sigma']) + " triangular: " + str(params['triangular'])
        output_filename_format = output_filename_format.replace("${sigma}", str(params['sigma']))\
                                                       .replace("${triangular", str(params['triangular']))
    elif algorithm == "softimpute":
        gram_completed, completion_start, completion_end \
            = matrix_completion.softimpute_matrix_completion(gram_drop)
        action = "Softimpute"
    else:
        assert False

    # eigenvalue check
    npsd_start = time.time()
    gram_completed_npsd = nearest_positive_semidefinite.nearest_positive_semidefinite(gram_completed)
    npsd_end = time.time()

    # save results
    log_file = os.path.join(output_dir, output_filename_format + ".pkl")
    action += " " + time.asctime(time.localtime())
    file_utils.append_and_save_result(log_file, pkl, gram_drop, gram_completed, gram_completed_npsd, indices_to_drop,
                                      action)

    # claculate errors
    mse, mse_dropped, mae, mae_dropped, re, re_dropped = calculate_errors(gram, gram_completed_npsd, dropped_elements)

    main_end = time.time()

    # save run times and errors
    analysis_file = log_file.replace(".pkl", ".json")
    num_calculated_elements = len(dropped_elements) - len(indices_to_drop) // 2
    file_utils.save_analysis(analysis_file, len(dropped_elements), num_calculated_elements,
                             completion_start, completion_end, npsd_start, npsd_end, main_start, main_end,
                             mse, mse_dropped, mae, mae_dropped, re, re_dropped,
                             train_start=train_start, train_end=train_end)