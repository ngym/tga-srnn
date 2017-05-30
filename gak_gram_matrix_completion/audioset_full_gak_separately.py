import numpy as np
from collections import OrderedDict

import scipy as sp
from scipy import io
from scipy.io import wavfile
from scipy import signal

import subprocess, functools, sys, threading, glob, json, random
import concurrent.futures

from plot_gram_matrix import plot

from string import Template

from gak import gak

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
        self.gram = OrderedDict()
        for seq_id1 in seq_ids:
            self.gram[seq_id1] = OrderedDict()
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

def read_and_resample_worder(f, frequency):
    mat_filename = f.replace(".wav", ("_freq" + str(frequency) + ".mat"))
    print(mat_filename)
    try:
        mat = io.loadmat(mat_filename)
        resampled_data = mat['resampled_data']
        print("read from mat")
    except:
        rate, data = io.wavfile.read(f)
        length = frequency * data.__len__() // rate
        print("read from wav")
        resampled_data = signal.resample(data, length)
    return resampled_data

def audioset_read_wavs_and_build_seqs(files, audioset_resampling_frequency, num_thread):
    for f in files:
        resampled_data = read_and_resample_worder(f, audioset_resampling_frequency)
        if resampled_data.ndim > 1:
            # stereo
            # convert stereo to mono
            # https://librosa.github.io/librosa/_modules/librosa/core/audio.html
            seqs[f] = np.array([[np.mean([np.float64(elem) for elem in sample], axis=0)] for sample in resampled_data])
        else:
            # mono
            seqs[f] = np.array(resampled_data).astype('float64')
        #print(seqs[f])
        print(str(seqs.__len__()) + " " + f + " length: " + str(resampled_data.__len__()))
        sys.stdout.flush()
    """
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_thread) as executor:
        future_to_file = {executor.submit(read_and_resample_worder, f, audioset_resampling_frequency): f
                           for f in files}
        print("reading %d files." % future_to_file.__len__())
        for future in concurrent.futures.as_completed(future_to_file):
            f = future_to_file[future]
            resampled_data = future.result()
            if resampled_data.ndim > 1:
                # stereo
                # convert stereo to mono
                # https://librosa.github.io/librosa/_modules/librosa/core/audio.html          
                seqs[f] = np.array([[np.mean([np.float64(elem) for elem in sample], axis=0)] for sample in resampled_data])
            else:
                # mono
                seqs[f] = np.array(resampled_data).astype(float64)
            #print(seqs[f])
            print(str(seqs.__len__()) + " " + f + " length: " + str(resampled_data.__len__()))
            sys.stdout.flush()
    """
def SixDMG_read_mats_and_build_seqs(files, attribute_type):
    for f in files:
        mat = io.loadmat(f)
        seqs[f] = np.array(SixDMG_pick_attribute(mat['gest'].transpose(), attribute_type)).astype('float64')

def SixDMG_pick_attribute(ll, attribute_type):
    retval = []
    if attribute_type == "position":
        for l in ll:
            retval.append(l[1:4])
    elif attribute_type == "velocity":
        for i in range(ll.__len__() - 1):
            retval.append([(ll[i+1][1] - ll[i][1])/((ll[i+1][0] - ll[i][0])/1000),
                           (ll[i+1][2] - ll[i][2])/((ll[i+1][0] - ll[i][0])/1000),
                           (ll[i+1][3] - ll[i][3])/((ll[i+1][0] - ll[i][0])/1000)])
    elif attribute_type == "acceleration":
        for l in ll:
            retval.append(l[8:11])
    elif attribute_type == "angularvelocity":
        for l in ll:
            retval.append(l[11:14])
    elif attribute_type == "orientation":
        for l in ll:
            retval.append(l[4:8])
    elif attribute_type == "all":
        for l in ll:
            retval.append(l[1:14])
    else:
        print("attribute type error.")
        assert False
    return retval
        
