import sys, json

from sklearn.svm import SVC
import sklearn.metrics as metrics
import scipy.io as sio
import numpy as np
import functools

dataset_type = None
attribute_type = None
loss_persentage = None
data_dir = "/Users/ngym/Lorincz-Lab/project/fast_time-series_data_classification/program/gak_gram_matrix_completion/OUTPUT/"

def mat_file_name(sigma, completion_alg):
    # gram_dataset_completionalg_sigma.mat
    #print("loss:" + str(loss_persentage))
    return data_dir + \
        "gram_" + \
        dataset_type + "_" + \
        attribute_type + "_" + \
        "sigma" + ("%.3f" % sigma) + "_" + \
        "loss" + str(loss_persentage) + "_" + \
        completion_alg + ".mat"

def convert_index_to_attributes(index):
    index_ = index.split('/')[-1]
    type_, ground_truth, k_group, trial = index_.split('_')
    return dict(type=type_, ground_truth=ground_truth, k_group=k_group, trial=trial)

def separate_gram(gram, data_attributes, k_group):
    unmatched = []
    matched = []
    matched_is = []
    assert gram.__len__() == data_attributes.__len__()
    for i in range(gram.__len__()):
        if data_attributes[i]['k_group'] == k_group:
            matched.append(gram[i])
            matched_is.append(i)
        else:
            unmatched.append(gram[i])
    new_matched = []
    for row in matched:
        new_row_matched = []
        for i in range(gram.__len__()):
            if i not in matched_is:
                new_row_matched.append(row[i])
        new_matched.append(new_row_matched)
    new_unmatched = []
    for row in unmatched:
        new_row_unmatched = []
        for i in range(gram.__len__()):
            if i not in matched_is:
                new_row_unmatched.append(row[i])
        new_unmatched.append(new_row_unmatched)
    return new_matched, new_unmatched

def tryout1hyperparameter(cost, train, train_gtruths, validation_or_test, v_or_t_gtruths):
   # indices in the gram matrix is passed to the function to indicate the split. 
   clf = SVC(C=cost, kernel='precomputed')
   clf.fit(np.array(train), np.array(train_gtruths))
   pred = clf.predict(validation_or_test) # to check
   #matches = [z[0] == z[1] for z in zip(pred, v_or_t_gtruths)]
   #score = [m for m in matches if m is False].__len__() / matches.__len__()
   print("l2regularization_costs: " + repr(cost))
   print("prediction & groud truth")
   print([int(n) for n in list(pred)])
   print([int(n) for n in v_or_t_gtruths])
   print(" " + functools.reduce(lambda a,b: a + "  " + b, ["!" if z[0] != z[1] else " " for z in zip(list(pred), v_or_t_gtruths)]))
   print("---")
   #fpr, tpr, thresholds = metrics.roc_curve(v_or_t_gtruths, pred)
   #score = metrics.auc(fpr, tpr)
   score = metrics.accuracy_score(v_or_t_gtruths, pred)
   return score

def optimizehyperparameter(completion_alg,
                           sigmas, # [sigma]
                           costs, # [C]
                           #train, # [person IDs], hence [k_group]
                           validation, # person ID/k_group
                           test # person ID/k_group
):
    def train_validation_test_split(sigma):
        # sigma and completion_alg determines gram matrix file
        mat_file = mat_file_name(sigma, completion_alg) 
        mat = sio.loadmat(mat_file)
        gram = mat['gram']
        indices = mat['indices']

        data_attributes = []
        ground_truths = []
        for index in indices:
            attr = convert_index_to_attributes(index)
            data_attributes.append(attr)
            ground_truths.append(attr['ground_truth'])
            
        test_matrix, train_validation_matrix = separate_gram(gram, data_attributes, test)
        validation_matrix, train_matrix = separate_gram(train_validation_matrix,
                                                        [d for d in data_attributes if d['k_group'] != test],
                                                        validation)
        train_gtruths = [d['ground_truth'] for d in data_attributes if d['k_group'] not in {validation, test}]
        validation_gtruths = [d['ground_truth'] for d in data_attributes if d['k_group'] == validation]
        train_validation_gtruths = [d['ground_truth'] for d in data_attributes if d['k_group'] != test]
        test_gtruths = [d['ground_truth'] for d in data_attributes if d['k_group'] == test]
        return test_matrix, train_validation_matrix, validation_matrix, train_matrix,\
    train_gtruths, validation_gtruths, train_validation_gtruths, test_gtruths
        
    error_to_hyperparameters = {}
    for sigma in sigmas:
        test_matrix, train_validation_matrix, validation_matrix, train_matrix,\
    train_gtruths, validation_gtruths, train_validation_gtruths, test_gtruths\
    = train_validation_test_split(sigma)
        for cost in costs:
            error_to_hyperparameters[tryout1hyperparameter(cost, train_matrix, train_gtruths,
                                                           validation_matrix, validation_gtruths)] = (sigma, cost)
            #/* indices in the gram matrix is passed to the function to indicate the split. */
    best_sigma, best_cost = error_to_hyperparameters[min(list(error_to_hyperparameters.keys()))]
    test_matrix, train_validation_matrix, validation_matrix, train_matrix,\
    train_gtruths, validation_gtruths, train_validation_gtruths, test_gtruths\
    = train_validation_test_split(best_sigma)
    print("test")
    return tryout1hyperparameter(best_cost, train_validation_matrix, train_validation_gtruths, test_matrix, test_gtruths)

def crossvalidation(completion_alg, sigmas, costs):
    #for each split of gram into train/validation/test (for loop for 22 test subjects):
    # actually the dataset I have has 25 participants
    # ["A1", "C1", "C2", "C3", "C4", "E1", "G1", "G2", "G3", "I1", "I2", "I3",
    #  "J1", "J2", "J3", "L1", "M1", "S1", "T1", "U1", "Y1", "Y2", "Y3", "Z1", "Z2"]
    # actually participants/person ID.
    #k_groups = ["A1", "C1", "C2", "C3", "C4", "E1", "G1", "G2", "G3", "I1", "I2", "I3",
    #            "J1", "J2", "J3", "L1", "M1", "S1", "T1", "U1", "Y1", "Y2", "Y3", "Z1", "Z2"]
    k_groups = ["C1", "J1", "M1", "T1", "Y1", "Y2"]

    errors = []
    for i in range(k_groups.__len__()):
        validation_group = k_groups[i-1]
        test_group = k_groups[i]
        errors.append(optimizehyperparameter(completion_alg, sigmas, costs, validation_group, test_group))
        # /* indices in the gram matrix is passed to the function to indicate the split. */
    return np.average(errors)

def compare_completion_algorithms(sigmas, costs):
    result_no_completion = crossvalidation("NoCompletion", sigmas, costs)
    result_nuclear_norm_minimization = crossvalidation("NuclearNormMinimization", sigmas, costs)
    result_soft_impute = crossvalidation("SoftImpute", sigmas, costs)

    print("NoCompletion: " + repr(result_no_completion))
    print("NuclearNormMinimization: " + repr(result_nuclear_norm_minimization))
    print("SoftImpute: " + repr(result_soft_impute))

if __name__ == "__main__":
    config_json_file = sys.argv[1]
    config_dict = json.load(open(config_json_file, 'r'))

    dataset_type = config_dict['dataset_type']
    attribute_type = config_dict['attribute_type']
    loss_persentage = config_dict['loss_persentage']
    sigmas_ = config_dict['gak_sigmas']
    l2regularization_costs = config_dict['l2regularization_costs']

    compare_completion_algorithms(sigmas_, l2regularization_costs)