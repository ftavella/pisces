# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/02_models.ipynb.

# %% auto 0
__all__ = ['SleepWakeClassifier', 'SGDLogisticRegression', 'MOResUNetPretrained', 'SplitMaker', 'LeaveOneOutSplitter',
           'run_split', 'run_splits']

# %% ../nbs/02_models.ipynb 4
import sys
import keras
import numpy as np
import polars as pl
from tqdm import tqdm
from io import StringIO
from pathlib import Path
from enum import Enum, auto
from itertools import repeat
from typing import Dict, List, Tuple
from .data_sets import DataSetObject, ModelInput1D, ModelInputSpectrogram, ModelOutputType, DataProcessor

# %% ../nbs/02_models.ipynb 6
import abc
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
import numpy as np


class SleepWakeClassifier(abc.ABC):
    """
    """
    @abc.abstractmethod
    def get_needed_X_y(self, data_set: DataSetObject, id: str) -> Tuple[np.ndarray, np.ndarray] | None:
        pass
    def train(self, examples_X: List[pl.DataFrame] = [], examples_y: List[pl.DataFrame] = [], 
              pairs_Xy: List[Tuple[pl.DataFrame, pl.DataFrame]] = [], 
              epochs: int = 10, batch_size: int = 32):
        pass
    def predict(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        pass
    def predict_probabilities(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        pass


# %% ../nbs/02_models.ipynb 8
class SGDLogisticRegression(SleepWakeClassifier):
    """Uses Sk-Learn's `SGDCLassifier` to train a logistic regression model. The SGD aspect allows for online learning, or custom training regimes through the `partial_fit` method.
     
    The model is trained with a balanced class weight, and uses L1 regularization. The input data is scaled with a `StandardScaler` before being passed to the model.
    """
    def __init__(self, 
                 data_processor: DataProcessor, 
                 lr: float = 0.15, 
                 epochs: int = 100,):
        self.model = SGDClassifier(loss='log_loss',
                                   learning_rate='adaptive',
                                   penalty='l1',
                                   eta0=lr,
                                   class_weight='balanced',
                                   max_iter=epochs,
                                   warm_start=True,
                                   verbose=1)
        self.scaler = StandardScaler()
        self.pipeline = Pipeline([('scaler', self.scaler), ('model', self.model)])
        if not isinstance(data_processor.model_input, ModelInput1D):
            raise ValueError("Model input must be set to 1D on the data processor")
        if not data_processor.output_type == ModelOutputType.SLEEP_WAKE:
            raise ValueError("Model output must be set to SleepWake on the data processor")
        self.data_processor = data_processor

    def get_needed_X_y(self, id: str) -> Tuple[np.ndarray, np.ndarray] | None:
        return self.data_processor.get_1D_X_y(id)

    def train(self, 
              examples_X: List[np.ndarray]=[], 
              examples_y: List[np.ndarray]=[], 
              pairs_Xy: List[Tuple[np.ndarray, np.ndarray]]=[],
              epochs: int = 10,
              ):
        """
        Assumes data is already preprocessed using `get_needed_X_y` 
        and ready to be passed to the model.

        Returns the loss history of the model.
        """
        if (examples_X and not examples_y) or (examples_y and not examples_X):
            raise ValueError("If providing examples, must provide both X and y")
        else:
            if examples_X and examples_y:
                assert len(examples_X) == len(examples_y)
        if pairs_Xy:
            assert not examples_X
            examples_X = [pair[0] for pair in pairs_Xy]
            examples_y = [pair[1] for pair in pairs_Xy]


        Xs = np.concatenate(examples_X, axis=0)
        ys = np.concatenate(examples_y, axis=0)

        selector = ys >= 0
        Xs = Xs[selector]
        ys = ys[selector]

        # Get loss
        old_stdout = sys.stdout
        sys.stdout = mystdout = StringIO()
        self.pipeline.fit(Xs, ys) # Fit the model
        sys.stdout = old_stdout
        loss_history = mystdout.getvalue()
        loss_list = []
        for line in loss_history.split('\n'):
            if(len(line.split("loss: ")) == 1):
                continue
            loss_list.append(float(line.split("loss: ")[-1]))

        return loss_list
    
    def _input_preprocessing(self, X: np.ndarray) -> np.ndarray:
        return self.scaler.transform(X)
    
    def predict(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        """
        Assumes data is already preprocessed using `get_needed_X_y`
        """
        return self.model.predict(self._input_preprocessing(sample_X))
    
    def predict_probabilities(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        """
        Assumes data is already preprocessed using `get_needed_X_y`
        """
        return self.model.predict_proba(self._input_preprocessing(sample_X))

# %% ../nbs/02_models.ipynb 10
from functools import partial
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import warnings

from .mads_olsen_support import *
from .utils import split_analysis


class MOResUNetPretrained(SleepWakeClassifier):
    tf_model = load_saved_keras()
    config = MO_PREPROCESSING_CONFIG

    def __init__(
        self,
        sampling_hz: int = FS,
        tf_model: keras.Model = None,
    ) -> None:
        """
        Initialize the MOResUNetPretrained classifier.

        Args:
            sampling_hz (int, optional): The sampling frequency in Hz. Defaults to FS.
            tf_model (keras.Model, optional): The TensorFlow model to use. Defaults to None, in which case the model is loaded from disk.
        """
        super().__init__()
        self.sampling_hz = sampling_hz
        self._tf_model = tf_model

    @property
    def tf_model(self) -> keras.Model:
        if self._tf_model is None:
            self._tf_model = load_saved_keras()
        return self._tf_model

    def prepare_set_for_training(self, 
                                 data_processor: DataProcessor, 
                                 ids: List[str],
                                 max_workers: int | None = None 
                                 ) -> List[Tuple[np.ndarray, np.ndarray] | None]:
        """
        Prepare the data set for training.

        Args:
            data_set (DataSetObject): The data set to prepare for training.
            ids (List[str], optional): The IDs to prepare. Defaults to None.
            max_workers (int, optional): The number of workers to use for parallel processing. Defaults to None, which uses all available cores. Setting to a negative number leaves that many cores unused. For example, if my machine has 4 cores and I set max_workers to -1, then 3 = 4 - 1 cores will be used; if max_workers=-3 then 1 = 4 - 3 cores are used.

        Returns:
            List[Tuple[np.ndarray, np.ndarray] | None]: A list of tuples, where each tuple is the result of `get_needed_X_y` for a given ID. An empty list indicates an error occurred during processing.
        """
        results = []
        
        # Get the number of available CPU cores
        num_cores = multiprocessing.cpu_count()
        workers_to_use = max_workers if max_workers is not None else num_cores
        if (workers_to_use > num_cores):
            warnings.warn(f"Attempting to use {max_workers} but only have {num_cores}. Running with {num_cores} workers.")
            workers_to_use = num_cores
        if workers_to_use <= 0:
            workers_to_use = num_cores + max_workers
        if workers_to_use < 1:
            # do this check second, NOT with elif, to verify we're still in a valid state
            raise ValueError(f"With `max_workers` == {max_workers}, we end up with max_workers + num_cores ({max_workers} + {num_cores}) which is less than 1. This is an error.")

        print(f"Using {workers_to_use} of {num_cores} cores ({int(100 * workers_to_use / num_cores)}%) for parallel preprocessing.")
        print(f"This can cause memory or heat issues if  is too high; if you run into problems, call prepare_set_for_training() again with max_workers = -1, going more negative if needed. (See the docstring for more info.)")
        # Create a pool of workers
        with ProcessPoolExecutor(max_workers=workers_to_use) as executor:
            results = list(
                tqdm(
                    executor.map(
                        self.get_needed_X_y,
                        repeat(data_processor),
                        ids,
                    ), total=len(ids), desc="Preparing data..."
                ))

        return results

    def get_needed_X_y(self, data_processor: DataProcessor, id: str) -> Tuple[np.ndarray, np.ndarray] | None:
        return data_processor.get_spectrogram_X_y(id)

    def train(self, 
              examples_X: List[pl.DataFrame] = [], 
              examples_y: List[pl.DataFrame] = [], 
              pairs_Xy: List[Tuple[pl.DataFrame, pl.DataFrame]] = [], 
              lr: float = 1e-5, validation_split: float = 0.1,
              epochs: int = 10, batch_size: int = 1,):
        """
        Trains the associated Keras model.
        """
        if examples_X or examples_y:
            assert len(examples_X) == len(examples_y)
        if pairs_Xy:
            assert not examples_X

        training = []
        training_iterator = iter(pairs_Xy) if pairs_Xy else zip(examples_X, examples_y)
        for X, y in training_iterator:
            try:
                y_reshaped = np.pad(
                    y.reshape(1, -1), 
                    pad_width=[
                        (0, 0), # axis 0, no padding
                        (0, N_OUT - y.shape[0]), # axis 1, pad to N_OUT from mads_olsen_support
                    ],
                    mode='constant', 
                    constant_values=0) 
                sample_weights = y_reshaped >= 0
                training.append((X, y_reshaped, sample_weights))
            except Exception as e:
                print(f"Error folding or trimming data: {e}")
                continue

        Xs = [X for X, _, _ in training]
        ys = [y for _, y, _ in training]
        weights = [w for _, _, w in training]
        Xs_c = np.concatenate(Xs, axis=0)
        ys_c = np.concatenate(ys, axis=0)
        weights = np.concatenate(weights, axis=0)

        self.tf_model.compile(
            optimizer=keras.optimizers.RMSprop(learning_rate=lr), 
            loss=keras.losses.SparseCategoricalCrossentropy(),
            metrics=[keras.metrics.SparseCategoricalAccuracy()],
            weighted_metrics=[])

        fit_result = self.tf_model.fit(
            Xs_c, ys_c * weights, batch_size=batch_size, epochs=epochs,
            sample_weight=weights, validation_split=validation_split,)

        return fit_result

    def predict(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        return np.argmax(self.predict_probabilities(sample_X), axis=1)

    def predict_probabilities(self, sample_X: np.ndarray | pl.DataFrame) -> np.ndarray:
        if isinstance(sample_X, pl.DataFrame):
            sample_X = sample_X.to_numpy()
        return self._evaluate_tf_model(sample_X)[0]

    def _evaluate_tf_model(self, inputs: np.ndarray) -> np.ndarray:
        inputs = inputs.astype(np.float32)
        preds = self.tf_model.predict(inputs)
        return preds

    def evaluate_data_set(self, 
                          data_processor: DataProcessor, 
                          exclude: List[str] = [], 
                          max_workers: int = None) -> Tuple[Dict[str, dict], list]:
        data_set = data_processor.data_set
        filtered_ids = [id for id in data_set.ids if id not in exclude]
        # Prepare the data
        print("Preprocessing data...")
        mo_preprocessed_data = [
            (d, i) 
            for (d, i) in zip(
                self.prepare_set_for_training(data_processor, filtered_ids, max_workers=max_workers),
                filtered_ids) 
            if d is not None
        ]

        print("Evaluating data set...")
        evaluations: Dict[str, dict] = {}
        for _, ((X, y_true), id) in tqdm(enumerate(mo_preprocessed_data)):
            y_prob = self.predict_probabilities(X)
            m = keras.metrics.SparseCategoricalAccuracy()
            # Remove masked values
            selector = y_true >= 0
            y_true_filtered = y_true[selector]
            y_prob_filtered = y_prob[selector]
            # Calculate sample weights
            unique, counts = np.unique(y_true_filtered, return_counts=True)
            class_weights = dict(zip(unique, counts))
            inv_class_weights = {k: 1.0 / v for k, v in class_weights.items()}
            min_weight = min(inv_class_weights.values())
            normalized_weights = {k: v / min_weight for k, v in inv_class_weights.items()}
            sample_weights = np.array([normalized_weights[class_id] for class_id in y_true_filtered])
            # Sparse categorical accuracy
            y_true_reshaped = y_true_filtered.reshape(-1, 1)
            m.update_state(y_true_reshaped, y_prob_filtered, sample_weight=sample_weights)
            accuracy = m.result().numpy()
            evaluations[id] = {
                'sparse_categorical_accuracy': accuracy,
            }

        return evaluations, mo_preprocessed_data

# %% ../nbs/02_models.ipynb 12
from typing import Type
from tqdm import tqdm
from sklearn.model_selection import LeaveOneOut


class SplitMaker:
    def split(self, ids: List[str]) -> Tuple[List[int], List[int]]:
        raise NotImplementedError
    
class LeaveOneOutSplitter(SplitMaker):
    def split(self, ids: List[str]) -> Tuple[List[int], List[int]]:
        loo = LeaveOneOut()
        return loo.split(ids)


def run_split(train_indices, 
              preprocessed_data_set: List[Tuple[np.ndarray, np.ndarray]], 
              swc: SleepWakeClassifier,
              epochs: int) -> SleepWakeClassifier:
    training_pairs = [
        preprocessed_data_set[i][0]
        for i in train_indices
        if preprocessed_data_set[i][0] is not None
    ]
    result = swc.train(pairs_Xy=training_pairs, epochs=epochs)

    return swc, result


def run_splits(split_maker: SplitMaker, 
               data_processor: DataProcessor, 
               swc_class: Type[SleepWakeClassifier], 
               epochs: int,
               exclude: List[str] = [],
               ) -> Tuple[
                   List[SleepWakeClassifier], 
                   List[np.ndarray], 
                   List[List[List[int]]] 
                   ]:
    split_models: List[swc_class] = []
    test_indices = []
    split_results = []
    splits = []

    swc = swc_class(data_processor, epochs=epochs)

    ids_to_split = [id for id in data_processor.data_set.ids if id not in exclude]
    tqdm_message_preprocess = f"Preparing data for {len(ids_to_split)} IDs"
    preprocessed_data = [(swc.get_needed_X_y(id), id) for id in tqdm(ids_to_split, desc=tqdm_message_preprocess)]

    tqdm_message_train = f"Training {len(ids_to_split)} splits"
    all_splits = split_maker.split(ids_to_split)
    for train_index, test_index in tqdm(all_splits, desc=tqdm_message_train, total=len(ids_to_split)):
        if preprocessed_data[test_index[0]][0] is None:
            continue
        model, result = run_split(train_indices=train_index, 
                                  preprocessed_data_set=preprocessed_data, 
                                  swc=swc_class(data_processor, epochs=epochs), 
                                  epochs=epochs)
        split_models.append(model)
        split_results.append(result)
        test_indices.append(test_index[0])
        splits.append([train_index, test_index])
    
    return split_models, split_results, preprocessed_data, splits
