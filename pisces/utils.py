# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_utils.ipynb.

# %% auto 0
__all__ = ['WASA_THRESHOLD', 'BALANCE_WEIGHTS', 'determine_header_rows_and_delimiter', 'ActivityCountAlgorithm',
           'build_activity_counts', 'build_ADS', 'build_activity_counts_te_Lindert_et_al', 'plot_scores_CDF',
           'plot_scores_PDF', 'constant_interp', 'avg_steps', 'add_rocs', 'pad_to_hat', 'mae_func', 'Constants',
           'SleepMetricsCalculator', 'split_analysis']

# %% ../nbs/00_utils.ipynb 4
import csv
import os
import time
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path

import numpy as np

# %% ../nbs/00_utils.ipynb 6
def determine_header_rows_and_delimiter(
    filename: Path | str
) -> Tuple[Optional[int], Optional[str]]:
    """
    Given a filename pointing at a CSV files, decides:
     * how many header lines there are (based on first line starting with a digit)
     * the delimiter-- right now tries whitespace and comma

    Returns one of:
     - (number of header rows, column delimiter),
     - (number of header rows, None) if the delimiter could not be inferred,
     - (None, None) if CSV has no numerical rows,

    :param filename: CSV Path or filepath literal
    :return: header and delimiter information, if possible.
    """
    MAX_ROWS = 100  # if you don't have data within first 100 lines, exit.
    header_row_count = 0
    with open(filename) as f:
        header_found = False
        line = ""  # modified in while below

        # Search over lines until we find one starting with a digit
        while not header_found:
            line = f.readline()
            if line == "":  # last line of file reached
                return None, None
            line = line.strip()
            try:
                int(line[0])
                header_found = True
            except ValueError:
                header_row_count += 1
            except IndexError:
                header_row_count += 1

            # guard against infinite loop
            if header_row_count >= MAX_ROWS:
                return None, None

        # Now try splitting that first line of data
        delim_guesses = [" ", ",", ", "]

        for guess in delim_guesses:
            try:
                comps = line.split(guess)  # whitespace separated?
                float(comps[0])
                return header_row_count, guess
            except ValueError:
                continue
        return header_row_count, None


# %% ../nbs/00_utils.ipynb 8
class ActivityCountAlgorithm(Enum):
    te_Lindert_et_al = 0
    ADS = 2


def build_activity_counts(
    data,
    axis: int = 3,
    prefix: str = "",
    algorithm: ActivityCountAlgorithm = ActivityCountAlgorithm.ADS
) -> Tuple[np.ndarray, np.ndarray]:
    if algorithm == ActivityCountAlgorithm.ActiGraphOfficial:
        print("No longer implemented due to conflicts with the `agcounts` package.")
    if algorithm == ActivityCountAlgorithm.ADS:
        return build_ADS(data)
    if algorithm == ActivityCountAlgorithm.te_Lindert_et_al:
        return build_activity_counts_te_Lindert_et_al(data, axis, prefix)


