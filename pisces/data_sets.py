# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/01_data_sets.ipynb.

# %% auto 0
__all__ = ['LOG_LEVEL', 'SimplifiablePrefixTree', 'IdExtractor', 'DataSetObject', 'ModelOutputType', 'PSGType', 'ModelInput',
           'ModelInput1D', 'ModelInputSpectogram', 'find_overlapping_time_section', 'ProcessedData']

# %% ../nbs/01_data_sets.ipynb 4
from pathlib import Path
from enum import Enum, auto
from typing import Dict, List, Tuple

# %% ../nbs/01_data_sets.ipynb 6
from copy import deepcopy
import warnings

class SimplifiablePrefixTree:
    """A standard prefix tree with the ability to "simplify" itself by combining nodes with only one child.

    These also have the ability to "flatten" themselves, which means to convert all nodes at and below a certain depth into leaves on the most recent ancestor of that depth.

    Parameters
    ----------
    delimiter : str
        The delimiter to use when splitting words into characters. If empty, the words are treated as sequences of characters.
    key : str
        The key of the current node in its parent's `.children` dictionary. If empty, the node is (likely) the root of the tree.
    
    Attributes
    ----------
    key : str
        The key of the current node in its parent's `.children` dictionary. If empty, the node is (likely) the root of the tree.
    children : Dict[str, SimplifiablePrefixTree]
        The children of the current node, stored in a dictionary with the keys being the children's keys.
    is_end_of_word : bool
        Whether the current node is the end of a word. Basically, is this a leaf node?
    delimiter : str
        The delimiter to use when splitting words into characters. If empty, the words are treated as sequences of characters.
    print_spacer : str
        The string to use to indent the printed tree.
    
    Methods
    -------
    chars_from(word: str) -> List[str]
        Splits a word into characters, using the `delimiter` attribute as the delimiter.
    insert(word: str) -> None
        Inserts a word into the tree.
    search(word: str) -> bool
        Searches for a word in the tree.
    simplified() -> SimplifiablePrefixTree
        Returns a simplified copy of the tree. The original tree is not modified.
    simplify() -> SimplifiablePrefixTree
        Simplifies the tree in place.
    reversed() -> SimplifiablePrefixTree
        Returns a reversed copy of the tree, except with with `node.key` reversed versus the node in `self.children`. The original tree is not modified.
    flattened(max_depth: int = 1) -> SimplifiablePrefixTree
        Returns a Tree identical to `self` up to the given depth, but with all nodes at + below `max_depth` converted into leaves on the most recent acestor of lepth `max_depth - 1`.
    _pushdown() -> List[SimplifiablePrefixTree]
        Returns a list corresponding to the children of `self`, with `self.key` prefixed to each child's key.
    print_tree(indent=0) -> str
        Prints the tree, with indentation.
    """
    def __init__(self, delimiter: str = "", key: str = ""):
        self.key = key
        self.children: Dict[str, SimplifiablePrefixTree] = {}
        self.is_end_of_word = False
        self.delimiter = delimiter
        self.print_spacer = "++"
    
    def chars_from(self, word: str):
        return word.split(self.delimiter) if self.delimiter else word

    def insert(self, word: str):
        node = self
        for char in self.chars_from(word):
            if char not in node.children:
                node.children[char] = SimplifiablePrefixTree(self.delimiter, key=char)
            node = node.children[char]
        node.is_end_of_word = True

    def search(self, word: str) -> bool:
        node = self
        for char in self.chars_from(word):
            if char not in node.children:
                return False
            node = node.children[char]
        return node.is_end_of_word
    
    def simplified(self) -> 'SimplifiablePrefixTree':
        self_copy = deepcopy(self)
        return self_copy.simplify()
    
    def simplify(self):
        if len(self.children) == 1 and not self.is_end_of_word:
            child_key = list(self.children.keys())[0]
            self.key += child_key
            self.children = self.children[child_key].children
            self.simplify()
        else:
            current_keys = list(self.children.keys())
            for key in current_keys:
                child = self.children.pop(key)
                child.simplify()
                self.children[child.key] = child
        return self
    
    def reversed(self) -> 'SimplifiablePrefixTree':
        rev_self = SimplifiablePrefixTree(self.delimiter, key=self.key[::-1])
        rev_self.children = {k[::-1]: v.reversed() for k, v in self.children.items()}
        return rev_self
    
    def flattened(self, max_depth: int = 1) -> 'SimplifiablePrefixTree':
        """Returns a Tree identical to `self` up to the given depth, but with all nodes at + below `max_depth` converted into leaves on the most recent acestor of lepth `max_depth - 1`.
        """
        flat_self = SimplifiablePrefixTree(self.delimiter, key=self.key)
        if max_depth == 0:
            if not self.is_end_of_word:
                warnings.warn(f"max_depth is 0, but {self.key} is not a leaf.")
            return flat_self
        if max_depth == 1:
            for k, v in self.children.items():
                if v.is_end_of_word:
                    flat_self.children[k] = SimplifiablePrefixTree(self.delimiter, key=k)
                else:
                    # flattened_children = v._pushdown()
                    for flattened_child in v._pushdown():
                        flat_self.children[flattened_child.key] = flattened_child
        else:
            for k, v in self.children.items():
                flat_self.children[k] = v.flattened(max_depth - 1)
        return flat_self
    
    def _pushdown(self) -> List['SimplifiablePrefixTree']:
        """Returns a list corresponding to the children of `self`, with `self.key` prefixed to each child's key.
        """
        pushed_down = [
            c
            for k in self.children.values()
            for c in k._pushdown()
        ]
        for i in range(len(pushed_down)):
            pushed_down[i].key = self.key + self.delimiter + pushed_down[i].key

        if not pushed_down:
            return [SimplifiablePrefixTree(self.delimiter, key=self.key)]
        else:
            return pushed_down
            

    def __str__(self):
        # prints .children recursively with indentation
        return self.key + "\n" + self.print_tree()

    def print_tree(self, indent=0) -> str:
        result = ""
        for key, child in self.children.items():
            result +=  self.print_spacer * indent + "( " + child.key + "\n"
            result += SimplifiablePrefixTree.print_tree(child, indent + 1)
        return result


