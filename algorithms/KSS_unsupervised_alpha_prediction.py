import copy, time

from sklearn.svm import SVC
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import LabelBinarizer
from sklearn.metrics import f1_score, roc_auc_score

import numpy as np

from collections import Counter

import keras.backend as K
from keras.models import Sequential, Model
from keras.callbacks import ModelCheckpoint, EarlyStopping, Callback
from keras.layers import Dense, Dropout, Input, SimpleRNN, LSTM, GRU, Masking, Activation, BatchNormalization
from keras.optimizers import Adam, RMSprop
from keras.layers.wrappers import Bidirectional
from keras.layers.merge import Concatenate
from keras.preprocessing.sequence import pad_sequences

import keras.initializers as initializers
import keras.regularizers as regularizers
import keras.constraints as constraints
from keras.legacy import interfaces
from keras.engine import Layer, InputSpec

import tensorflow as tf

from utils import multi_gpu
from utils import make_matrix_incomplete
from algorithms.rnn import Rnn

def get_classification_error(gram,
                             small_gram_indices,
                             tv_indices,
                             test_indices,
                             seqs_,
                             epochs, patience,
                             logfile_hdf5,
                             logfile_loss,
                             rnn,
                             rnn_units,
                             dense_units,
                             dropout,
                             implementation,
                             bidirectional,
                             batchnormalization,
                             mode,
                             labels,
                             lmbd_start,
                             lmbd_end):
    gram = gram.astype('float32')
    seqs = np.array(seqs_)
    # pre-processing
    time_dim = max([seq.shape[0] for seq in seqs])
    pad_value = -4444
    seqs = pad_sequences([seq.tolist() for seq in seqs],
                         maxlen=time_dim, dtype='float16',
                         padding='post', value=pad_value)
    feat_dim = seqs[0].shape[1]
    input_shape = (time_dim, feat_dim)

    
    small_gram = gram[small_gram_indices][:, small_gram_indices]
    tv_ks = gram[tv_indices][:, small_gram_indices]
    #tv_ks = gram[small_gram_indices][:, tv_indices]
    test_ks = gram[test_indices][:, small_gram_indices]
    #test_ks = gram[small_gram_indices][:, test_indices]

    tv_seqs = seqs[tv_indices]
    test_seqs = seqs[test_indices]

    labels_ar = np.array(labels)
    small_gram_labels = labels_ar[small_gram_indices]
    tv_labels = labels_ar[tv_indices]
    test_labels = labels_ar[test_indices]

    size_groups_small_gram = np.unique(small_gram_labels, return_counts=True)[1]

    K.clear_session()

    model = Unsupervised_alpha_prediction_network(input_shape,
                                                  pad_value,
                                                  rnn_units,
                                                  dense_units,
                                                  rnn, dropout,
                                                  implementation,
                                                  bidirectional,
                                                  batchnormalization,
                                                  lmbd_start,
                                                  lmbd_end,
                                                  small_gram, size_groups_small_gram)

    if mode == 'train':
        model.train_and_validate(tv_seqs,
                                 tv_ks,
                                 epochs,
                                 patience,
                                 logfile_hdf5,
                                 logfile_loss,
                                 size_groups_small_gram, tv_labels)

    alpha_pred, pred_start, pred_end = model.predict(test_seqs)

    alpha_g_norm = calc_group_norm(size_groups_small_gram, alpha_pred)
    pred_indices = K.get_value(K.argmax(alpha_g_norm, axis=0)) # index

    labels_order = np.unique(tv_labels, return_counts=True)[0]
    true_labels = test_labels
    true_indices = np.concatenate([np.where(labels_order == l) for l in true_labels])

    roc_auc_, f1_ = calc_scores(pred_indices, true_indices, len(labels_order))
    print("test roc_auc: %f" % roc_auc_)
    print("test f1     : %f" % f1_)
    assert False
    
    return (roc_auc_, f1_)