# %% ../nbs/00_utils.ipynb 9
def build_ADS(
    time_xyz: np.ndarray,
    sampling_hz: float = 50.0,
    bin_size_seconds: float = 15,
    prefix: str = "",
) -> Tuple[np.ndarray, np.ndarray]:
    """ADS algorithm for activity counts, developed by Arcascope with support from the NHRC.

    Parameters
    ---
     - `time_xyz`: numpy array with shape (N_samples, 4) where the 4 coordinates are: [time, x, y, z] 
     - `sampling_hz`: `float` sampling frequency of thetime_xyz 
    """
    data_shape_error = ValueError(
            f"`time_xyz` must have shape (N_samples, 4) but has shape {time_xyz.shape}"
        )
    try:
        assert (len(time_xyz.shape) == 2 and time_xyz.shape[1] == 4)
    except AssertionError:
        raise data_shape_error

    time_data_raw = time_xyz[:, 0]
    x_accel = time_xyz[:, 1]
    y_accel = time_xyz[:, 2]
    z_accel = time_xyz[:, 3]

    # Interpolate to sampling Hz
    time_values = np.arange(
        np.amin(time_data_raw), np.amax(time_data_raw), 1 / sampling_hz
    )
    # Must do each coordinate separately
    x_data = np.interp(time_values, time_data_raw, x_accel)
    y_data = np.interp(time_values, time_data_raw, y_accel)
    z_data = np.interp(time_values, time_data_raw, z_accel)

    # Calculate "amplitude" = timeseries of 2-norm of (x, y, z)
    amplitude = np.linalg.norm(np.array([x_data, y_data, z_data]), axis = 0)

    abs_amplitude_deriv = np.abs(np.diff(amplitude))
    abs_amplitude_deriv = np.insert(abs_amplitude_deriv, 0, 0)

    # Binning step
    # Sum abs_amplitude_deriv in time-based windows
    # ex: bin_size_seconds = 15
    # Step from first to last time by 15 seconds
    time_counts = np.arange(
        np.amin(time_data_raw), np.amax(time_data_raw), bin_size_seconds
    )

    # Convert time at 50 hz to "# of 15 second windows past start"
    bin_values = (time_values - time_values[0]).astype(int) // bin_size_seconds
    sums_in_bins = np.bincount(bin_values, abs_amplitude_deriv)
    sums_in_bins[sums_in_bins <= 0.05 * max(sums_in_bins)] = 0.0
    return time_counts, sums_in_bins




# %% ../nbs/00_utils.ipynb 10
from scipy.signal import butter, filtfilt

def build_activity_counts_te_Lindert_et_al(
    time_xyz, axis: int = 3, prefix: str = ""
) -> Tuple[np.ndarray, np.ndarray]:
    """Implementation of the reverse-engineered activity count algorithm from
    te Lindert BH, Van Someren EJ. Sleep. 2013
    Sleep estimates using microelectromechanical systems (MEMS). 
    doi: 10.5665/sleep.2648
    
    :param time_xyz: `np.ndarray` loaded from timestamped triaxial accelerometer CSV. Shape (N, 4)
    :return: (time, activity counts with 15 second epoch)
    """

    # a helper function to calculate max over 2 epochs
    def max2epochs(data, fs, epoch):
        data = data.flatten()

        seconds = int(np.floor(np.shape(data)[0] / fs))
        data = np.abs(data)
        data = data[0 : int(seconds * fs)]

        data = data.reshape(fs, seconds, order="F").copy()

        data = data.max(0)
        data = data.flatten()
        N = np.shape(data)[0]
        num_epochs = int(np.floor(N / epoch))
        data = data[0 : (num_epochs * epoch)]

        data = data.reshape(epoch, num_epochs, order="F").copy()
        epoch_data = np.sum(data, axis=0)
        epoch_data = epoch_data.flatten()

        return epoch_data
    
    fs = 50
    time = np.arange(np.amin(time_xyz[:, 0]), np.amax(time_xyz[:, 0]), 1.0 / fs)
    z_data = np.interp(time, time_xyz[:, 0], time_xyz[:, axis])

    cf_low = 3
    cf_hi = 11
    order = 5
    w1 = cf_low / (fs / 2)
    w2 = cf_hi / (fs / 2)
    pass_band = [w1, w2]
    b, a = butter(order, pass_band, "bandpass")

    z_filt = filtfilt(b, a, z_data)
    z_filt = np.abs(z_filt)

    top_edge = 5
    bottom_edge = 0
    number_of_bins = 128

    bin_edges = np.linspace(bottom_edge, top_edge, number_of_bins + 1)
    binned = np.digitize(z_filt, bin_edges)
    epoch = 15
    counts = max2epochs(binned, fs, epoch)
    counts = (counts - 18) * 3.07
    counts[counts < 0] = 0

    time_counts = np.linspace(np.min(time_xyz[:, 0]), max(time_xyz[:, 0]), np.shape(counts)[0])
    time_counts = np.expand_dims(time_counts, axis=1)
    counts = np.expand_dims(counts, axis=1)

    return time_counts, counts