def worker_for_f1(files, f1index, file_num, gak_sigma, triangular):
    f1 = files[f1index]
    seq1 = seqs[f1]
    ret_dict = {}
    for f2index in range(f1index, file_num):
        f2 = files[f2index]
        seq2 = seqs[f2]
        ret_dict[f2] = gak(seq1, seq2, gak_sigma, triangular)
    return ret_dict

if __name__ == "__main__":
    config_json_file = sys.argv[1]
    config_dict = json.load(open(config_json_file, 'r'))
    
    num_thread = config_dict['num_thread']

    dataset_type = config_dict['dataset_type']

    data_files = config_dict['data_mat_files']
    gak_sigma = np.float64(config_dict['gak_sigma'])
    random_seed = int(config_dict['random_seed'])

    output_dir = config_dict['output_dir']
    
    files = []
    for df in data_files:
        files_ = glob.glob(df)
        print(files_[:3])
        print("...")
        print(files_[-3:])
        files += files_
    files = sorted(files)

    audioset_resampling_frequency = config_dict['audioset_resampling_frequency']
    
    if dataset_type in {"num", "upperChar"}:
        # 6DMG
        SixDMG_read_mats_and_build_seqs(files, data_attribute_type)
    else:
        # audioset
        audioset_read_wavs_and_build_seqs(files, audioset_resampling_frequency, num_thread)

    gram = GRAMmatrix(files)

    similarities = []
    file_num = files.__len__()

    gak_triangular = np.median([seq.__len__() for seq in seqs.values()]) * 0.5
    print("gak_triangular: " + repr(gak_triangular))
    
    futures = []

    separated_part = config_dict['part']
    assert 0 <= separated_part and separated_part < 5
    first_part_start   = (separated_part       * file_num//10) # <=
    first_part_finish  = ((separated_part + 1) * file_num//10) # <
    second_part_start  = ((9 - separated_part) * file_num//10) # <=
    second_part_finish = ((10- separated_part) * file_num//10) # <

    output_filename_format = Template(config_dict['output_filename_format']).safe_substitute(
        dict(dataset_type=dataset_type,
             audioset_resampling_frequency=audioset_resampling_frequency,
             gak_sigma=("%.3f" % gak_sigma))

    html_out_full_gak = output_dir + output_filename_format.replace("${completion_alg}", "FullGAK") + \
                        "_part" + str(separated_part) + ".html"
    mat_out_full_gak = output_dir + output_filename_format.replace("${completion_alg}", "FullGAK") + \
                       "_part" + str(separated_part) + ".mat"

    gak_logfile = output_dir + output_filename_format.replace("_${completion_alg}", "") + \
                  "_part" + str(separated_part) + ".log"
    gak_logger = Logger(gak_logfile)

    #seqs[files[f2index]]
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_thread) as executor:
        print("Start submitting jobs.")
        future_to_files = {executor.submit(worker_for_f1, files, f1index, file_num, gak_sigma, gak_triangular):
                           f1index
                           for f1index in range(file_num)
                           if (first_part_start  <= f1index and f1index < first_part_finish ) or
                              (second_part_start <= f1index and f1index < second_part_finish)}
        num_futures = future_to_files.__len__()
        print(str(num_futures) + " jobs are submitted.")
        num_finished_jobs = 0
        for future in concurrent.futures.as_completed(future_to_files):
            f1index = future_to_files[future]
            f1 = files[f1index]
            ret_dict = future.result()
            ret_dict_keys = list(ret_dict.keys())
            for f2 in ret_dict_keys:
                value = ret_dict[f2]
                gram.register(f1, f2, value)
                gak_logger.write(f1 + ", " + f2 + ", " + str(value) + "\n")
            num_finished_jobs += 1
            print(str(num_finished_jobs) + "/" + str(num_futures), end=" ")
            sys.stdout.flush()

    print(" ")

    similarities = []
    for i in gram.gram.values():
        similarities.append(list(i.values()))

    # "FullGAK separately"
    plot(html_out_full_gak,
         similarities, files)
    io.savemat(mat_out_full_gak, dict(gram=similarities, indices=files))
    print("Separated FullGAK files are output.")