def calc_group_norm(size_groups_small_gram, alpha_pred):
    cumsum = np.cumsum(size_groups_small_gram)
    group_start_and_end = [(s, e) for (s, e) in zip(np.concatenate([np.array([0]), cumsum[:-1]]), cumsum)]
    group_indices = [K.variable(np.arange(s, e), dtype='int32') for (s, e) in group_start_and_end]
    
    alpha_pred_T = K.transpose(K.variable(alpha_pred))
    alpha_g_norm_ = [K.sqrt(K.sum(K.square(K.gather(alpha_pred_T, g)), axis=0) ) for g in group_indices]
    alpha_g_norm = K.stack(alpha_g_norm_)
    return alpha_g_norm


def calc_scores(pred_indices, true_indices, l):
    pred_binary = np.zeros([len(true_indices), l])
    for i, index in enumerate(pred_indices):
        pred_binary[i][index] = 1
                             
    true_binary = np.zeros([len(true_indices), l])
    for i, index in enumerate(true_indices):
        true_binary[i][index] = 1

    roc_auc_ = roc_auc_score(y_true=true_binary, y_score=pred_binary)
    f1_ = f1_score(true_binary, pred_binary, average='weighted')

    return (roc_auc_, f1_)

    
    
class Unsupervised_alpha_prediction_network(Rnn):
    def __init__(self, input_shape, pad_value, rnn_units, dense_units,
                 rnn, dropout, implementation, bidirectional, batchnormalization,
                 lmbd_start, lmbd_end,
                 gram, size_groups):
        """
        :param input_shape: Keras input shape
        :param pad_value: Padding value to be skipped among time steps
        :param rnn_units: Recurrent layer sizes
        :param dense_units: Dense layer sizes
        :param rnn: Recurrent Layer type (Vanilla, LSTM or GRU)
        :param dropout: Dropout probability
        :param implementation: RNN implementation (0: CPU, 2: GPU, 1: any)
        :param bidirectional: Flag to switch between Forward and Bidirectional RNN
        :param batchnormalization: Flag to switch Batch Normalization on/off
        :type input_shape: tuple
        :type pad_value: float
        :type rnn_units: list of ints
        :type dense_units: list of ints
        :type rnn: str
        :type dropout: float
        :type implementation: int
        :type bidirectional: bool
        :type batchnormalization: bool
        """
        super().__init__(input_shape, pad_value, rnn_units, dense_units,
                         rnn, dropout, implementation,
                         bidirectional, batchnormalization)

        self.hyperparams = {'lambda_start': lmbd_start,
                            'lambda_end': lmbd_end,
                            'end_epoch': 15}
        
        self.model = self.__create_RNN_unsupervised_alpha_prediction_network(gram, size_groups)

    def __create_RNN_unsupervised_alpha_prediction_network(self, gram, size_groups):
        """

        :return: Keras Deep RNN Siamese network
        :rtype: keras.models.Model
        """
        self.sparse_rate_callback = LambdaRateScheduler(start=self.hyperparams['lambda_start'],
                                                        end=self.hyperparams['lambda_end'],
                                                        end_epoch=self.hyperparams['end_epoch'],
                                                        dtype='float32')
        
        base_network = self.create_RNN_base_network()
        input_ = Input(shape=self.input_shape)
        processed = base_network(input_)
        parent = Dense(units=(gram.shape[0]), use_bias=False
                       if self.batchnormalization else True)(processed)
        if self.batchnormalization:
            parent = BatchNormalization()(parent)
        out = GroupSoftThresholdingLayer(size_groups)(parent)
        #out = Dense(units=gram.shape[0])(parent)

        model = Model(input_, out)

        optimizer = RMSprop(clipnorm=1.)
        if self.gpu_count > 1:
            model = multi_gpu.make_parallel(model, self.gpu_count)

        self.loss_function = KSS_Loss(self.sparse_rate_callback.var, gram, size_groups)

        #model.compile(loss="mse", optimizer=optimizer)
        model.compile(loss=self.loss_function, optimizer=optimizer)

        return model

    def train_and_validate(self,
                           tv_seqs,
                           tv_ks,
                           epochs,
                           patience,
                           logfile_hdf5,
                           logfile_loss,
                           size_groups_small_gram, tv_labels):
        """Keras Siamese RNN training function.
        Carries out training and validation for given data over given number of epochs
        Logs results and network parameters

        :param trval_indices: Training and Validation 2-tuples of time series index pairs
        :param seqs: List of time series
        :param epochs: Number of passes over data set
        :param patience: Early Stopping parameter
        :param logfile_hdf5: Log file name for network structure and weights in HDF5 format
        :type tr_indices: list of tuples
        :type seqs: list of np.ndarrays
        :type epochs: int
        :type patience: int
        :type logfile_hdf5: str
        """

        def do_epoch(action, current_epoch, epoch_count,
                     seqs, ks, log_file, val_indices, size_groups_small_gram, tv_labels):
            processed_sample_count = 0
            average_loss = 0
            gen = self.__generator_seqs_and_alpha(seqs, ks)
            start = curr_time = time.time()
            current_batch_iteration = 0
            if action == "training":
                while processed_sample_count < seqs.shape[0]:
                    # training batch
                    seqs_batch, ks_batch = next(gen)
                    batch_loss = self.model.train_on_batch(seqs_batch, ks_batch)
                    average_loss = (average_loss * processed_sample_count + batch_loss * seqs_batch.shape[0]) / \
                                   (processed_sample_count + seqs_batch.shape[0])
                    processed_sample_count += seqs_batch.shape[0]
                    prev_time = curr_time
                    curr_time = time.time()
                    elapsed_time = curr_time - start
                    eta = ((curr_time - prev_time) * seqs.shape[0] / seqs_batch.shape[0]) - elapsed_time
                    print_current_status(action, current_epoch, epoch_count,
                                         processed_sample_count, seqs.shape[0],
                                         elapsed_time, eta,
                                         average_loss, batch_loss,
                                         end='\r')
                    log_current_status(log_file, action, current_epoch, current_batch_iteration, average_loss, batch_loss)
                    current_batch_iteration += 1
                print_current_status(action, current_epoch, epoch_count,
                                     processed_sample_count, seqs.shape[0],
                                     elapsed_time, eta,
                                     average_loss, batch_loss)
                return None
            elif action == "validation":
                pred_alpha_batch_list = []
                while processed_sample_count < seqs.shape[0]:
                    seqs_batch, ks_batch = next(gen)
                    pred_alpha_batch = self.model.predict_on_batch(seqs_batch)
                    pred_alpha_batch_list.append(pred_alpha_batch)
                    processed_sample_count += seqs_batch.shape[0]
                alpha_pred = np.concatenate(pred_alpha_batch_list)
                #print("np.mean([np.count_nonzero(ap) for ap in alpha_pred]) :%d" % np.mean([np.count_nonzero(ap) for ap in alpha_pred]))
                #print("alpha_pred.shape                                     :" + repr(alpha_pred.shape))

                alpha_g_norm = calc_group_norm(size_groups_small_gram, alpha_pred)
                pred_indices = K.get_value(K.argmax(alpha_g_norm, axis=0)) # index

                print("mean density (anti-sparsity): %d/%d" % (np.mean([np.count_nonzero(a > (np.max(a) * 0.01)) for a in K.get_value(alpha_g_norm).T]),
                                                               K.get_value(K.shape(alpha_g_norm))[0]))
                print(K.get_value(alpha_g_norm).T[0])
                print(alpha_pred[0][:size_groups_small_gram[0]])
                
                labels_order = np.unique(tv_labels, return_counts=True)[0]
                true_labels = tv_labels[val_indices] # label
                true_indices = np.concatenate([np.where(labels_order == l)
                                               for l in true_labels])

                roc_auc_, f1_ = calc_scores(pred_indices, true_indices, len(labels_order))
                return (roc_auc_, f1_)
            else:
                assert False

        def log_current_status(file, action, current_epoch, batch_iteration, average_loss, batch_loss):
            if action == "training":
                text = "%d, %d, %.10f, %.10f, nan, nan\n"
            else:
                text = "%d, %d, nan, nan, %.10f, %.10f\n"
            file.write(text %
                       (current_epoch, batch_iteration,
                        average_loss, batch_loss))
            file.flush()

        def print_current_status(action, current_epoch, epoch_count,
                                 processed_sample_count, total_sample_count,
                                 elapsed_time, eta, average_loss, loss_batch,
                                 end='\n'):
            print("epoch:[%d/%d] %s:[%d/%d] %ds, ETA:%ds, ave_loss:%.10f, loss_batch:%.10f                       " %
                  (current_epoch, epoch_count,
                   action, processed_sample_count, total_sample_count,
                   elapsed_time, eta,
                   average_loss, loss_batch),
                  end=end)

        loss_file = open(logfile_loss, "w")
        wait = 0
        best_roc_auc_ = -np.inf
        best_f1_ = -np.inf
        loss_file.write("epoch, batch_iteration, average_training_loss, training_batch_loss, "
                        "validation_roc_auc_, validation_f1_\n")
        for epoch in range(1, epochs + 1):
            permutated_indices = np.random.permutation(np.arange(tv_seqs.shape[0]))
            num_tr = int(tv_seqs.shape[0] * 0.9)

            tr_indices  = permutated_indices[:num_tr]
            val_indices = permutated_indices[num_tr:]
            
            tr_seqs  = tv_seqs[tr_indices]
            val_seqs = tv_seqs[val_indices]
            
            tr_ks  = tv_ks[tr_indices]
            val_ks = tv_ks[val_indices]

            tr_labels  = tv_labels[tr_indices]
            val_labels = tv_labels[val_indices]
            
            # training
            self.sparse_rate_callback.on_epoch_begin(epoch)
            _ = do_epoch("training", epoch, epochs,
                         tr_seqs, tr_ks, loss_file,
                         None, None, None)

            # validation
            roc_auc_, f1_ = do_epoch("validation", epoch, epochs,
                                     val_seqs, val_ks, loss_file,
                                     val_indices, size_groups_small_gram, tv_labels)
            print("validation roc_auc: %f" % roc_auc_)
            print("validation f1     : %f" % f1_)

            if roc_auc_ > best_roc_auc_ or\
               (roc_auc_ == best_roc_auc_ and f1_ > best_f1_):
                best_roc_auc_ = roc_auc_
                best_f1_ = f1_
                self.sparse_rate_callback.save_best_lmbd()
                self.model.save_weights(logfile_hdf5)
                best_weights = self.model.get_weights()
                wait = 0
            else:
                if wait >= patience:
                    self.model.set_weights(best_weights)
                    break
                wait += 1
        loss_file.close()
        self.sparse_rate_callback.on_train_end()
        
    def predict(self, test_seqs):
        """Keras Siamese RNN prediction function.
        Carries out predicting for given data
        Logs results and network parameters

        :param te_indices: Testing 2-tuples of time series index pairs
        :param seqs: List of time series
        :return: Predictions

        :type te_indices: list of tuples
        :type seqs: list of np.ndarrays
        :returns: List of predicted network outputs
        :rtype: np.ndarrays
        """
        # prediction
        pred_start = time.time()
        alpha_pred = self.model.predict(test_seqs)
        pred_end = time.time()

        return alpha_pred, pred_start, pred_end
    def __generator_seqs_and_alpha(self, seqs_, ks_):
        """Siamese RNN data batch generator.
        Yields minibatches of 2 time series and their corresponding output value (Triangular Global Alignment kernel in our case)

        :param indices: 2-tuples of time series index pairs
        :param gram_drop: Gram matrix with dropped elements
        :param seqs: List of time series
        :type indices: list of tuples
        :type gram_drop: list of lists
        :type seqs: list of np.ndarrays
        :returns: Minibatch of data for Siamese RNN
        :rtype: list of np.ndarrays
        """
        batch_size_base = 32
        if self.gpu_count > 1:
            batch_size = batch_size_base * self.gpu_count
        else:
            batch_size = batch_size_base

        rest_seqs = seqs_.copy()
        rest_ks = ks_.copy()
        while rest_seqs.shape[0] > 0:
            seqs      = rest_seqs[:batch_size]
            rest_seqs = rest_seqs[batch_size:]
            ks      = rest_ks[:batch_size]
            rest_ks = rest_ks[batch_size:]
            yield (seqs, ks)
        raise StopIteration