# %% ../nbs/00_utils.ipynb 12
from typing import Any, List
from matplotlib import pyplot as plt
import numpy as np

def plot_scores_CDF(scores: List[float], ax: plt.Axes = None, label: str = None, color: str = None):
    """Plot the cumulative dist function (CDF) of the scores."""
    # plt.figure(figsize=(20, 10))
    if ax is None:
        _, ax = plt.subplots()
    ax.set_xlim(0, 1)
    _ = ax.hist(scores,
                cumulative=True,
                density=True,
                bins=100,
                label=label,
                color=color,)


def plot_scores_PDF(
        scores: List[float], 
        ax: plt.Axes = None, 
        label: str = None, 
        hist_color: str = None, 
        mean_color: str = 'tab:orange', 
        stdev_color: str = 'gray', 
        alpha: float = 1.0
        ):
    """Plot the probability dist function (PDF) of the scores."""
    ax_ = ax
    if ax is None:
        _, ax_ = plt.subplots()
    ax_.set_xlim(0, 1)
    _ = ax_.hist(scores, bins=20,
                density=True,   
                label=label,
                color=hist_color,
                alpha=alpha,
                )

    # plot the mean as a vertical 'tab:orange' line
    mean_score = np.mean(scores)
    ax_.axvline(mean_score, color=mean_color, linestyle='--', label=f"Mean: {mean_score:.3f}")
    stdev_score = np.std(scores)
    ax_.axvline(mean_score - stdev_score, color=stdev_color, linestyle='--', label=f"Std. Dev: {stdev_score:.3f}")
    ax_.axvline(mean_score + stdev_score, color=stdev_color, linestyle='--')
    if ax is None:
        ax_.legend()

# %% ../nbs/00_utils.ipynb 13
def constant_interp(
    x: np.ndarray, xp: np.ndarray, yp: np.ndarray, side: str = "right"
) -> np.ndarray:
    # constant interpolation, from https://stackoverflow.com/a/39929401/3856731
    indices = np.searchsorted(xp, x, side=side)
    y2 = np.concatenate(([0], yp))

    return y2[indices]

def avg_steps(
    xs: List[List[float]], ys: List[List[float]]
) -> Tuple[np.ndarray, np.ndarray]:
    """Computes average of step functions.

    Each ys[j] is thought of as a right-continuous step function given by

    `ys[j](x) = xs[j][i]`
    for
    `xs[j][i] <= x < xs[j][i+1]`

    This function returns two NumPy arrays, `(inputs, outputs)`, giving the pointwise average
    (see below) of these functions, one for inputs and one for outputs.
    These output arrays can be considered to give another step function.

    For a list of functions `[f_1, f_2, ..., f_n]`, their pointwise average
    is the function `f_bar` defined by

    `f_bar(x) = (1/n)(f_1(x) + f_2(x) + ... + f_n(x))`

    Returns
    ---
    `inputs`: `np.ndaray`
        The union of all elements of all vectors in `xs`; this is the mutual domain
        of the average function.
    `outputs`: `np.ndarray`
        The pointwise average of the `ys[j]`s, considered as step functions extended
        to the full real line by assuming constant values for `x < min(xs[j])`
        or `x > max(xs[j])`
    """
    all_xs = []

    # Start by removing extraneous dims
    xs = [np.squeeze(x) for x in xs]
    ys = [np.squeeze(y) for y in ys]

    for j in range(len(xs)):
        x = xs[j]
        y = ys[j]
        # union all x-values
        all_xs += list(x)

        # ensure array values are sorted
        x_sort = np.argsort(x)
        xs[j] = x[x_sort]
        ys[j] = y[x_sort]

    all_xs = list(set(all_xs))
    all_xs.sort()

    all_xs = np.array(all_xs)

    # Holds constant-interpolated step fns as rows (axis 0).
    # We "evaluate" ys[j] for every x-value in `all_xs`
    # Easy to average via np.mean(all_curves, axis=0)
    all_curves = np.zeros((len(xs), len(all_xs)))

    for j, (x, y) in enumerate(zip(xs, ys)):
        x, y = np.array(x), np.array(y)
        all_curves[j] = constant_interp(all_xs, x, y, side="right")

    avg_curve = np.mean(all_curves, axis=0)

    return all_xs, avg_curve