class IdExtractor(SimplifiablePrefixTree):
    """Class extending the prefix trees that incorporates the algorithm for extracting IDs from a list of file names. The algorithm is somewhat oblique, so it's better to just use the `extract_ids` method versus trying to use the prfix trees directly at the call site.
    
    The algorithm is based on the assumption that the IDs are the same across all file names, but that the file names may have different suffixes. The algorithm reverses the file names, inserts them into the tree, and then simplifes and flattens that tree in order to find the IDs as leaves of that simplified tree.

    1. Insert the file name string into the tree, but with each string **reversed**.
    2. Simplify the tree, combining nodes with only one child.
    3. There may be unexpected suffix matches for these IDs, so we flatten the tree to depth 1, meaning all children of the root are combined to make leaves.
    4. The leaves are the IDs we want to extract. However, we must reverse these leaf keys to get the original IDs, since we reversed the file names in step 1.

    TODO:
    * If we want to find IDs for files with differing prefixes instead, we should instead insert the file names NOT reversed and then NOT reverse in the last step.

    * To handle IDs that appear in the middle of file names, we can use both methods to come up with a list of potential IDs based on prefix and suffix, then figure out the "intersection" of those lists. (Maybe using another prefix tree?)

    """
    def __init__(self, delimiter: str = "", key: str = ""):
        super().__init__(delimiter, key)

    def extract_ids(self, files: List[str]) -> List[str]:
        for file in files:
            self.insert(file[::-1])
        return sorted([
            c.key for c in self
                .prefix_flattened()
                .children
                .values()
        ])
    
    def prefix_flattened(self) -> 'IdExtractor':
        return self.simplified().flattened(1).reversed()
    

