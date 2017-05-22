import numpy as np
import TGA_python3_wrapper.global_align as ga
import scipy.io as sio

import subprocess, functools, sys, threading, glob, json, random
import concurrent.futures

import plotly.offline as po
import plotly.graph_objs as pgo

from fancyimpute import BiScaler, KNN, NuclearNormMinimization, SoftImpute

class Logger:
    def __init__(self, log_file):
        self.__lock = threading.Lock()
        self.__fd = open(log_file, 'w')
    def write(self, msg):
        self.__lock.acquire()
        try:
            self.__fd.write(msg)
            #self.__fd.flush()
        finally:
            self.__lock.release()
    def __del__(self):
        self.__fd.write("\n")
        self.__fd.close()

gak_logger = None

class GRAMmatrix:
    def __init__(self, seq_ids):
        self.__lock = threading.Lock()
        self.gram = {}
        for seq_id1 in seq_ids:
            self.gram[seq_id1] = {}
            for seq_id2 in seq_ids:
                self.gram[seq_id1][seq_id2] = -1
    def register(self, seq_id1, seq_id2, value):
        self.__lock.acquire()
        try:
            self.gram[seq_id1][seq_id2] = value
            self.gram[seq_id2][seq_id1] = value
        finally:
            self.__lock.release()

gram = None

seqs = {}

def read_mats_and_build_seqs(files):
    for f in files:
        mat = sio.loadmat(f)
        seqs[f] = second_map(np.float64, mat['gest'].transpose())

def second_map(func, ll):
    retval = []
    for l in ll:
        retval.append(list(map(func, l[1:4])))
    return np.array(retval)

DATA_DIR = "/Users/ngym/Lorincz-Lab/project/fast_time-series_data_classification/dataset/6DMG_mat_112712/matR_char/"

def gak(seq1, seq2):
    #print(threading.get_ident())
    if matrix_completion != "NO_COMPLETION":
        randval = random.randint(0, 9)
        if randval == 0:
            return np.nan
    
    T1 = seq1.__len__()
    T2 = seq2.__len__()

    #sigma = 0.5*(T1+T2)/2*np.sqrt((T1+T2)/2)
    sigma = 2 ** 0
    #print("sigma: " + repr(sigma), end="  ")
    
    diff_t = np.abs(T1-T2)

    triangular = 0

    val = ga.tga_dissimilarity(seq1, seq2, sigma, triangular)
    kval = np.exp(-val)
    if 0 < triangular <= diff_t:
        assert kval == 0
    return kval

matrix_completion = "NO_COMPLETION"

if __name__ == "__main__":
    config_json_file = sys.argv[1]
    config_dict = json.load(open(config_json_file, 'r'))
    
    file_out = config_dict['output_html']
    num_thread = config_dict['num_thread']
    gak_logfile = config_dict['gak_logfile']
    data_files = config_dict['data_mat_files']
    matrix_completion = config_dict['matrix_completion']
    print(matrix_completion)
    if matrix_completion in {"NO_COMPLETION", "NUCLEAR_NORM_MINIMIZATION", "SOFT_IMPUTE"}:
        print(matrix_completion + " is selected")
    else:
        print("Invalid completion option")
        assert False

    random.seed(1)
        
    gak_logger = Logger(gak_logfile)

    files = []
    for df in data_files:
        files_ = glob.glob(df)
        print(files_[:3])
        print("...")
        print(files_[-3:])
        files += files_

    read_mats_and_build_seqs(files)
    
    gram = GRAMmatrix(files)

    similarities = []
    file_num = files.__len__()

    futures = []

    def worker_for_f1(f1index, f2indices):
        f1 = files[f1index]
        seq1 = seqs[f1]
        ret_dict = {}
        for f2index in f2indices:
            f2 = files[f2index]
            seq2 = seqs[f2]
            ret_dict[f2] = gak(seq1, seq2)
        return ret_dict
    #seqs[files[f2index]]
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_thread) as executor:
        print("Start submitting jobs.")
        future_to_files = {executor.submit(worker_for_f1, f1index, range(f1index, file_num)):
                           files[f1index]
                           for f1index in range(file_num)}
        num_futures = future_to_files.__len__()
        print(str(num_futures) + " jobs are submitted.")
        num_finished_jobs = 0
        for future in concurrent.futures.as_completed(future_to_files):
            f1 = future_to_files[future]
            ret_dict = future.result()
            ret_dict_keys = list(ret_dict.keys())
            for f2 in ret_dict_keys:
                value = ret_dict[f2]
                gram.register(f1, f2, value)
                gak_logger.write(f1 + ", " + f2 + ", " + str(value) + "\n")
            num_finished_jobs += 1
            print(str(num_finished_jobs) + "/" + str(num_futures) , end=" ")
            sys.stdout.flush()

    print(" ")
    
    similarities = []
    for i in gram.gram.values():
        similarities.append(list(i.values()))

    matrix_incomplete = np.array(similarities)

    if matrix_completion == "NO_COMPLETION":
        processed_similarities = similarities
    elif matrix_completion == "NUCLEAR_NORM_MINIMIZATION":
        # matrix completion using convex optimization to find low-rank solution
        # that still matches observed values. Slow!
        X_filled = NuclearNormMinimization().complete(matrix_incomplete)
        processed_similarities = X_filled
    elif matrix_completion == "SOFT_IMPUTE":
        # Instead of solving the nuclear norm objective directly, instead
        # induce sparsity using singular value thresholding
        X_filled = SoftImpute().complete(matrix_incomplete)
        processed_similarities = X_filled
    else:
        print("Invalid completion option")
        assert False

    # To fix the direction of the matrix as the diagonal line is from top-left to bottom-right.
    processed_similarities_ = processed_similarities[::-1]
    files_to_show = []
    for f in files:
        files_to_show.append(f.split('/')[-1])
    files_to_show_ = files_to_show[::-1]
        
    trace = pgo.Heatmap(z=processed_similarities_,
                        x=files_to_show,
                        y=files_to_show_
    )
    data=[trace]
    po.plot(data, filename=file_out, auto_open=False)