class SoftThresholdingLayer(Layer):
    """Parametric Rectified Linear Unit.
    It follows:
    `f(x) = alpha * x for x < 0`,
    `f(x) = x for x >= 0`,
    where `alpha` is a learned array with the same shape as x.
    # Input shape
        Arbitrary. Use the keyword argument `input_shape`
        (tuple of integers, does not include the samples axis)
        when using this layer as the first layer in a model.
    # Output shape
        Same shape as the input.
    # Arguments
        alpha_initializer: initializer function for the weights.
        alpha_regularizer: regularizer for the weights.
        alpha_constraint: constraint for the weights.
        shared_axes: the axes along which to share learnable
            parameters for the activation function.
            For example, if the incoming feature maps
            are from a 2D convolution
            with output shape `(batch, height, width, channels)`,
            and you wish to share parameters across space
            so that each filter only has one set of parameters,
            set `shared_axes=[1, 2]`.
    # References
        - [Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification](https://arxiv.org/abs/1502.01852)
    """

    @interfaces.legacy_prelu_support
    def __init__(self, theta_initializer='zeros',
                 theta_regularizer=None,
                 theta_constraint=None,
                 shared_axes=None,
                 **kwargs):
        super(SoftThresholdingLayer, self).__init__(**kwargs)
        self.supports_masking = True
        self.theta_initializer = initializers.get(theta_initializer)
        self.theta_regularizer = regularizers.get(theta_regularizer)
        self.theta_constraint = constraints.get(theta_constraint)
        if shared_axes is None:
            self.shared_axes = None
        elif not isinstance(shared_axes, (list, tuple)):
            self.shared_axes = [shared_axes]
        else:
            self.shared_axes = list(shared_axes)

    def build(self, input_shape):
        print("SoftThresholdingLayer input_shape:")
        print(input_shape)
        param_shape = list(input_shape[1:])
        self.param_broadcast = [False] * len(param_shape)
        if self.shared_axes is not None:
            for i in self.shared_axes:
                param_shape[i - 1] = 1
                self.param_broadcast[i - 1] = True
        self.theta = self.add_weight(shape=param_shape,
                                     name='theta',
                                     initializer=self.theta_initializer,
                                     regularizer=self.theta_regularizer,
                                     constraint=self.theta_constraint)
        # Set input spec
        axes = {}
        if self.shared_axes:
            for i in range(1, len(input_shape)):
                if i not in self.shared_axes:
                    axes[i] = input_shape[i]
        self.input_spec = InputSpec(ndim=len(input_shape), axes=axes)
        self.built = True

    def call(self, inputs, mask=None):
        return K.sign(inputs) * K.relu(K.abs(inputs) - self.theta)

    def get_config(self):
        config = {
            'theta_initializer': initializers.serialize(self.theta_initializer),
            'theta_regularizer': regularizers.serialize(self.theta_regularizer),
            'theta_constraint': constraints.serialize(self.theta_constraint),
            'shared_axes': self.shared_axes
        }
        base_config = super(SoftThresholdingLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class GroupSoftThresholdingLayer(Layer):
    """Parametric Rectified Linear Unit.
    It follows:
    `f(x) = alpha * x for x < 0`,
    `f(x) = x for x >= 0`,
    where `alpha` is a learned array with the same shape as x.
    # Input shape
        Arbitrary. Use the keyword argument `input_shape`
        (tuple of integers, does not include the samples axis)
        when using this layer as the first layer in a model.
    # Output shape
        Same shape as the input.
    # Arguments
        alpha_initializer: initializer function for the weights.
        alpha_regularizer: regularizer for the weights.
        alpha_constraint: constraint for the weights.
        shared_axes: the axes along which to share learnable
            parameters for the activation function.
            For example, if the incoming feature maps
            are from a 2D convolution
            with output shape `(batch, height, width, channels)`,
            and you wish to share parameters across space
            so that each filter only has one set of parameters,
            set `shared_axes=[1, 2]`.
    # References
        - [Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification](https://arxiv.org/abs/1502.01852)
    """

    @interfaces.legacy_prelu_support
    def __init__(self,
                 size_groups,
                 theta_initializer='zeros',
                 theta_regularizer=None,
                 theta_constraint=None,
                 **kwargs):
        super(GroupSoftThresholdingLayer, self).__init__(**kwargs)
        self.supports_masking = True
        self.theta_initializer = initializers.get(theta_initializer)
        self.theta_regularizer = regularizers.get(theta_regularizer)
        self.theta_constraint = constraints.get(theta_constraint)

        self.size_groups = size_groups
        self.cumsum = np.cumsum(size_groups)

    def build(self, input_shape):
        param_shape = [len(self.size_groups)]
        self.param_shape = param_shape
        self.theta = self.add_weight(shape=param_shape,
                                     name='theta',
                                     initializer=self.theta_initializer,
                                     regularizer=self.theta_regularizer,
                                     constraint=self.theta_constraint)
        # Set input spec
        axes = {}
        self.input_spec = InputSpec(ndim=len(input_shape), axes=axes)
        self.built = True

    def call(self, inputs, mask=None):
        inputs_permute = K.permute_dimensions(inputs, [len(inputs.shape) - 1] + list(range(len(inputs.shape) - 1)))
        input_g = [inputs_permute[s:e] for (s, e) in zip(np.concatenate([np.array([0]), self.cumsum[:-1]]), self.cumsum)]
        input_g_norm = [K.sqrt(K.sum(K.square(g), keepdims=True) + K.epsilon()) for g in input_g]
        input_g_thres = [g / nrm * K.relu(nrm - t) for (g, nrm, t)
                         in zip(input_g, input_g_norm, [self.theta[i] for i in range(self.theta.shape[0])])]
        concat = K.concatenate(input_g_thres, axis=0)
        outputs = K.permute_dimensions(concat, list(range(1, len(inputs.shape))) + [0])
        return outputs

    def get_config(self):
        config = {
            'theta_initializer': initializers.serialize(self.theta_initializer),
            'theta_regularizer': regularizers.serialize(self.theta_regularizer),
            'theta_constraint': constraints.serialize(self.theta_constraint),
        }
        base_config = super(GroupSoftThresholdingLayer, self).get_config()
        return dict(list(base_config.items()) + list(config.items()))

class LambdaRateScheduler(Callback):
    '''Sparse rate scheduler.
    # Arguments
        schedule: a function that takes an epoch index as input
            (integer, indexed from 0) and returns a new
            learning rate as output (float).
    '''
    def __init__(self, start, end, end_epoch, dtype=K.floatx()):
        super(LambdaRateScheduler, self).__init__()
        self.var = K.variable(start, dtype=dtype, name='k')
        self.start = start
        self.end = end
        self.end_epoch = end_epoch
        self.dtype = dtype
        self.best_lmbd = np.nan

    def on_epoch_begin(self, epoch, logs={}):
        if epoch % 3 != 1:
            return
        if epoch <= self.end_epoch:
            l = np.min([epoch / self.end_epoch, 1.])
            lmbd = (1 - l) * self.start + l * self.end
            K.set_value(self.var, lmbd.astype(self.dtype))
        else:
            K.set_value(self.var, self.best_lmbd)
        print(("lmbd at epoch beginning:%f" % K.get_value(self.var)))
    def on_train_end(self, logs=None):
        print(("lmbd at ending         :%f" % K.get_value(self.var)))
        """
        K.set_value(self.var, self.end)
        print(("lmbd at epoch ending   :%f" % K.get_value(self.var)))
        """
    def save_best_lmbd(self):
        self.best_lmbd = K.get_value(self.var)
        print(("save lmbd as best      :%f" % K.get_value(self.var)))

class KSS_Loss:
    def __init__(self, lmbd, gram, size_groups):
        self.lmbd = lmbd
        self.__name__ = "custom"
        self.cumsum = np.cumsum(size_groups)
        group_start_and_end = [(s, e) for (s, e) in zip(np.concatenate([np.array([0]), self.cumsum[:-1]]), self.cumsum)]
        self.group_indices = [K.variable(np.arange(s, e), dtype='int32') for (s, e) in group_start_and_end]
        self.gram_sliced = [K.variable(gram[s:e]) for (s, e) in group_start_and_end]
    def __call__(self, k_true, alpha_pred):
        # alpha_pred: [sample, dict]
        alpha_pred_T = K.transpose(alpha_pred) # [dict, sample]

        dot = K.concatenate([K.dot(g, alpha_pred_T) for g in self.gram_sliced], axis=0)
        
        quad = K.batch_dot(alpha_pred_T, dot, axes=0)
        linear = K.batch_dot(k_true, alpha_pred, axes=1)

        alpha_g_norm = [K.sqrt(K.sum(K.square(K.gather(alpha_pred_T, g)), axis=0) + K.epsilon()) for g in self.group_indices]
        reg = K.sum(K.stack(alpha_g_norm), axis=0)
        #alpha_g = K.stack([K.gather(alpha_pred_T, g) for g in self.group_indices]) # [group, dict/group, sample]
        #alpha_g_norm = K.sqrt(K.sum(K.square(alpha_g), axis=1) + K.epsilon()) # [group, sample]
        #reg = K.sum(alpha_g_norm, axis=0)
        
        return K.mean(.5 * K.flatten(quad) - K.flatten(linear) + self.lmbd * reg) + 10000
        """
        #alpha_pred_permute = K.permute_dimensions(alpha_pred, [len(alpha_pred.shape) - 1] + list(range(len(alpha_pred.shape) - 1)))
        alpha_pred_permute = K.permute_dimensions(alpha_pred, self.alpha_permute_order)
        alpha_permute_g = K.gather(alpha_pred_permute, self.group_indices)
        #alpha_permute_g_norm = [K.sqrt(K.sum(K.square(g), axis=1) + K.epsilon()) for g in alpha_permute_g]
        alpha_permute_g_norm = K.sqrt(K.sum(K.square(alpha_permute_g), axis=1) + K.epsilon())
        #alpha_g_norm = K.permute_dimensions(alpha_permute_g_norm, [len(alpha_pred.shape) - 1] + list(range(len(alpha_pred.shape) - 1)))
        alpha_g_norm = K.permute_dimensions(alpha_permute_g_norm, self.alpha_permute_order)
        reg = K.sum(K.stack(alpha_g_norm))

    
        #start_and_end = zip(np.concatenate([np.array([0]), cumsum[:-1]]), cumsum)
        #unstack_alpha = tf.unstack(alpha_pred, axis=1)
        #group_norms = [K.sqrt(K.sum(K.square(a[s:e])) + K.epsilon()) for (s, e) in start_and_end for a in unstack_alpha]
        #reg = K.stack(K.sum(group_norms))
        """