# %% ../nbs/01_data_sets.ipynb 11
import os
import re
from typing import DefaultDict, Iterable
from collections import defaultdict
import logging

import polars as pl
import numpy as np
from .utils import determine_header_rows_and_delimiter

LOG_LEVEL = logging.INFO

class DataSetObject:
    FEATURE_PREFIX = "cleaned_"

    # Set up logging
    logger = logging.getLogger(__name__)
    logger.setLevel(LOG_LEVEL)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path
        self.ids: List[str] = []

        # keeps track of the files for each feature and user
        self._feature_map: DefaultDict[str, Dict[str, str]] = defaultdict(dict)
        self._feature_cache: DefaultDict[str, Dict[str, pl.DataFrame]] = defaultdict(dict)
    
    @property
    def features(self) -> List[str]:
        return list(self._feature_map.keys())
    
    def __str__(self):
        return f"{self.name}: {self.path}"

    def get_feature_data(self, feature: str, id: str) -> pl.DataFrame | None:
        if feature not in self.features:
            warnings.warn(f"Feature {feature} not found in {self.name}. Returning None.")
            return None
        if id not in self.ids:
            warnings.warn(f"ID {id} not found in {self.name}")
            return None
        if (df := self._feature_cache[feature].get(id)) is None:
            file = self.get_filename(feature, id)
            if not file:
                return None
            self.logger.debug(f"Loading {file}")
            try:
                n_rows, delimiter = determine_header_rows_and_delimiter(file)
                # self.logger.debug(f"n_rows: {n_rows}, delimiter: {delimiter}")
                df = pl.read_csv(file, has_header=True if n_rows > 0 else False,
                                 skip_rows=max(n_rows-1, 0), 
                                 separator=delimiter)
            except Exception as e:
                warnings.warn(f"Error reading {file}:\n{e}")
                return None
            # sort by time when loading
            df.sort(df.columns[0])
            self._feature_cache[feature][id] = df
        return df

    def get_filename(self, feature: str, id: str) -> Path | None:
        feature_ids = self._feature_map.get(feature)
        if feature_ids is None:
            # raise ValueError(f"Feature {feature_ids} not found in {self.name}")
            print(f"Feature {feature_ids} not found in {self.name}")
            return None
        file = feature_ids.get(id)
        if file is None:
            # raise ValueError
            print(f"ID {id} not found in {self.name}")
            return None
        return self.get_feature_path(feature)\
            .joinpath(file)
    
    def get_feature_path(self, feature: str) -> Path:
        return self.path.joinpath(self.FEATURE_PREFIX + feature)
    
    def _extract_ids(self, files: List[str]) -> List[str]:
        return IdExtractor().extract_ids(files)
    
    def add_feature_files(self, feature: str, files: Iterable[str]):
        if feature not in self.features:
            self.logger.debug(f"Adding feature {feature} to {self.name}")
            self._feature_map[feature] = {}
        # use a set for automatic deduping
        deduped_ids = set(self.ids)
        extracted_ids = sorted(self._extract_ids(files))
        files = sorted(list(files))
        # print('# extracted_ids:', len(extracted_ids))
        for id, file in zip(extracted_ids, files):
            # print('adding data for id:', id, 'file:', file)
            self._feature_map[feature][id] = file
            # set.add only adds the value if it's not already in the set
            deduped_ids.add(id)
        self.ids = sorted(list(deduped_ids))
    
    def get_feature_files(self, feature: str) -> Dict[str, str]:
        return {k: v for k, v in self._feature_map[feature].items()}
    
    def get_id_files(self, id: str) -> Dict[str, str]:
        return {k: v[id] for k, v in self._feature_map.items()}
    
    def load_feature_data(self, feature: str | None, id: str | None) -> Dict[str, np.ndarray]:
        if feature not in self.features:
            raise ValueError(f"Feature {feature} not found in {self.name}")
    
    @classmethod
    def find_data_sets(cls, root: str | Path) -> Dict[str, 'DataSetObject']:
        set_dir_regex = r".*" + cls.FEATURE_PREFIX + r"(.+)"
        # this regex matches the feature directory name and the data set name
        # but doesn't work on Windows (? maybe, cant test) because of the forward slashes
        feature_dir_regex = r".*/(.+)/" + cls.FEATURE_PREFIX + r"(.+)"

        data_sets: Dict[str, DataSetObject] = {}
        for root, dirs, files in os.walk(root, followlinks=True):
            # check to see if the root is a feature directory,
            # if it is, add that feature data to the data set object,
            # creating a new data set object if necessary.
            if (root_match := re.match(feature_dir_regex, root)):
                cls.logger.debug(f"Feature directory: {root}")
                cls.logger.debug(f"data set name: {root_match.group(1)}")
                cls.logger.debug(f"feature is: {root_match.group(2)}", )
                data_set_name = root_match.group(1)
                feature_name = root_match.group(2)
                if (data_set := data_sets.get(data_set_name)) is None:
                    data_set = DataSetObject(root_match.group(1), Path(root).parent)
                    data_sets[data_set.name] = data_set
                files = [f for f in files if not f.startswith(".") and not f.endswith(".tmp")]
                data_set.add_feature_files(feature_name, files)
        
        return data_sets
    