# %% ../nbs/00_utils.ipynb 14
from typing import List

from sklearn.metrics import auc as auc_score

def add_rocs(fprs: List[np.ndarray],
             tprs: List[np.ndarray],
             x_class: str = "SLEEP",
             y_class: str = "WAKE", 
             min_auc: float = 0.0,
             avg_curve_color: str = "tab:blue",
             specific_curve_color: str = "tab:orange",
             roc_group_name: str = "", 
             ax: plt.Axes | None = None):
    """
    Adds ROC curves to the given plot, or makes a new plot if ax is None.

    if ax is None, we are making a new plot. We do additional formatting
    in this case, such as adding the legend and showing the plot. 
    
    When `ax` is provided, we expect the call site to do formatting.
    """
    # don't overwrite ax, this lets us use the None info later on 
    # to automatically show the legend and do other formatting, 
    # which otherwise we'd expect the call site to peform on `ax`
    resolved_ax = ax if ax is not None else plt.subplots()[1]
    aucs = np.array([
        auc_score(fpr, tpr)
        for fpr, tpr in zip(fprs, tprs)
    ])

    all_fprs, avg_curve = avg_steps(
            xs=[list(fprs[i]) for i in range(len(aucs)) if aucs[i] > min_auc],
            ys=[list(tprs[i]) for i in range(len(aucs)) if aucs[i] > min_auc],
        )

    avg_auc = np.mean(aucs[aucs > min_auc])

    resolved_ax.step(
        all_fprs,
        avg_curve,
        c=avg_curve_color,
        where="post",
        label=f"{roc_group_name + ' ' * bool(roc_group_name)}All splits avg ROC-AUC: {avg_auc:0.3f}",
    )
    for roc in zip(fprs, tprs):
        resolved_ax.step(roc[0], roc[1], c=specific_curve_color, alpha=0.2, where="post")
    resolved_ax.plot([0, 1], [0, 1], "-.", c="black")

    resolved_ax.set_ylabel(f"Fraction of {y_class} scored as {y_class}")
    resolved_ax.set_xlabel(f"Fraction of {x_class} scored as {y_class}")

    resolved_ax.spines["top"].set_visible(False)
    resolved_ax.spines["right"].set_visible(False)

    if ax is None:
        # show the legend if we are making a new plot
        # otherwise, the call site might want to make their own legend, leave it.
        resolved_ax.legend()
        plt.show()

# %% ../nbs/00_utils.ipynb 16
import warnings


def pad_to_hat(y: np.ndarray, y_hat: np.ndarray) -> np.ndarray:
    """Adds zeros to the end of y to match the length of y_hat.

    Useful when the inputs had to be padded with zeros to match shape requirements for dense layers.
    """
    pad = y_hat.shape[-1] - y.shape[-1]
    if pad < 0:
        warnings.warn(f"y_hat is shorter than y by {-pad} elements, trimming y.")
        return y[:pad]
    y_padded = np.pad(y, (0, pad), constant_values=0)
    return y_padded

# %% ../nbs/00_utils.ipynb 17
from typing import Callable


