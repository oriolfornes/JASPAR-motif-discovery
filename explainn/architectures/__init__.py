from Bio import motifs
from collections import OrderedDict
import math
import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score
import torch
import torch.nn as nn
import warnings
warnings.filterwarnings("ignore")

class ExpAct(nn.Module):
    """Exponential Activation."""

    def _init_(self):
        super(ExpAct, self)._init_()

    def forward(self, x):
        return(torch.exp(x))

class UnSqueeze(torch.nn.Module):
    def forward(self, x):
        return(x.unsqueeze(-1))

class _Model(nn.Module):

    def load_weights(self, weight_file):
        sd = torch.load(weight_file)
        ord_dict = OrderedDict()
        keys = list(self.state_dict().keys())
        values = list(sd.values())
        for i in range(len(values)):
            v = values[i]
            if v.dim() > 1:
                if v.shape[-1] == 1:
                    ord_dict[keys[i]] = v.squeeze(-1)
                    continue
            ord_dict[keys[i]] = v
        self.load_state_dict(ord_dict)

class ExplaiNN(_Model):
    """ExplaiNN: explainable neural networks."""

    def __init__(self, cnn_units, kernel_size, sequence_length, n_features=1,
        weights_file=None):
        """
        Parameters
        ----------
        cnn_units : int
            Total number of individual CNN units
        kernel_size : int
            Convolutional kernel size
        sequence_length : int
            Input sequence length
        n_features : int
            Total number of features to predict
        weights_file : pass
        """
        super(ExplaiNN, self).__init__()

        self._options = {
            "cnn_units": cnn_units,
            "kernel_size": kernel_size,
            "sequence_length": sequence_length,
            "n_features": n_features,
            "weights_file": weights_file,
        }

        n = math.floor((sequence_length - kernel_size + 1) / 7.)
        self.__channels_after_maxpool = n

        self.linears = nn.Sequential(
            nn.Conv1d(
                in_channels=4*cnn_units,
                out_channels=1*cnn_units,
                kernel_size=kernel_size,
                groups=cnn_units,
            ),
            nn.BatchNorm1d(cnn_units),
            ExpAct(),
            nn.MaxPool1d(7, 7),
            nn.Flatten(), 
            UnSqueeze(),
            nn.Conv1d(
                in_channels=self.__channels_after_maxpool*cnn_units,
                out_channels=100*cnn_units,
                kernel_size=1,
                groups=cnn_units,
            ),
            nn.BatchNorm1d(100*cnn_units, 1e-05, 0.1, True),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Conv1d(
                in_channels=100*cnn_units,
                out_channels=1*cnn_units,
                kernel_size=1,
                groups=cnn_units
            ),
            nn.BatchNorm1d(1*cnn_units, 1e-05, 0.1, True),
            nn.ReLU(),
            nn.Flatten(),
        )

        self.final = nn.Linear(cnn_units, n_features)

        if weights_file is not None:
            self.load_weights(weights_file)

    def forward(self, x):
        """Forward propagation of a batch."""
        x = x.repeat(1, self._options["cnn_units"], 1)
        o = self.linears(x)

        return(self.final(o))

class PWM(nn.Module):
    """PWM (Position Weight Matrix)."""

    def __init__(self, pwms, sequence_length, scoring="sum"):
        """
        Parameters
        ----------
        pwms : list
            List of PWMs; PWMs should be encoded as numpy
            arrays with shape = (4, PWM length); the four
            nt should be provided in the "ACGT" order
        sequence_length: int
            Input sequence length
        scoring : max | sum
            Return either the max. score or the sum occupancy
            score for each sequence
        """
        super(PWM, self).__init__()

        groups, _, kernel_size = pwms.shape

        self._options = {
            "groups": groups,
            "kernel_size": kernel_size,
            "sequence_length": sequence_length,
            "scoring": scoring
        }

        self.conv1d = nn.Conv1d(
            in_channels=4*groups,
            out_channels=1*groups,
            kernel_size=kernel_size,
            groups=groups,
        )

        # No bias
        self.conv1d.bias.data = torch.Tensor([0.]*groups)

        # Set weights to PWM weights
        self.conv1d.weight.data = torch.Tensor(pwms)

        # Freeze
        for p in self.conv1d.parameters():
            p.requires_grad = False

    def forward(self, x):
        """Forward propagation of a batch."""
        x_rev = _flip(_flip(x, 1), 2)
        o = self.conv1d(x.repeat(1, self._options["groups"], 1))
        o_rev = self.conv1d(x_rev.repeat(1, self._options["groups"], 1))
        o = torch.cat((o, o_rev), 2)
        if self._options["scoring"] == "max":
            return(torch.max(o, 2)[0])
        else:
            return(torch.sum(o, 2))

        #return(torch.nn.Sequential(conv1d, maxpool1d).to(device))

