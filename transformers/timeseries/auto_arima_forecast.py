"""Auto ARIMA transformer is a time series transformer that predicts target using ARIMA models"""

# For more information about the python ARIMA package
# please visit https://www.alkaline-ml.com/pmdarima/index.html

import importlib

from h2oaicore.transformer_utils import CustomTimeSeriesTransformer
import datatable as dt
import numpy as np
import pandas as pd


class MyAutoArimaTransformer(CustomTimeSeriesTransformer):
    _binary = False
    _multiclass = False
    _modules_needed_by_name = ['pmdarima']
    _included_model_classes = None

    @staticmethod
    def get_default_properties():
        return dict(col_type="time_column", min_cols=1, max_cols=1, relative_importance=1)

    def fit(self, X: dt.Frame, y: np.array = None):
        """
        Fits ARIMA models (1 per time group) using historical target values contained in y
        :param X: Datatable frame containing the features
        :param y: numpy array containing the historical values of the target
        :return: self
        """
        # Import the ARIMA python module
        pm = importlib.import_module('pmdarima')
        # Init models
        self.models = {}
        # Convert to pandas
        X = X.to_pandas()
        XX = X[self.tgc].copy()
        XX['y'] = np.array(y)
        self.nan_value = np.mean(y)
        self.ntrain = X.shape[0]

        # Group the input by TGC (Time group column) excluding the time column itself
        tgc_wo_time = list(np.setdiff1d(self.tgc, self.time_column))
        if len(tgc_wo_time) > 0:
            XX_grp = XX.groupby(tgc_wo_time)
        else:
            XX_grp = [([None], XX)]

        # Build 1 ARIMA model per time group columns
        for key, X in XX_grp:
            key = key if isinstance(key, list) else [key]
            grp_hash = '_'.join(map(str, key))
            # print("auto arima - fitting on data of shape: %s for group: %s" % (str(X.shape), grp_hash))
            order = np.argsort(X[self.time_column])
            try:
                model = pm.auto_arima(X['y'].values[order], error_action='ignore')
            except:
                model = None
            self.models[grp_hash] = model
        return self

    def transform(self, X: dt.Frame):
        """
        Uses fitted models (1 per time group) to predict the target
        If self.is_train exists, it means we are doing in-sample predictions
        if it does not then we Arima is used to predict the future
        :param X: Datatable Frame containing the features
        :return: ARIMA predictions
        """
        X = X.to_pandas()
        XX = X[self.tgc].copy()
        tgc_wo_time = list(np.setdiff1d(self.tgc, self.time_column))
        if len(tgc_wo_time) > 0:
            XX_grp = XX.groupby(tgc_wo_time)
        else:
            XX_grp = [([None], XX)]
        preds = []
        for key, X in XX_grp:
            key = key if isinstance(key, list) else [key]
            grp_hash = '_'.join(map(str, key))
            # print("auto arima - transforming data of shape: %s for group: %s" % (str(X.shape), grp_hash))
            order = np.argsort(X[self.time_column])
            if grp_hash in self.models:
                model = self.models[grp_hash]
                if model is not None:
                    yhat = model.predict_in_sample() \
                        if hasattr(self, 'is_train') else model.predict(n_periods=X.shape[0])
                    yhat = yhat[order]
                    XX = pd.DataFrame(yhat, columns=['yhat'])
                else:
                    XX = pd.DataFrame(np.full((X.shape[0], 1), self.nan_value), columns=['yhat'])  # invalid model
            else:
                XX = pd.DataFrame(np.full((X.shape[0], 1), self.nan_value), columns=['yhat'])  # unseen groups
            XX.index = X.index
            preds.append(XX)
        XX = pd.concat(tuple(preds), axis=0).sort_index()

        return XX

    def fit_transform(self, X: dt.Frame, y: np.array = None):
        """
        Fits the ARIMA models (1 per time group) and outputs the corresponding predictions
        :param X: Datatable Frame
        :param y: Target to be used to fit the ARIMA model and perdict in-sample
        :return: in-sample ARIMA predictions
        """
        # Flag the fact we are doing in-sample predictions
        self.is_train = True
        ret = self.fit(X, y).transform(X)
        del self.is_train
        return ret

    def update_history(self, X: dt.Frame, y: np.array = None):
        """
        Update the model fit with additional observed endog/exog values.
        Updating an ARIMA adds new observations to the model, updating the MLE of the parameters
        accordingly by performing several new iterations (maxiter) from the existing model parameters.
        :param X: Datatable Frame containing input features
        :param y: Numpy array containing new observations to update the ARIMA model
        :return:
        """
        X = X.to_pandas()
        XX = X[self.tgc].copy
        XX['y'] = np.array(y)
        tgc_wo_time = list(np.setdiff1d(self.tgc, self.time_column))
        if len(tgc_wo_time) > 0:
            XX_grp = XX.groupby(tgc_wo_time)
        else:
            XX_grp = [([None], XX)]
        for key, X in XX_grp:
            key = key if isinstance(key, list) else [key]
            grp_hash = '_'.join(map(str, key))
            print("auto arima - update history with data of shape: %s for group: %s" % (str(X.shape), grp_hash))
            order = np.argsort(X[self.time_column])
            if grp_hash in self.models:
                model = self.models[grp_hash]
                if model is not None:
                    model.update(X['y'].values[order])
        return self