# %% ../nbs/01_data_sets.ipynb 13
class ModelOutputType(Enum):
    SLEEP_WAKE = auto()
    WAKE_LIGHT_DEEP_REM = auto()

class PSGType(Enum):
    HAS_N4 = auto()
    NO_N4 = auto()

class ModelInput:
    def __init__(self,
                 input_features: List[str] | str,
                 ):
        if isinstance(input_features, str):
            input_features = [input_features]
        self.input_features = input_features

class ModelInput1D(ModelInput):
    def __init__(self,
                 input_features: List[str] | str,
                 input_window_size: int | float, # Window size (in seconds) for the input data. Window will be centered around the time point for which the model is making a prediction
                 input_sampling_hz: int | float, # Sampling rate of the input data (1/s)
                 ):
        super().__init__(input_features)
        # input_window_size
        if not isinstance(input_window_size, (int, float)):
            raise ValueError("input_window_size must be an int or a float")
        else:
            if input_window_size <= 0:
                raise ValueError("input_window_size must be greater than 0")
        # input_sampling_hz
        if not isinstance(input_sampling_hz, (int, float)):
            raise ValueError("input_sampling_hz must be an int or a float")
        else:
            if input_sampling_hz <= 0:
                raise ValueError("input_sampling_hz must be greater than 0")

        self.input_window_size = float(input_window_size)
        self.input_sampling_hz = float(input_sampling_hz)
        # Number of samples for the input window of a single feature
        self.input_window_samples = int(self.input_window_size * self.input_sampling_hz)
        ## force it to be odd to have perfectly centered window
        if self.input_window_samples % 2 == 0:
            self.input_window_samples += 1
        # Dimension of the input data for the model
        self.model_input_dimension = int(len(input_features) * self. input_window_samples)

class ModelInputSpectogram(ModelInput):
    # variables specific to this case
    pass

# %% ../nbs/01_data_sets.ipynb 14
def find_overlapping_time_section(
     data_set: DataSetObject,
     features: List[str], # List of features included in the calculation, typically a combination of input and output features
     id: str, # Subject id to process
     ) -> Tuple[int, int]:
     '''
     Find common time interval when there's data for all features
     '''
     max_start = None
     min_end = None
     for feature in features:
          data = data_set.get_feature_data(feature, id)
          time = data[:, 0]
          if max_start is None:
               max_start = time.min()
          else:
               max_start = max([max_start, time.min()])
          if min_end is None:
               min_end = time.max()
          else:
               min_end = min([min_end, time.max()])
     return (max_start, min_end)