#     # def __init__(self, cnn_units, kernel_size, sequence_length, n_features=1,
#     #     clamp_weights=False, no_padding=False, weights_file=None):
#     #     """
#     #     Parameters
#     #     ----------
#     #     cnn_units : int
#     #         Total number of individual CNN units
#     #     kernel_size : int
#     #         Convolutional kernel size
#     #     sequence_length : int
#     #         Input sequence length
#     #     n_features : int
#     #         Total number of features to predict
#     #     weights_file : pass
#     #         ...
#     #     """
#     #     super(CAM, self).__init__()

#     #     self._options = {
#     #         "cnn_units": cnn_units,
#     #         "kernel_size": kernel_size,
#     #         "sequence_length": sequence_length,
#     #         "n_features": n_features,
#     #         "clamp_weights": clamp_weights,
#     #         "no_padding": no_padding,
#     #         "weights_file": weights_file,
#     #     }

#     #     if no_padding:
#     #         self.__n_channels = math.floor((sequence_length-kernel_size+1)/7.)
#     #         self.__padding = 0
#     #     else:
#     #         self.__n_channels = math.floor((sequence_length+kernel_size+1)/7.)
#     #         self.__padding = kernel_size

#     #     self.linears = nn.Sequential(
#     #         nn.Conv1d(
#     #             in_channels=4*cnn_units,
#     #             out_channels=1*cnn_units,
#     #             kernel_size=kernel_size,
#     #             padding=self.__padding,
#     #             groups=cnn_units,
#     #         ),
#     #         nn.BatchNorm1d(cnn_units),
#     #         ExpAct(),
#     #         nn.MaxPool1d(7, 7),
#     #         nn.Flatten(), 
#     #         UnSqueeze(),
#     #         nn.Conv1d(
#     #             in_channels=self.__n_channels*cnn_units,
#     #             out_channels=100*cnn_units,
#     #             kernel_size=1,
#     #             groups=cnn_units,
#     #         ),
#     #         nn.BatchNorm1d(100*cnn_units, 1e-05, 0.1, True),
#     #         nn.ReLU(),
#     #         nn.Dropout(0.3),
#     #         nn.Conv1d(
#     #             in_channels=100*cnn_units,
#     #             out_channels=1*cnn_units,
#     #             kernel_size=1,
#     #             groups=cnn_units
#     #         ),
#     #         nn.BatchNorm1d(1*cnn_units, 1e-05, 0.1, True),
#     #         nn.ReLU(),
#     #         nn.Flatten(),
#     #     )

#     #     self.final = nn.Linear(cnn_units, n_features)

#     #     if weights_file is not None:
#     #         self.load_weights(weights_file)

#     # def forward(self, x):
#     #     """Forward propagation of a batch."""
#     #     x = x.repeat(1, self._options["cnn_units"], 1)
#     #     o = self.linears(x)

#     #     return(self.final(o))

# class Basset(nn.Module):
#     """Basset architecture (Kelley, Snoek & Rinn, 2016)."""

#     def __init__(self, sequence_length, n_features=1, output="binary"):
#         """
#         Parameters
#         ----------
#         sequence_length : int
#             Input sequence length
#         n_features : int
#             Total number of features to predict
#         """
#         super(Basset, self).__init__()

#         padding = math.floor((200 - sequence_length) / 2.)

#         self.blk1 = nn.Sequential(
#             nn.Conv1d(4, 100, kernel_size=19, padding=padding),
#             nn.BatchNorm1d(100),
#             nn.ReLU(inplace=True)
#         )
#         self.max_pool = nn.MaxPool1d(kernel_size=3, stride=3)
    
#         self.blk2 = nn.Sequential(
#             nn.Conv1d(100, 200, kernel_size=7),
#             nn.BatchNorm1d(200),
#             nn.ReLU(inplace=True),
#             nn.MaxPool1d(kernel_size=3, stride=3)
#         )

#         self.blk3 = nn.Sequential(
#             nn.Conv1d(200, 200, kernel_size=4),
#             nn.BatchNorm1d(200),
#             nn.ReLU(inplace=True),
#             nn.MaxPool1d(kernel_size=3, stride=3)
#         )

#         self.fc1 = nn.Sequential(
#             nn.Linear(1000, 1000),
#             nn.BatchNorm1d(1000, 1e-05, 0.1, True),
#             nn.ReLU(inplace=True),
#             nn.Dropout(0.3)
#         )

#         self.fc2 = nn.Sequential(
#             nn.Linear(1000, 1000),
#             nn.BatchNorm1d(1000, 1e-05, 0.1, True),
#             nn.ReLU(inplace=True),
#             nn.Dropout(0.3)
#         )

#         self.fc3 = nn.Sequential(
#             nn.Linear(1000, n_features)
#         )
#         if output == "binary":
#             self.fc3.add_module("Sigmoid", nn.Sigmoid())