def mae_func(
    func: Callable[[np.ndarray], float],
    trues: List[np.ndarray],
    preds: List[np.ndarray],
) -> float:
    """Computes Mean Absolute Error (MAE) for the numerical function `func` on the given lists.

    This function is useful for computing MAE of statistical functions giving a single float
    for every NumPy array.

    Parameters
    ---
    `func`: callable `(np.ndarray) -> float`
        The statistic we are computing for truth/prediction arrays. It is called on each element
        of the lists of NumPy arrays, then MAE of the resulting statistic lists is computed.
    `trues`: `list` of `np.ndarray`
        The "True" labels, eg. This function is symmetric in `trues` and `preds`, and isn't specific
        to classifiers, so the argument names are just mnemonics.
    `preds`: `list` of `np.ndarray`
        The "Predicted" labels, eg.

    Returns
    ---
    MAE of `func` applied to elements of `trues` and `preds`.
    """
    assert len(trues) == len(preds)

    # aes = (A)bsolute (E)rror(S)
    # We will take the mean of this list for Mean Absolute Error
    aes = list(
        map(lambda ab: abs(ab[0] - ab[1]), zip(map(func, trues), map(func, preds)))
    )

    return sum(aes) / len(aes)


# %% ../nbs/00_utils.ipynb 19
from sklearn.metrics import roc_auc_score, roc_curve
from functools import partial


class Constants:
    # WAKE_THRESHOLD = 0.3  # These values were used for scikit-learn 0.20.3, See:
    # REM_THRESHOLD = 0.35  # https://scikit-learn.org/stable/whats_new.html#version-0-21-0
    WAKE_THRESHOLD = 0.5  #
    REM_THRESHOLD = 0.35

    DEFAULT_EPOCH_DURATION_IN_SECONDS = 30
    SECONDS_PER_MINUTE = 60
    SECONDS_PER_DAY = 3600 * 24
    SECONDS_PER_HOUR = 3600
    VERBOSE = True


class SleepMetricsCalculator:
    @staticmethod
    def get_tst(labels, epoch_seconds: float | None = 30.0):
        tst = np.sum(labels > 0)
        epoch_seconds = (
            epoch_seconds
            if epoch_seconds is not None
            else Constants.DEFAULT_EPOCH_DURATION_IN_SECONDS
        )
        return tst * epoch_seconds / Constants.SECONDS_PER_MINUTE

    @staticmethod
    def get_wake_after_sleep_onset(labels, epoch_seconds: float | None = 30.0):
        select = labels >= 0
        labels = labels[select]
        sleep_indices = np.argwhere(labels > 0)

        epoch_seconds = (
            epoch_seconds
            if epoch_seconds is not None
            else Constants.DEFAULT_EPOCH_DURATION_IN_SECONDS
        )
        if np.shape(sleep_indices)[0] > 0:
            sol_index = np.amin(sleep_indices)
            indices_where_wake_occurred = np.where(labels == 0)

            waso_indices = np.where(indices_where_wake_occurred > sol_index)
            waso_indices = waso_indices[1]
            number_waso_indices = np.shape(waso_indices)[0]
            return number_waso_indices * epoch_seconds / Constants.SECONDS_PER_MINUTE
        else:
            # print("*" * 10 + "get_wake_after_sleep_onset" + "*" * 10)
            # print(labels)
            return len(labels) * epoch_seconds / Constants.SECONDS_PER_MINUTE

    @staticmethod
    def get_sleep_efficiency(labels):
        sleep_indices = np.where(labels > 0)
        sleep_efficiency = float(np.shape(sleep_indices)[1]) / float(
            np.shape(labels)[0]
        )
        return sleep_efficiency

    @staticmethod
    def get_sleep_onset_latency(labels, epoch_seconds: Optional[float]):
        sleep_indices = np.argwhere(labels > 0)
        epoch_seconds = (
            epoch_seconds
            if epoch_seconds is not None
            else Constants.DEFAULT_EPOCH_DURATION_IN_SECONDS
        )
        if np.shape(sleep_indices)[0] > 0:
            return np.amin(sleep_indices) * epoch_seconds / Constants.SECONDS_PER_MINUTE
        else:
            return len(labels) * epoch_seconds / Constants.SECONDS_PER_MINUTE

    @staticmethod
    def get_time_in_rem(labels, epoch_seconds: Optional[float]):
        rem_epoch_indices = np.where(labels == 2)
        rem_time = np.shape(rem_epoch_indices)[1]
        return rem_time * epoch_seconds / Constants.SECONDS_PER_MINUTE

    @staticmethod
    def get_time_in_nrem(labels, epoch_seconds: Optional[float]):
        rem_epoch_indices = np.where(labels == 1)
        rem_time = np.shape(rem_epoch_indices)[1]
        return rem_time * epoch_seconds / Constants.SECONDS_PER_MINUTE

    @classmethod
    def report_mae_tst_waso(
        cls,
        y_pred_y_true: List[Tuple[np.ndarray, np.ndarray]],
        sleep_acc: float = 0.93,
        epoch_seconds: Optional[float] = 30,
    ) -> Dict[str, float]:
        res = {"mae_tst_minutes": [], "mae_waso_minutes": []}
        preds = []
        trues = []
        for pred, true in y_pred_y_true:
            fprs, tprs, thresholds = roc_curve(true, pred)
            threshold = thresholds[np.argmax(fprs <= (1 - sleep_acc))]
            preds.append(pred >= threshold)
            trues.append(true)

        tst_func = partial(cls.get_tst, epoch_seconds=epoch_seconds)
        waso_func = partial(cls.get_wake_after_sleep_onset, epoch_seconds=epoch_seconds)
        res["mae_tst_minutes"] = mae_func(tst_func, trues=trues, preds=preds)
        res["mae_waso_minutes"] = mae_func(waso_func, trues=trues, preds=preds)

        return res