# %% ../nbs/01_data_sets.ipynb 15
class ProcessedData:
    def __init__(self, 
                 data_set: DataSetObject,
                 model_input: ModelInput,
                 output_feature: str='psg',
                 output_type: ModelOutputType=ModelOutputType.WAKE_LIGHT_DEEP_REM,
                 psg_type: PSGType=PSGType.HAS_N4,
                 ):
        # Currently developing support for one dimensional input type
        self.data_set = data_set
        self.input_features = model_input.input_features
        self.output_feature = output_feature
        self.output_type = output_type
        self.psg_type = psg_type

        if isinstance(model_input, ModelInput1D):
            self.input_window_size = model_input.input_window_size
            self.input_sampling_hz = model_input.input_sampling_hz
            self.input_window_samples = model_input.input_window_samples
            self.model_input_dimension = model_input.model_input_dimension
        elif isinstance(model_input, ModelInputSpectogram):
            raise NotImplementedError("Spectogram input type not yet supported")

    def get_labels(self, id: str, start: int, end: int,
                   output_feature: str) -> pl.DataFrame | None:
        data = self.data_set.get_feature_data(output_feature, id)
        data = data.filter(data[:, 0] >= start)
        data = data.filter(data[:, 0] <= end)
        return data

    def get_1D_X_for_feature(self, interpolation_timestamps: np.ndarray, 
                             epoch_times: np.ndarray, feature_times: np.ndarray, 
                             feature_values: np.ndarray) -> np.ndarray:
            interpolation = np.interp(interpolation_timestamps, feature_times, feature_values)
            X_feature = []
            for t in epoch_times:
                t_idx = np.argmin(np.abs(interpolation_timestamps - t))
                # Window centered around t with half `window_samples` on each side
                window_idx_start = t_idx - self.input_window_samples // 2
                window_idx_end = t_idx + self.input_window_samples // 2 + (self.input_window_samples % 2)
                window_data = interpolation[window_idx_start:window_idx_end]
                # reshape into (1, window_size)
                window_data = window_data.reshape(1, -1)
                X_feature.append(window_data)
            # create a numpy array of shape (n_samples, window_size)
            X_feature = np.vstack(X_feature)
            return X_feature

    def get_1D_X_y(self, id: str) -> Tuple[np.ndarray, np.ndarray] | None:
        # Find overlapping time section
        max_start, min_end = find_overlapping_time_section(self.data_set, 
                                                           self.input_features,
                                                           id)
        # Get labels
        labels = self.get_labels(id, max_start, min_end, self.output_feature)
        label_times = labels[:, 0]
        epoch_start = label_times.min() + self.input_window_size / 2.0
        epoch_end = label_times.max() - self.input_window_size / 2.0
        filtered_labels = labels.filter(labels[:, 0] >= epoch_start)
        filtered_labels = filtered_labels.filter(filtered_labels[:, 0] <= epoch_end)
        epoch_times = filtered_labels[:, 0]
        # Get input data
        interpolation_timestamps = np.arange(max_start, 
                                             min_end, 
                                             1.0/self.input_sampling_hz)
        # Interpolate all data to the same time points
        interpolated_features = []
        for feature in self.input_features:
            data = self.data_set.get_feature_data(feature, id)
            feature_times = data[:, 0]
            if feature == 'accelerometer':
                # Handle accelerometer data
                for i in range(1, 4):
                    feature_values = data[:, i]
                    X_feature = self.get_1D_X_for_feature(interpolation_timestamps, 
                                                          epoch_times, feature_times, 
                                                          feature_values)
                    interpolated_features.append(X_feature)
            else:
                feature_values = data[:, 1]
                X_feature = self.get_1D_X_for_feature(interpolation_timestamps, 
                                                      epoch_times, feature_times, 
                                                      feature_values)
                interpolated_features.append(X_feature)
        # Concatenate input features alongside the first dimension
        X = np.concatenate(interpolated_features, axis=1)
        y = filtered_labels[:, 1].to_numpy()
        return X, y