#     def forward(self, x):
#         """Forward propagation of a batch."""
#         o = self.blk1(x)
#         # Save activations from 1st layer
#         # (activations, act_index) = torch.max(o, dim=2)
#         o = self.max_pool(0)
#         o = self.blk2(o)
#         o = self.blk3(o)
#         o = torch.flatten(o, start_dim=1)
#         o = self.fc1(o)
#         o = self.fc2(o)

#         return(self.fc3(o))

# DanQ Pytorch implementation 
# From: https://github.com/PuYuQian/PyDanQ/blob/master/DanQ_train.py
class DanQ(_Model):
    """DanQ architecture (Quang & Xie, 2016)."""

    def __init__(self, sequence_length, n_features=1, weights_file=None):
        """
        Parameters
        ----------
        sequence_length : int
            Input sequence length
        n_features : int
            Total number of features to predict
        weights_file : pass
        """
        super(DanQ, self).__init__()

        self._options = {
            "sequence_length": sequence_length,
            "n_features": n_features,
            "weights_file": weights_file,
        }

        n = math.floor((sequence_length - 25) / 13.)
        self.__channels_after_bilstm = n
  
        self.Conv1 = nn.Conv1d(
            in_channels=4,
            out_channels=320,
            kernel_size=26,
            padding=0,
        )
        self.Maxpool = nn.MaxPool1d(kernel_size=13, stride=13)
        self.Drop1 = nn.Dropout(p=0.2)
        self.BiLSTM = nn.LSTM(
            input_size=320,
            hidden_size=320,
            num_layers=2,
            batch_first=True,
            dropout=0.5,
            bidirectional=True
        )
        self.Linear1 = nn.Linear(self.__channels_after_bilstm*640, 925)
        self.Linear2 = nn.Linear(925, n_features)

        if weights_file is not None:
            self.load_weights(weights_file)

    def forward(self, x):
        """Forward propagation of a batch."""
        o = self.Conv1(x)
        o = nn.functional.relu(o)
        o = self.Maxpool(o)
        o = self.Drop1(o)
        o_o = torch.transpose(o, 1, 2)
        o , _ = self.BiLSTM(o_o)
        o = o.contiguous().view(-1, self.__channels_after_bilstm*640)
        o = self.Linear1(o)
        o = nn.functional.relu(o)

        return(self.Linear2(o))

def _flip(x, dim):
    """
    Adapted from Selene:
    https://github.com/FunctionLab/selene/blob/master/selene_sdk/utils/non_strand_specific_module.py

    Reverses the elements in a given dimension `dim` of the Tensor.
    source: https://github.com/pytorch/pytorch/issues/229
    """
    xsize = x.size()
    dim = x.dim() + dim if dim < 0 else dim
    x = x.contiguous()
    x = x.view(-1, *xsize[dim:])
    x = x.view(
        x.size(0), x.size(1), -1)[:, getattr(
            torch.arange(x.size(1)-1, -1, -1),
            ("cpu","cuda")[x.is_cuda])().long(), :]

    return(x.view(xsize))

# class NonStrandSpecific(nn.Module):
#     """
#     Adapted from Selene:
#     https://github.com/FunctionLab/selene/blob/master/selene_sdk/utils/non_strand_specific_module.py

#     A torch.nn.Module that wraps a user-specified model architecture if the
#     architecture does not need to account for sequence strand-specificity.

#     Parameters
#     ----------
#     model : torch.nn.Module
#         The user-specified model architecture.
#     mode : {'mean', 'max'}, optional
#         Default is 'mean'. NonStrandSpecific will pass the input and the
#         reverse-complement of the input into `model`. The mode specifies
#         whether we should output the mean or max of the predictions as
#         the non-strand specific prediction.

#     Attributes
#     ----------
#     model : torch.nn.Module
#         The user-specified model architecture.
#     mode : {'mean', 'max'}
#         How to handle outputting a non-strand specific prediction.
#     """

#     def __init__(self, model):
#         super(NonStrandSpecific, self).__init__()

#         self.model = model

#     def forward(self, input):
#         reverse_input = None
#         reverse_input = _flip(_flip(input, 1), 2)

#         output = self.model.forward(input)
#         output_from_rev = self.model.forward(reverse_input)

#         return((output + output_from_rev) / 2)

def get_loss(input_data="binary"):
    """
    Specify the appropriate loss function (criterion) for this model.

    Returns
    -------
    torch.nn._Loss
    """
    if input_data == "binary":
        return(nn.BCEWithLogitsLoss())
    return(nn.MSELoss())

def get_metrics(input_data="binary"):
    if input_data == "binary":
        return(dict(aucROC=roc_auc_score, aucPR=average_precision_score))
    return(dict(Pearson=pearsonr, Spearman=spearmanr))

def get_optimizer(params, lr=1e-03):
    return(torch.optim.Adam(params, lr=lr))