# %% ../nbs/00_utils.ipynb 21
from sklearn.metrics import roc_auc_score, roc_curve, cohen_kappa_score

WASA_THRESHOLD = 0.93
BALANCE_WEIGHTS = True

def split_analysis(y, y_hat_sleep_proba, sleep_accuracy: float = WASA_THRESHOLD, balancing: bool = BALANCE_WEIGHTS):

    y_flat = y.reshape(-1,)
    n_sleep = np.sum(y_flat > 0)
    n_wake = np.sum(y_flat == 0)
    N = n_sleep + n_wake

    balancing_weights_ignore_mask = np.where(y_flat > 0, N / n_sleep, N / n_wake) \
        if balancing else np.ones_like(y_flat)
    balancing_weights_ignore_mask /= np.sum(balancing_weights_ignore_mask) # sums to 1.0

    # adjust y to match the lenght of y_hat, which was padded to fit model constraints
    y_padded = pad_to_hat(y_flat, y_hat_sleep_proba)
    # make a mask to ignore the padded values, so they aren't counted against us
    mask = pad_to_hat(balancing_weights_ignore_mask, y_hat_sleep_proba)

    # also ignore any unscored or missing values.
    y_to_score = pad_to_hat(y_flat >= 0, y_hat_sleep_proba)
    mask *= y_to_score
    # roc_auc will complain if -1 is in y_padded
    y_padded *= y_to_score 

    # ROC analysis
    fprs, tprs, thresholds = roc_curve(y_padded, y_hat_sleep_proba, sample_weight=mask)

    # Sleep accuracy = (n sleep correct) / (n sleep) = TP/AP = TPR
    wasa_threshold = thresholds[np.sum(tprs <= sleep_accuracy)]
    y_guess = y_hat_sleep_proba > wasa_threshold

    # # WASA X
    guess_right = y_guess == y_padded
    y_wake = y_padded == 0
    wake_accuracy = np.sum(y_wake * guess_right * y_to_score) / np.sum(n_wake)
     
    return {
        "y_padded": y_padded,
        "y_hat": y_hat_sleep_proba,
        "mask": mask,
        "kappa": cohen_kappa_score(y_padded, y_guess, sample_weight=mask),
        "auc": roc_auc_score(y_padded, y_hat_sleep_proba, sample_weight=mask),
        "roc_curve": {"tprs": tprs,
                      "fprs": fprs,
                      "thresholds": thresholds
        }, 
        f"wasa{int(100 * sleep_accuracy)}_threshold": wasa_threshold,
        f"wasa{int(100 * sleep_accuracy)}": wake_accuracy, 
    }
